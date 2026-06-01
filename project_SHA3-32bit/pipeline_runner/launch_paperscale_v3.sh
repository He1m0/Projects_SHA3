#!/usr/bin/env sh
# Launch paperscale-v3 sigma sweep (36 runs: 9 sigmas × 4 modes).
#
# CRITICAL: All 36 runs need fresh simulation (paperscale_v2 trace dirs are gone).
#   traces_paperscale_v3_{mode}_sigma{X} will be created on IDP during simulation.
#
# SIMULATION CAP: max 3 concurrent simulations (disk-write bandwidth limit on IDP).
# R2 RAM CAP:     max 18 concurrent R2 processes (~33 GB commit/process, ~600 GB total).
#
# Wave structure (each wave = 3 concurrent simulations → auto-transition to R2):
#   Wave A1/A2/A3 : hd mode, sigma 0p1-1p0 / 1p5-2p5 / 3p0-4p0
#   Wave B1/B2/B3 : hw mode, same sigma batches
#   Wave C1/C2/C3 : id mode, same sigma batches
#   Wave D1/D2/D3 : f9 mode, same sigma batches
#
# Recommended launch order (keeps total sims ≤ 9, R2 ≤ 18):
#   1. Launch A1 + B1 + D1 simultaneously   (9 sims)
#   2. Check R2: pgrep -c -f detect_script  → wait until ≤ 15 before next batch
#   3. Launch A2 + B2 + D2                  (9 more sims)
#   4. R2 count ≤ 12 → Launch C1 + D3 etc.
#   5. Proceed until all 12 batches launched.
#
# ICS level for σ≥3.0: PLACEHOLDER (midscale-derived). Before training starts for
# any σ=3.0/3.5/4.0 run, run check_ics_archive.py to verify or find higher level:
#   ssh IDP "for level in 090 080 070 060 050 040 030 020 010; do
#     python3 \$sb/pipeline_runner/check_ics_archive.py \
#       --ics-zip \$sb/0002_detection/Code_extract_ics/ics_original_\${level}.zip \
#       2>&1 | grep -E 'OK:|ERROR' && break; done"
#   If higher level passes → apply --skip-detection fix to use it.
#
# Usage:
#   sh launch_paperscale_v3.sh --wave WAVE [--dry-run]
#   sh launch_paperscale_v3.sh --status
#   sh launch_paperscale_v3.sh --ics-scan   (run after all σ≥3.0 runs show [MOVE:DN])
#
# WAVE values: A1 A2 A3 B1 B2 B3 C1 C2 C3 D1 D2 D3

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ENVS_BASE="${SCRIPT_DIR}/envs/paperscale_v3_sigma_sweep"
DRY_RUN=0

# ── helpers ──────────────────────────────────────────────────────────────────

print_help() {
  sed -n '2,/^set -eu/{ /^set -eu/d; s/^# \{0,1\}//; p }' "$0"
  exit 0
}

launch_single() {
  env_file="$1"
  name=$(basename "${env_file}" | sed 's/^\.env_//')
  echo "  Launching: ${name}"
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "    [DRY RUN] run_sandboxes.sh --ssh IDP ${env_file}"
    return
  fi
  tmp_dir="/tmp/paperscale_v3_single_$$_${name}"
  mkdir -p "${tmp_dir}"
  cp "${env_file}" "${tmp_dir}/"
  sh "${SCRIPT_DIR}/run_sandboxes.sh" \
    --envs-dir "${tmp_dir}" \
    --ssh IDP
  rm -rf "${tmp_dir}"
}

check_r2_count() {
  count=$(ssh IDP "pgrep -c -f detect_script 2>/dev/null || echo 0")
  echo "Current R2 processes on IDP: ${count} (cap: 18)"
  if [ "${count}" -gt 18 ]; then
    echo "WARNING: ${count} > 18. Do not launch more R2 until count drops."
    return 1
  fi
  return 0
}

check_r2_warn_only() {
  count=$(ssh IDP "pgrep -c -f detect_script 2>/dev/null || echo 0")
  if [ "${count}" -gt 15 ]; then
    echo "  R2 count=${count} (warning: approaching cap 18). Consider waiting."
  else
    echo "  R2 count=${count} — OK to launch."
  fi
}

launch_batch() {
  mode="$1"; sigma1="$2"; sigma2="$3"; sigma3="$4"
  sigma_dir1="${ENVS_BASE}/sigma${sigma1}"
  sigma_dir2="${ENVS_BASE}/sigma${sigma2}"
  sigma_dir3="${ENVS_BASE}/sigma${sigma3}"
  echo "  Batch: ${mode} σ=${sigma1}/${sigma2}/${sigma3}"
  check_r2_warn_only
  launch_single "${sigma_dir1}/.env_paperscale_v3_${mode}_sigma${sigma1}"
  launch_single "${sigma_dir2}/.env_paperscale_v3_${mode}_sigma${sigma2}"
  launch_single "${sigma_dir3}/.env_paperscale_v3_${mode}_sigma${sigma3}"
}

# ── status ────────────────────────────────────────────────────────────────────

show_status() {
  echo "=== Paperscale v3 status ==="
  r2_count=$(ssh IDP "pgrep -c -f detect_script 2>/dev/null || echo 0")
  echo "R2 processes running: ${r2_count} / 10"
  echo ""
  echo "Per-run state (last log line):"
  ssh IDP '
for mode in hd hw id f9; do
  for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
    sb=/storage/ge96pug/Projects_SHA3_sandbox_paperscale_v3_${mode}_sigma${sig}
    plr="$sb/project_SHA3-32bit/pipeline_runner"
    sandbox_log="$plr/sandbox_paperscale_v3_${mode}_sigma${sig}.log"
    fix_log="$plr/paperscale_v3_${mode}_sigma${sig}.log"
    # prefer fix_log if it exists (created when ICS fix re-launched training/SASCA)
    if [ -f "$fix_log" ]; then
      log="$fix_log"
      log_label="[fix]"
    elif [ -f "$sandbox_log" ]; then
      log="$sandbox_log"
      log_label=""
    else
      echo "  not_started ${mode}_sigma${sig}"
      continue
    fi
    if grep -q "COMPLETE" "$log" 2>/dev/null; then complete=1
    elif [ -f "$sandbox_log" ] && grep -q "COMPLETE" "$sandbox_log" 2>/dev/null; then complete=1
    else complete=0; fi
    # fix_log = post-detection by definition; otherwise check sandbox log for [MOVE:DN]
    if [ -n "$log_label" ]; then
      movedn=1
    elif grep -q "\[MOVE:DN\]" "$log" 2>/dev/null; then movedn=1
    else movedn=0; fi
    last=$(tail -1 "$log" 2>/dev/null | cut -c1-80)
    if [ "$complete" -eq 1 ]; then
      echo "  DONE     ${mode}_sigma${sig}"
    elif [ "$movedn" -eq 1 ]; then
      echo "  training ${mode}_sigma${sig}${log_label}: $last"
    else
      echo "  detect   ${mode}_sigma${sig}: $last"
    fi
  done
done'
}

# ── ICS scan for σ≥3.0 runs ──────────────────────────────────────────────────

ics_scan() {
  echo "=== ICS boundary scan for paperscale v3 σ=3.0/3.5/4.0 ==="
  echo "Finding highest ICS level that passes for each run..."
  ssh IDP '
for mode in hd hw id f9; do
  for sig in 3p0 3p5 4p0; do
    sb=/storage/ge96pug/Projects_SHA3_sandbox_paperscale_v3_${mode}_sigma${sig}/project_SHA3-32bit
    if [ ! -d "$sb/0002_detection/Code_extract_ics" ]; then
      echo "  ${mode}_sigma${sig}: detection not complete yet"
      continue
    fi
    printf "  ${mode}_sigma${sig}: "
    found=0  # reset per run — avoids stale value suppressing "NO valid level found"
    for level in 090 080 070 060 050 040 030 020 010; do
      zipf="$sb/0002_detection/Code_extract_ics/ics_original_${level}.zip"
      if [ ! -f "$zipf" ]; then continue; fi
      result=$(python3 "$sb/pipeline_runner/check_ics_archive.py" \
        --ics-zip "$zipf" 2>&1)
      if echo "$result" | grep -q "^OK:"; then
        echo "max valid level = ${level}"
        found=1
        break
      fi
    done
    if [ "$found" -eq 0 ]; then echo "NO valid level found"; fi
  done
done'
  echo ""
  echo "Per-sigma standard (for all 4 modes to match, use f9 result):"
  echo "  Compare f9 and hd/hw/id per sigma. Use lowest value across all 4 modes."
  echo "  If paperscale allows higher level than midscale baseline, update env and apply:"
  echo "    sh launch_paperscale_v3.sh --fix-ics MODE SIGMA LEVEL"
}

# ── ICS level fix (after detection, before training) ─────────────────────────

fix_ics() {
  mode="$1"; sigma_s="$2"; level="$3"
  sb="/storage/ge96pug/Projects_SHA3_sandbox_paperscale_v3_${mode}_sigma${sigma_s}/project_SHA3-32bit"
  echo "Applying ICS fix: ${mode}_sigma${sigma_s} → level ${level}"
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  [DRY RUN] would update ${sb}/.env and apply --skip-detection"
    return
  fi
  # Store as plain integer (no leading zeros) — pack.sh pads with printf internally.
  # Leading zeros in shell env would be interpreted as octal by printf '%03d'.
  ssh IDP "sed -i \
    -e 's/SHA3_TRAINING_ICS_LEVEL=.*/SHA3_TRAINING_ICS_LEVEL=${level}/' \
    -e 's/SHA3_VALIDATION_TEMPLATE_TAG=.*/SHA3_VALIDATION_TEMPLATE_TAG=${level}/' \
    -e 's/SHA3_VALIDATION_ICS_TAG=.*/SHA3_VALIDATION_ICS_TAG=${level}/' \
    -e 's/SHA3_SASCA_TEMPLATE_TAG=.*/SHA3_SASCA_TEMPLATE_TAG=${level}/' \
    -e 's/SHA3_SASCA_ICS_TAG=.*/SHA3_SASCA_ICS_TAG=${level}/' \
    \"${sb}/.env\""
  # Also update the deployed envs/ copy so re-runs via --env-file read the corrected level.
  ssh IDP "sed -i \
    -e 's/SHA3_TRAINING_ICS_LEVEL=.*/SHA3_TRAINING_ICS_LEVEL=${level}/' \
    -e 's/SHA3_VALIDATION_TEMPLATE_TAG=.*/SHA3_VALIDATION_TEMPLATE_TAG=${level}/' \
    -e 's/SHA3_VALIDATION_ICS_TAG=.*/SHA3_VALIDATION_ICS_TAG=${level}/' \
    -e 's/SHA3_SASCA_TEMPLATE_TAG=.*/SHA3_SASCA_TEMPLATE_TAG=${level}/' \
    -e 's/SHA3_SASCA_ICS_TAG=.*/SHA3_SASCA_ICS_TAG=${level}/' \
    \"${sb}/pipeline_runner/envs/.env_paperscale_v3_${mode}_sigma${sigma_s}\" 2>/dev/null || true"
  # Also update local env file
  env_file="${ENVS_BASE}/sigma${sigma_s}/.env_paperscale_v3_${mode}_sigma${sigma_s}"
  sed -i \
    -e "s/SHA3_TRAINING_ICS_LEVEL=.*/SHA3_TRAINING_ICS_LEVEL=${level}/" \
    -e "s/SHA3_VALIDATION_TEMPLATE_TAG=.*/SHA3_VALIDATION_TEMPLATE_TAG=${level}/" \
    -e "s/SHA3_VALIDATION_ICS_TAG=.*/SHA3_VALIDATION_ICS_TAG=${level}/" \
    -e "s/SHA3_SASCA_TEMPLATE_TAG=.*/SHA3_SASCA_TEMPLATE_TAG=${level}/" \
    -e "s/SHA3_SASCA_ICS_TAG=.*/SHA3_SASCA_ICS_TAG=${level}/" \
    "${env_file}"
  # Append a redirect marker to the original sandbox log so the trail is visible there too.
  ssh IDP "echo '[FIX $(date +%Y-%m-%dT%H:%M)] ICS level corrected to ${level}. Re-run logs to: pipeline_runner/paperscale_v3_${mode}_sigma${sigma_s}.log' \
    >> \"${sb}/pipeline_runner/sandbox_paperscale_v3_${mode}_sigma${sigma_s}.log\" 2>/dev/null || true"
  echo "  Updated ${sb}/.env"
  echo "  Updated local ${env_file}"
  echo "  Next: re-launch training with --skip-detection (run_sandboxes.sh or run_full_pipeline.sh)"
}

# ── argument parsing ──────────────────────────────────────────────────────────

if [ "$#" -eq 0 ]; then print_help; fi

WAVE=""
FIX_MODE=""; FIX_SIGMA=""; FIX_LEVEL=""
ACTION="wave"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --wave)     WAVE="$2"; shift 2 ;;
    --status)   ACTION="status"; shift ;;
    --ics-scan) ACTION="ics_scan"; shift ;;
    --fix-ics)  ACTION="fix_ics"; FIX_MODE="$2"; FIX_SIGMA="$3"; FIX_LEVEL="$4"; shift 4 ;;
    --dry-run)  DRY_RUN=1; shift ;;
    --help|-h)  print_help ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

case "${ACTION}" in
  status)  show_status; exit 0 ;;
  ics_scan) ics_scan; exit 0 ;;
  fix_ics) fix_ics "${FIX_MODE}" "${FIX_SIGMA}" "${FIX_LEVEL}"; exit 0 ;;
esac

# ── wave launches ─────────────────────────────────────────────────────────────

case "${WAVE}" in
  # hd — HW+HD mode
  A1) echo "=== Wave A1: hd σ=0.1/0.5/1.0 (3 sims) ==="; launch_batch hd 0p1 0p5 1p0 ;;
  A2) echo "=== Wave A2: hd σ=1.5/2.0/2.5 (3 sims) ==="; launch_batch hd 1p5 2p0 2p5 ;;
  A3) echo "=== Wave A3: hd σ=3.0/3.5/4.0 (3 sims) ==="; launch_batch hd 3p0 3p5 4p0 ;;
  # hw — HW mode
  B1) echo "=== Wave B1: hw σ=0.1/0.5/1.0 (3 sims) ==="; launch_batch hw 0p1 0p5 1p0 ;;
  B2) echo "=== Wave B2: hw σ=1.5/2.0/2.5 (3 sims) ==="; launch_batch hw 1p5 2p0 2p5 ;;
  B3) echo "=== Wave B3: hw σ=3.0/3.5/4.0 (3 sims) ==="; launch_batch hw 3p0 3p5 4p0 ;;
  # id — identity mode
  C1) echo "=== Wave C1: id σ=0.1/0.5/1.0 (3 sims) ==="; launch_batch id 0p1 0p5 1p0 ;;
  C2) echo "=== Wave C2: id σ=1.5/2.0/2.5 (3 sims) ==="; launch_batch id 1p5 2p0 2p5 ;;
  C3) echo "=== Wave C3: id σ=3.0/3.5/4.0 (3 sims) ==="; launch_batch id 3p0 3p5 4p0 ;;
  # f9 — pure F9 mode
  D1) echo "=== Wave D1: f9 σ=0.1/0.5/1.0 (3 sims) ==="; launch_batch f9 0p1 0p5 1p0 ;;
  D2) echo "=== Wave D2: f9 σ=1.5/2.0/2.5 (3 sims) ==="; launch_batch f9 1p5 2p0 2p5 ;;
  D3) echo "=== Wave D3: f9 σ=3.0/3.5/4.0 (3 sims) ==="; launch_batch f9 3p0 3p5 4p0 ;;
  *) echo "Unknown wave: ${WAVE}. Use A1-A3, B1-B3, C1-C3, D1-D3." >&2; exit 1 ;;
esac

echo ""
echo "Quick status commands:"
echo "  sh ${SCRIPT_DIR}/launch_paperscale_v3.sh --status"
echo "  ssh IDP \"pgrep -c -f detect_script 2>/dev/null\""
echo "  ssh IDP \"pgrep -c -f KeccakSim 2>/dev/null\""
