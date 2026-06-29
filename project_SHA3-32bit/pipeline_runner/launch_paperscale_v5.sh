#!/usr/bin/env sh
# Launch paperscale-v5 sigma sweep (18 runs: 9 sigmas × 2 SNR-equalized modes).
#
# SNR-equalized: f9_scale=√3≈1.7321, id_scale≈0.01913 — both match HW SNR_var=2/σ².
# ICS level 90 used uniformly for all sigmas (valid because SNR is now matched to HW).
# SASCA: 200 iterations, 201 rate points, 8-bit step — matches paperscale-v4 (HW/HD).
#
# SIMULATION CAP: max 3 concurrent simulations (disk-write bandwidth limit on IDP).
# R2 RAM CAP:     max 10 concurrent R2 processes (~33 GB commit/process, CommitLimit=511 GB).
#
# Wave structure (each wave = 3 concurrent simulations → auto-transition to R2):
#   Wave A1/A2/A3 : f9 mode, sigma 0p1-1p0 / 1p5-2p5 / 3p0-4p0
#   Wave B1/B2/B3 : id mode, sigma 0p1-1p0 / 1p5-2p5 / 3p0-4p0
#
# Recommended launch order (low sigma first for priority results):
#   1. sh launch_smoke_v6.sh --wave sanity    (sanity check before committing paperscale)
#   2. sh launch_paperscale_v5.sh --wave A1   (f9 σ=0.1/0.5/1.0)
#   3. R2 count ≤ 6 → sh launch_paperscale_v5.sh --wave B1   (id σ=0.1/0.5/1.0)
#   4. R2 count ≤ 6 → sh launch_paperscale_v5.sh --wave A2
#   5. R2 count ≤ 6 → sh launch_paperscale_v5.sh --wave B2
#   6. R2 count ≤ 6 → sh launch_paperscale_v5.sh --wave A3
#   7. R2 count ≤ 6 → sh launch_paperscale_v5.sh --wave B3
#
# After detection for any run: check ICS level 90 passes (should, given SNR matching).
# If not: use --fix-ics MODE SIGMA LEVEL (same as paperscale-v3 fix mechanism).
#
# Usage:
#   sh launch_paperscale_v5.sh --wave WAVE [--dry-run]
#   sh launch_paperscale_v5.sh --status
#   sh launch_paperscale_v5.sh --ics-scan   (run after σ≥3.0 runs complete detection)
#   sh launch_paperscale_v5.sh --fix-ics MODE SIGMA LEVEL
#
# WAVE values: A1 A2 A3 B1 B2 B3

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ENVS_BASE="${SCRIPT_DIR}/envs/paperscale_v5_sigma_sweep"
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
  tmp_dir="/tmp/paperscale_v5_single_$$_${name}"
  mkdir -p "${tmp_dir}"
  cp "${env_file}" "${tmp_dir}/"
  sh "${SCRIPT_DIR}/run_sandboxes.sh" \
    --envs-dir "${tmp_dir}" \
    --ssh IDP
  rm -rf "${tmp_dir}"
}

check_r2_count() {
  count=$(ssh IDP "pgrep -c -f detect_script 2>/dev/null || echo 0")
  echo "Current R2 processes on IDP: ${count} (cap: 10)"
  if [ "${count}" -gt 10 ]; then
    echo "WARNING: ${count} > 10. Do not launch more waves until count drops."
    return 1
  fi
  return 0
}

check_r2_warn_only() {
  count=$(ssh IDP "pgrep -c -f detect_script 2>/dev/null || echo 0")
  if [ "${count}" -gt 6 ]; then
    echo "  R2 count=${count} (warning: approaching cap 10). Wait until ≤6 before next wave."
  else
    echo "  R2 count=${count} — OK to launch."
  fi
}

launch_batch() {
  mode="$1"; sigma1="$2"; sigma2="$3"; sigma3="$4"
  echo "  Batch: ${mode} σ=${sigma1}/${sigma2}/${sigma3}"
  check_r2_warn_only
  launch_single "${ENVS_BASE}/sigma${sigma1}/.env_paperscale_v5_${mode}_sigma${sigma1}"
  launch_single "${ENVS_BASE}/sigma${sigma2}/.env_paperscale_v5_${mode}_sigma${sigma2}"
  launch_single "${ENVS_BASE}/sigma${sigma3}/.env_paperscale_v5_${mode}_sigma${sigma3}"
}

# ── status ────────────────────────────────────────────────────────────────────

show_status() {
  echo "=== Paperscale v5 status ==="
  r2_count=$(ssh IDP "pgrep -c -f detect_script 2>/dev/null || echo 0")
  echo "R2 processes running: ${r2_count} / 10"
  echo ""
  echo "Per-run state (last log line):"
  ssh IDP '
for mode in f9 id; do
  for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
    sb=/storage/ge96pug/Projects_SHA3_sandbox_paperscale_v5_${mode}_sigma${sig}
    plr="$sb/project_SHA3-32bit/pipeline_runner"
    log="$plr/sandbox_paperscale_v5_${mode}_sigma${sig}.log"
    if [ ! -f "$log" ]; then
      echo "  not_started ${mode}_sigma${sig}"
      continue
    fi
    if grep -q "COMPLETE" "$log" 2>/dev/null; then
      echo "  DONE     ${mode}_sigma${sig}"
    elif grep -q "\[MOVE:DN\]" "$log" 2>/dev/null; then
      last=$(tail -1 "$log" 2>/dev/null | cut -c1-80)
      echo "  training ${mode}_sigma${sig}: $last"
    else
      last=$(tail -1 "$log" 2>/dev/null | cut -c1-80)
      echo "  detect   ${mode}_sigma${sig}: $last"
    fi
  done
done'
}

# ── ICS scan for σ≥3.0 runs ──────────────────────────────────────────────────

ics_scan() {
  echo "=== ICS boundary scan for paperscale v5 σ=3.0/3.5/4.0 ==="
  echo "Finding highest ICS level that passes for each run..."
  ssh IDP '
for mode in f9 id; do
  for sig in 3p0 3p5 4p0; do
    sb=/storage/ge96pug/Projects_SHA3_sandbox_paperscale_v5_${mode}_sigma${sig}/project_SHA3-32bit
    if [ ! -d "$sb/0002_detection/Code_extract_ics" ]; then
      echo "  ${mode}_sigma${sig}: detection not complete yet"
      continue
    fi
    printf "  ${mode}_sigma${sig}: "
    found=0
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
  echo "Expected: all runs show max valid level = 090 (SNR-matched to HW)."
  echo "If any run shows < 090, use --fix-ics MODE SIGMA LEVEL to correct and re-run training."
}

# ── ICS level fix (after detection, before training) ─────────────────────────

fix_ics() {
  mode="$1"; sigma_s="$2"; level="$3"
  sb="/storage/ge96pug/Projects_SHA3_sandbox_paperscale_v5_${mode}_sigma${sigma_s}/project_SHA3-32bit"
  env_file="${ENVS_BASE}/sigma${sigma_s}/.env_paperscale_v5_${mode}_sigma${sigma_s}"
  echo "Applying ICS fix: ${mode}_sigma${sigma_s} → level ${level}"
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  [DRY RUN] would update ${sb}/.env and local ${env_file}"
    return
  fi
  for f in "${sb}/.env" "${sb}/pipeline_runner/envs/.env_paperscale_v5_${mode}_sigma${sigma_s}"; do
    ssh IDP "[ -f $(printf "'%s'" "$f") ] && sed -i \
      -e 's/SHA3_TRAINING_ICS_LEVEL=.*/SHA3_TRAINING_ICS_LEVEL=${level}/' \
      -e 's/SHA3_VALIDATION_TEMPLATE_TAG=.*/SHA3_VALIDATION_TEMPLATE_TAG=${level}/' \
      -e 's/SHA3_VALIDATION_ICS_TAG=.*/SHA3_VALIDATION_ICS_TAG=${level}/' \
      -e 's/SHA3_SASCA_TEMPLATE_TAG=.*/SHA3_SASCA_TEMPLATE_TAG=${level}/' \
      -e 's/SHA3_SASCA_ICS_TAG=.*/SHA3_SASCA_ICS_TAG=${level}/' \
      $(printf "'%s'" "$f") || true"
  done
  sed -i \
    -e "s/SHA3_TRAINING_ICS_LEVEL=.*/SHA3_TRAINING_ICS_LEVEL=${level}/" \
    -e "s/SHA3_VALIDATION_TEMPLATE_TAG=.*/SHA3_VALIDATION_TEMPLATE_TAG=${level}/" \
    -e "s/SHA3_VALIDATION_ICS_TAG=.*/SHA3_VALIDATION_ICS_TAG=${level}/" \
    -e "s/SHA3_SASCA_TEMPLATE_TAG=.*/SHA3_SASCA_TEMPLATE_TAG=${level}/" \
    -e "s/SHA3_SASCA_ICS_TAG=.*/SHA3_SASCA_ICS_TAG=${level}/" \
    "${env_file}"
  echo "  Updated sandbox and local env file. Re-run training with --skip-detection."
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
  status)   show_status; exit 0 ;;
  ics_scan) ics_scan; exit 0 ;;
  fix_ics)  fix_ics "${FIX_MODE}" "${FIX_SIGMA}" "${FIX_LEVEL}"; exit 0 ;;
esac

# ── wave launches ─────────────────────────────────────────────────────────────

case "${WAVE}" in
  # f9 — SNR-equalized F9 mode
  A1) echo "=== Wave A1: f9 σ=0.1/0.5/1.0 (3 sims) ==="; launch_batch f9 0p1 0p5 1p0 ;;
  A2) echo "=== Wave A2: f9 σ=1.5/2.0/2.5 (3 sims) ==="; launch_batch f9 1p5 2p0 2p5 ;;
  A3) echo "=== Wave A3: f9 σ=3.0/3.5/4.0 (3 sims) ==="; launch_batch f9 3p0 3p5 4p0 ;;
  # id — SNR-equalized identity mode
  B1) echo "=== Wave B1: id σ=0.1/0.5/1.0 (3 sims) ==="; launch_batch id 0p1 0p5 1p0 ;;
  B2) echo "=== Wave B2: id σ=1.5/2.0/2.5 (3 sims) ==="; launch_batch id 1p5 2p0 2p5 ;;
  B3) echo "=== Wave B3: id σ=3.0/3.5/4.0 (3 sims) ==="; launch_batch id 3p0 3p5 4p0 ;;
  *) echo "Unknown wave: ${WAVE}. Use A1-A3, B1-B3." >&2; exit 1 ;;
esac

echo ""
echo "Quick status commands:"
echo "  sh ${SCRIPT_DIR}/launch_paperscale_v5.sh --status"
echo "  ssh IDP \"pgrep -c -f detect_script 2>/dev/null\""
echo "  ssh IDP \"pgrep -c -f KeccakSim 2>/dev/null\""
