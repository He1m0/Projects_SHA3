#!/usr/bin/env sh
# Launch paperscale-v6 pure-HD sigma sweep (9 runs: mode=hd x 9 sigmas).
#
# KeccakSim_v3, mode=hd, hd_scale=1.0. Same paperscale-scale trace counts /
# SASCA params as paperscale_v5 (100 det, 400 training, 40 val, 1000 SASCA,
# iter=200, 201 rate points, 8-bit step) for direct comparability.
#
# Two-phase approach (per RUN_LOG_hd_promotion.md Part 8 -- same pattern
# already used for smoke_v7_hd_pure): detection-only first to pin the
# per-sigma ICS level (starting guess: 40, from smoke_v7 -- do NOT assume it
# holds at paperscale scale, 100 detection sets vs smoke's 10), THEN training
# onward once confirmed. This avoids re-running paperscale's ~64h/run R2
# stage if the ICS level turns out wrong.
#
# SIMULATION CAP: max 3 concurrent simulations (disk-write bandwidth limit on IDP).
# R2 RAM CAP:     max 10 concurrent R2 processes (~33 GB commit/process, CommitLimit=511 GB).
# NOTE: paperscale_v5's own runs share this same IDP host -- check current R2/KeccakSim
# counts before every wave, don't just trust the caps below in isolation.
#
# Wave structure (sim+deploy only, --skip-chain -- cheap, no training/SASCA):
#   Wave C1 : sigma 0.1/0.5/1.0
#   Wave C2 : sigma 1.5/2.0/2.5
#   Wave C3 : sigma 3.0/3.5/4.0
#
# Recommended flow:
#   1. sh launch_paperscale_v6.sh --wave C1   (sim+deploy only, 3 sandboxes)
#   2. sh launch_paperscale_v6.sh --wave C2
#   3. sh launch_paperscale_v6.sh --wave C3
#   4. sh launch_paperscale_v6.sh --detect-only   (launches 0001+0002 chains for all 9,
#        staggered under R2_CAP -- run after all 9 sandboxes have traces deployed)
#   5. sh launch_paperscale_v6.sh --ics-scan      (once all 9 detections complete)
#   6. sh launch_paperscale_v6.sh --fix-ics SIGMA LEVEL   (if a sigma's confirmed level != 40)
#   7. sh launch_paperscale_v6.sh --resume SIGMA  (training onward, one sigma at a time,
#        only after the Phase-3 resource-contention gate is cleared -- see RUN_LOG_hd_promotion.md)
#
# Usage:
#   sh launch_paperscale_v6.sh --wave WAVE [--dry-run]
#   sh launch_paperscale_v6.sh --status
#   sh launch_paperscale_v6.sh --detect-only [--dry-run]
#   sh launch_paperscale_v6.sh --ics-scan
#   sh launch_paperscale_v6.sh --fix-ics SIGMA LEVEL
#   sh launch_paperscale_v6.sh --resume SIGMA [--dry-run]
#
# WAVE values: C1 C2 C3

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ENVS_BASE="${SCRIPT_DIR}/envs/paperscale_v6_hd_pure_sigma_sweep"
DRY_RUN=0

# ── helpers ──────────────────────────────────────────────────────────────────

print_help() {
  sed -n '2,/^set -eu/{ /^set -eu/d; s/^# \{0,1\}//; p }' "$0"
  exit 0
}

label_for() {
  # paperscale_v6_hd_pure_sigma<X>
  printf "paperscale_v6_hd_pure_sigma%s" "$1"
}

launch_single() {
  env_file="$1"
  name=$(basename "${env_file}" | sed 's/^\.env_//')
  echo "  Launching (sim+deploy only): ${name}"
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "    [DRY RUN] run_sandboxes.sh --ssh IDP ${env_file} -- --skip-chain"
    return
  fi
  tmp_dir="/tmp/paperscale_v6_single_$$_${name}"
  mkdir -p "${tmp_dir}"
  cp "${env_file}" "${tmp_dir}/"
  sh "${SCRIPT_DIR}/run_sandboxes.sh" \
    --envs-dir "${tmp_dir}" \
    --ssh IDP \
    -- --skip-chain
  rm -rf "${tmp_dir}"
}

check_r2_warn_only() {
  count=$(ssh IDP "pgrep -c -f detect_script 2>/dev/null || echo 0")
  if [ "${count}" -gt 6 ]; then
    echo "  R2 count=${count} (warning: approaching cap 10, shared with paperscale_v5). Wait until <=6 before next wave."
  else
    echo "  R2 count=${count} -- OK to launch."
  fi
}

launch_batch() {
  sigma1="$1"; sigma2="$2"; sigma3="$3"
  echo "  Batch: hd sigma=${sigma1}/${sigma2}/${sigma3}"
  check_r2_warn_only
  launch_single "${ENVS_BASE}/sigma${sigma1}/.env_paperscale_v6_hd_pure_sigma${sigma1}"
  launch_single "${ENVS_BASE}/sigma${sigma2}/.env_paperscale_v6_hd_pure_sigma${sigma2}"
  launch_single "${ENVS_BASE}/sigma${sigma3}/.env_paperscale_v6_hd_pure_sigma${sigma3}"
}

# ── status ────────────────────────────────────────────────────────────────────

show_status() {
  echo "=== Paperscale v6 (pure HD) status ==="
  r2_count=$(ssh IDP "pgrep -c -f detect_script 2>/dev/null || echo 0")
  echo "R2 processes running (shared with paperscale_v5): ${r2_count} / 10"
  echo ""
  echo "Per-run state:"
  ssh IDP '
for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
  label="paperscale_v6_hd_pure_sigma${sig}"
  sb=/storage/ge96pug/Projects_SHA3_sandbox_${label}
  plr="$sb/project_SHA3-32bit/pipeline_runner"
  if [ ! -d "$sb" ]; then
    echo "  not_started ${label}"
    continue
  fi
  detect_log="$plr/detect_only_sigma${sig}.log"
  full_log="$plr/${label}.log"
  if [ -f "$full_log" ] && grep -q "COMPLETE: run_full_pipeline finished" "$full_log" 2>/dev/null; then
    echo "  DONE        ${label}"
  elif [ -f "$detect_log" ] && grep -q "COMPLETE: 0002 detection chain finished" "$detect_log" 2>/dev/null; then
    echo "  detect_done ${label} (awaiting ICS confirm + resume)"
  elif [ -f "$detect_log" ]; then
    last=$(tail -1 "$detect_log" 2>/dev/null | cut -c1-70)
    echo "  detecting   ${label}: $last"
  elif [ -d "$sb/project_SHA3-32bit/0002_detection/Raw" ] || [ -d "$sb/project_SHA3-32bit/0001_reference/Raw" ]; then
    echo "  traces_only ${label} (sim+deploy done, detection not started)"
  else
    echo "  deploying   ${label}"
  fi
done'
}

# ── detect-only: run_0001_chain.sh && run_0002_chain.sh per sandbox ─────────
# NOTE: these chain scripts do NOT activate the sandbox .venv the way
# run_full_pipeline.sh does -- must prepend .venv/bin to PATH explicitly
# (this bit smoke_v7's Phase 2, see RUN_LOG_hd_promotion.md).

detect_only() {
  echo "=== Launching detection-only (0001+0002 chains) for all 9 paperscale_v6 sigmas ==="
  for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
    label=$(label_for "${sig}")
    sb="/storage/ge96pug/Projects_SHA3_sandbox_${label}"
    plr="${sb}/project_SHA3-32bit/pipeline_runner"
    log="${plr}/detect_only_sigma${sig}.log"
    tmux_label="sandbox_${label}_detect"
    cmd="cd ${plr} && PATH=${sb}/.venv/bin:\$PATH sh run_0001_chain.sh && PATH=${sb}/.venv/bin:\$PATH sh run_0002_chain.sh"
    if [ "${DRY_RUN}" -eq 1 ]; then
      echo "  [DRY RUN] tmux new-session -d -s ${tmux_label} \"${cmd} > ${log} 2>&1\""
      continue
    fi
    echo "  Launching detect-only: ${label}"
    ssh IDP "tmux new-session -d -s '${tmux_label}' \"${cmd} > '${log}' 2>&1\""
  done
  echo "Check progress with: sh $0 --status"
}

# ── ICS scan across all 9 sigmas ─────────────────────────────────────────────

ics_scan() {
  echo "=== ICS boundary scan for paperscale v6 (pure HD), all 9 sigmas ==="
  echo "Finding highest ICS level that passes for each sigma (starting guess: 40, from smoke_v7)..."
  ssh IDP '
for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
  sb=/storage/ge96pug/Projects_SHA3_sandbox_paperscale_v6_hd_pure_sigma${sig}/project_SHA3-32bit
  if [ ! -d "$sb/0002_detection/Code_extract_ics" ]; then
    echo "  sigma${sig}: detection not complete yet"
    continue
  fi
  printf "  sigma${sig}: "
  found=0
  for level in 090 080 070 060 050 040 030 020 010; do
    zipf="$sb/0002_detection/Code_extract_ics/ics_original_${level}.zip"
    if [ ! -f "$zipf" ]; then continue; fi
    result=$(python3 "$sb/pipeline_runner/check_ics_archive.py" --ics-zip "$zipf" 2>&1)
    if echo "$result" | grep -q "^OK:"; then
      echo "max valid level = ${level}"
      found=1
      break
    fi
  done
  if [ "$found" -eq 0 ]; then echo "NO valid level found"; fi
done'
  echo ""
  echo "smoke_v7 found level 40 for every sigma (structural D-word gap, not noise-driven)."
  echo "Compare against that -- a deviation here is itself a finding worth logging."
}

# ── ICS level fix (after detection, before training) ─────────────────────────

fix_ics() {
  sigma_s="$1"; level="$2"
  label=$(label_for "${sigma_s}")
  sb="/storage/ge96pug/Projects_SHA3_sandbox_${label}/project_SHA3-32bit"
  env_file="${ENVS_BASE}/sigma${sigma_s}/.env_paperscale_v6_hd_pure_sigma${sigma_s}"
  echo "Applying ICS fix: ${label} -> level ${level}"
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  [DRY RUN] would update ${sb}/.env and local ${env_file}"
    return
  fi
  for f in "${sb}/.env" "${sb}/pipeline_runner/envs/.env_paperscale_v6_hd_pure_sigma${sigma_s}"; do
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
  echo "  Updated sandbox and local env file. Resume with --resume ${sigma_s}."
}

# ── resume: training onward (Phase 3, gated) ─────────────────────────────────

resume() {
  sigma_s="$1"
  label=$(label_for "${sigma_s}")
  sb="/storage/ge96pug/Projects_SHA3_sandbox_${label}"
  plr="${sb}/project_SHA3-32bit/pipeline_runner"
  tmux_label="sandbox_${label}"
  log="${plr}/${label}.log"
  cmd="cd ${plr} && sh run_full_pipeline.sh --skip-detection --env-file ../.env"
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  [DRY RUN] tmux new-session -d -s ${tmux_label} \"${cmd} > ${log} 2>&1\""
    return
  fi
  echo "Resuming training onward for ${label}"
  echo "Reminder: confirm the Phase-3 resource-contention gate is actually clear (check"
  echo "paperscale_v5 R2/KeccakSim load) before doing this for all 9 sigmas at once."
  ssh IDP "tmux new-session -d -s '${tmux_label}' \"${cmd} > '${log}' 2>&1\""
}

# ── argument parsing ──────────────────────────────────────────────────────────

if [ "$#" -eq 0 ]; then print_help; fi

WAVE=""
FIX_SIGMA=""; FIX_LEVEL=""
RESUME_SIGMA=""
ACTION="wave"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --wave)        WAVE="$2"; shift 2 ;;
    --status)      ACTION="status"; shift ;;
    --detect-only) ACTION="detect_only"; shift ;;
    --ics-scan)    ACTION="ics_scan"; shift ;;
    --fix-ics)     ACTION="fix_ics"; FIX_SIGMA="$2"; FIX_LEVEL="$3"; shift 3 ;;
    --resume)      ACTION="resume"; RESUME_SIGMA="$2"; shift 2 ;;
    --dry-run)     DRY_RUN=1; shift ;;
    --help|-h)     print_help ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

case "${ACTION}" in
  status)      show_status; exit 0 ;;
  detect_only) detect_only; exit 0 ;;
  ics_scan)    ics_scan; exit 0 ;;
  fix_ics)     fix_ics "${FIX_SIGMA}" "${FIX_LEVEL}"; exit 0 ;;
  resume)      resume "${RESUME_SIGMA}"; exit 0 ;;
esac

case "${WAVE}" in
  C1) echo "=== Wave C1: hd sigma=0.1/0.5/1.0 (3 sims) ==="; launch_batch 0p1 0p5 1p0 ;;
  C2) echo "=== Wave C2: hd sigma=1.5/2.0/2.5 (3 sims) ==="; launch_batch 1p5 2p0 2p5 ;;
  C3) echo "=== Wave C3: hd sigma=3.0/3.5/4.0 (3 sims) ==="; launch_batch 3p0 3p5 4p0 ;;
  *) echo "Unknown wave: ${WAVE}. Use C1-C3." >&2; exit 1 ;;
esac

echo ""
echo "Quick status commands:"
echo "  sh ${SCRIPT_DIR}/launch_paperscale_v6.sh --status"
echo "  ssh IDP \"pgrep -c -f detect_script 2>/dev/null\""
echo "  ssh IDP \"pgrep -c -f KeccakSim 2>/dev/null\""
