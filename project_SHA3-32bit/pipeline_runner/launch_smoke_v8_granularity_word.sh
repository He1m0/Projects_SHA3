#!/usr/bin/env sh
# Launch smoke-v8 granularity sigma sweep (36 runs: 4 pure modes x 9 sigmas).
#
# Word-granularity clones of the current canonical byte-mode pure-mode
# baselines: smoke_v5 (hw), smoke_v7_hd_pure (hd), smoke_v6 (f9, id). See
# envs/smoke_v8_granularity_word_sigma_sweep/gen_envs.py for the exact
# per-var substitutions (SIM_GRANULARITY=word, trace lengths 55296->13824).
#
# Purpose: sanity check whether simulator granularity (byte vs. word) changes
# detection/SASCA outcomes -- never tested before. Always run --wave sanity
# FIRST to catch config mistakes before committing to the full 36-run sweep.
#
# Usage:
#   sh launch_smoke_v8_granularity_word.sh --wave sanity  (hw+hd+f9+id sigma=1.0 -- 4 runs, gate check)
#   sh launch_smoke_v8_granularity_word.sh --wave all      (all 36 runs)
#   sh launch_smoke_v8_granularity_word.sh --wave hw       (all 9 hw runs)
#   sh launch_smoke_v8_granularity_word.sh --wave hd       (all 9 hd runs)
#   sh launch_smoke_v8_granularity_word.sh --wave f9       (all 9 f9 runs)
#   sh launch_smoke_v8_granularity_word.sh --wave id       (all 9 id runs)
#   sh launch_smoke_v8_granularity_word.sh --status
#   sh launch_smoke_v8_granularity_word.sh --dry-run --wave all
#
# Manual ICS-gate fallback (normally handled unattended by
# auto_sweep_monitor.sh -- use these only to intervene on a HALTed unit):
#   sh launch_smoke_v8_granularity_word.sh --ics-scan MODE_SIGMA
#   sh launch_smoke_v8_granularity_word.sh --fix-ics MODE_SIGMA LEVEL
#   sh launch_smoke_v8_granularity_word.sh --resume MODE_SIGMA
#   (MODE_SIGMA example: hd_sigma1p0)

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ENVS_DIR="${SCRIPT_DIR}/envs/smoke_v8_granularity_word_sigma_sweep"
DRY_RUN=0
SSH_TARGET=IDP
. "${SCRIPT_DIR}/ics_gate_lib.sh"

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
  tmp_dir="/tmp/smoke_v8_granularity_word_single_$$_${name}"
  mkdir -p "${tmp_dir}"
  cp "${env_file}" "${tmp_dir}/"
  sh "${SCRIPT_DIR}/run_sandboxes.sh" \
    --envs-dir "${tmp_dir}" \
    --ssh IDP
  rm -rf "${tmp_dir}"
}

launch_mode() {
  mode="$1"
  echo "=== smoke-v8 granularity-word: all ${mode} runs (9 sigmas) ==="
  tmp_dir="/tmp/smoke_v8_granularity_word_mode_$$_${mode}"
  mkdir -p "${tmp_dir}"
  for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
    cp "${ENVS_DIR}/.env_smoke_v8_granularity_word_${mode}_sigma${sig}" "${tmp_dir}/"
  done
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  [DRY RUN] would launch 9 runs from ${tmp_dir}"
    ls "${tmp_dir}"
    rm -rf "${tmp_dir}"
    return
  fi
  sh "${SCRIPT_DIR}/run_sandboxes.sh" \
    --envs-dir "${tmp_dir}" \
    --ssh IDP
  rm -rf "${tmp_dir}"
}

# ── status ────────────────────────────────────────────────────────────────────

show_status() {
  echo "=== Smoke v8 granularity-word status ==="
  echo ""
  ssh IDP '
for mode in hw hd f9 id; do
  for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
    sb=/storage/ge96pug/Projects_SHA3_sandbox_smoke_v8_granularity_word_${mode}_sigma${sig}
    plr="$sb/project_SHA3-32bit/pipeline_runner"
    log="$plr/sandbox_smoke_v8_granularity_word_${mode}_sigma${sig}.log"
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

# ── manual ICS-gate fallback (delegates to ics_gate_lib.sh) ──────────────────

label_from_mode_sigma() {
  printf "smoke_v8_granularity_word_%s" "$1"
}

env_file_from_mode_sigma() {
  printf "%s/.env_%s" "${ENVS_DIR}" "$(label_from_mode_sigma "$1")"
}

# ── argument parsing ──────────────────────────────────────────────────────────

if [ "$#" -eq 0 ]; then print_help; fi

WAVE=""
ACTION="wave"
ICS_SCAN_ARG=""; FIX_ARG=""; FIX_LEVEL=""; RESUME_ARG=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --wave)     WAVE="$2"; shift 2 ;;
    --status)   ACTION="status"; shift ;;
    --ics-scan) ACTION="ics_scan"; ICS_SCAN_ARG="$2"; shift 2 ;;
    --fix-ics)  ACTION="fix_ics"; FIX_ARG="$2"; FIX_LEVEL="$3"; shift 3 ;;
    --resume)   ACTION="resume"; RESUME_ARG="$2"; shift 2 ;;
    --dry-run)  DRY_RUN=1; shift ;;
    --help|-h)  print_help ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

case "${ACTION}" in
  status)   show_status; exit 0 ;;
  ics_scan) ics_scan_label "$(label_from_mode_sigma "${ICS_SCAN_ARG}")"; exit 0 ;;
  fix_ics)
    fix_ics_label "$(label_from_mode_sigma "${FIX_ARG}")" "$(env_file_from_mode_sigma "${FIX_ARG}")" "${FIX_LEVEL}"
    echo "  Updated sandbox and local env file. Resume with --resume ${FIX_ARG}."
    exit 0
    ;;
  resume)
    resume_label "$(label_from_mode_sigma "${RESUME_ARG}")"
    exit 0
    ;;
esac

# ── wave launches ─────────────────────────────────────────────────────────────

case "${WAVE}" in
  sanity)
    echo "=== Smoke v8 granularity-word sanity check: hw+hd+f9+id sigma=1.0 (4 runs) ==="
    echo "Gate: verify 0001_reference doesn't crash, each mode's ICS level is non-empty, SASCA completes."
    launch_single "${ENVS_DIR}/.env_smoke_v8_granularity_word_hw_sigma1p0"
    launch_single "${ENVS_DIR}/.env_smoke_v8_granularity_word_hd_sigma1p0"
    launch_single "${ENVS_DIR}/.env_smoke_v8_granularity_word_f9_sigma1p0"
    launch_single "${ENVS_DIR}/.env_smoke_v8_granularity_word_id_sigma1p0"
    ;;
  all)
    echo "=== Smoke v8 granularity-word: all 36 runs ==="
    launch_mode hw
    launch_mode hd
    launch_mode f9
    launch_mode id
    ;;
  hw) launch_mode hw ;;
  hd) launch_mode hd ;;
  f9) launch_mode f9 ;;
  id) launch_mode id ;;
  *)
    echo "Unknown wave: ${WAVE}. Use: sanity, all, hw, hd, f9, id." >&2
    exit 1
    ;;
esac

echo ""
echo "Monitor: sh ${SCRIPT_DIR}/launch_smoke_v8_granularity_word.sh --status"
