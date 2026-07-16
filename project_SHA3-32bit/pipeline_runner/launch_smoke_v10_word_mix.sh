#!/usr/bin/env sh
# Launch smoke-v10 word-mix sigma sweep (36 runs: 4 pure modes x 9 sigmas).
#
# Word-mix-kernel clones of the smoke_v8 word-granularity baselines -- see
# envs/smoke_v10_word_mix/gen_envs.py for the exact per-var transform
# (SIM_MODE dropped for explicit SIM_*_SCALE vars, SIM_SCRIPT_OVERRIDE=
# KeccakSim_v4.py, SIM_EMISSION_KERNEL=word-mix, trace lengths back to
# byte-mode's 55296).
#
# Batched by SIGMA TIER, not by mode: all 4 modes at one noise level launch
# together, tiers processed ascending (lowest sigma first/prioritized) --
# unlike smoke_v8/v9's launchers, which batch by mode. Always run --wave
# sanity FIRST (sigma=1.0, all 4 modes) to catch config mistakes before the
# full 36-run sweep.
#
# Usage:
#   sh launch_smoke_v10_word_mix.sh --wave sanity   (sigma=1.0, 4 modes -- gate check)
#   sh launch_smoke_v10_word_mix.sh --wave all       (all 36 runs, ascending sigma tiers)
#   sh launch_smoke_v10_word_mix.sh --wave sigma0p1  (one sigma tier, 4 modes)
#   sh launch_smoke_v10_word_mix.sh --status
#   sh launch_smoke_v10_word_mix.sh --dry-run --wave all
#
# Manual ICS-gate fallback (normally handled unattended by
# auto_sweep_monitor.sh --family smoke_v10 -- use these only to intervene on
# a HALTed unit):
#   sh launch_smoke_v10_word_mix.sh --ics-scan MODE_SIGMA
#   sh launch_smoke_v10_word_mix.sh --fix-ics MODE_SIGMA LEVEL
#   sh launch_smoke_v10_word_mix.sh --resume MODE_SIGMA
#   (MODE_SIGMA example: hd_sigma1p0)

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ENVS_DIR="${SCRIPT_DIR}/envs/smoke_v10_word_mix"
DRY_RUN=0
SSH_TARGET=IDP
. "${SCRIPT_DIR}/ics_gate_lib.sh"

SIGMAS_ASC="0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0"
MODES="hw hd f9 id"

# ── helpers ──────────────────────────────────────────────────────────────────

print_help() {
  sed -n '2,/^set -eu/{ /^set -eu/d; s/^# \{0,1\}//; p }' "$0"
  exit 0
}

launch_sigma_tier() {
  sigma="$1"
  echo "=== smoke-v10 word-mix: sigma=${sigma} tier (4 modes) ==="
  tmp_dir="/tmp/smoke_v10_word_mix_sigma_$$_${sigma}"
  mkdir -p "${tmp_dir}"
  for mode in ${MODES}; do
    cp "${ENVS_DIR}/.env_smoke_v10_word_mix_${mode}_sigma${sigma}" "${tmp_dir}/"
  done
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  [DRY RUN] would launch 4 runs from ${tmp_dir}"
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
  echo "=== Smoke v10 word-mix status (sigma tiers ascending) ==="
  echo ""
  ssh IDP '
for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
  for mode in hw hd f9 id; do
    sb=/storage/ge96pug/Projects_SHA3_sandbox_smoke_v10_word_mix_${mode}_sigma${sig}
    plr="$sb/project_SHA3-32bit/pipeline_runner"
    log="$plr/sandbox_smoke_v10_word_mix_${mode}_sigma${sig}.log"
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
  printf "smoke_v10_word_mix_%s" "$1"
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

# ── wave launches (sigma-major: ascending tiers, 4 modes each) ──────────────

case "${WAVE}" in
  sanity)
    launch_sigma_tier 1p0
    ;;
  all)
    echo "=== Smoke v10 word-mix: all 36 runs, ascending sigma tiers ==="
    for sig in ${SIGMAS_ASC}; do
      launch_sigma_tier "${sig}"
    done
    ;;
  sigma*)
    launch_sigma_tier "${WAVE#sigma}"
    ;;
  *)
    echo "Unknown wave: ${WAVE}. Use: sanity, all, sigma<X> (e.g. sigma0p1)." >&2
    exit 1
    ;;
esac

echo ""
echo "Monitor: sh ${SCRIPT_DIR}/launch_smoke_v10_word_mix.sh --status"
