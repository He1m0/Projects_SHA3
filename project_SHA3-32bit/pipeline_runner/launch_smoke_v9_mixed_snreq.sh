#!/usr/bin/env sh
# Launch smoke-v9 mixed-mode total-variance-equalized diagnostics (20 runs:
# hwhd x9 + f9hw x9 + f9hd x1 + f9hwhd x1).
#
# Supersedes the un-equalized mixed-mode combos (smoke_v5 "hd" HW+HD combined,
# smoke_v6_f9mixed_* F9+HD/F9+HW/F9+HW+HD): those summed each component at its
# own single-mode-equalized scale, so total signal variance scaled with the
# number of active components (2.5/4.0/4.0/6.0) instead of holding at the
# fixed reference (2.0) shared by every single-mode baseline. This sweep
# equal-splits each config's variance budget across its active components so
# every row totals SNR_var=2.0/sigma^2. See
# ~/.claude/plans/prepare-a-plan-run-log-for-jiggly-grove.md and
# RUN_LOG_mixed_snreq.md for the full derivation and status.
#
# ICS level: env files start at 90 (matching the pre-existing mixed-mode
# convention) but this is NOT assumed to hold for the HD-containing configs
# (hwhd, f9hd, f9hwhd) -- always run --wave sanity first and check ICS levels
# via check_ics_archive.py before committing the batched waves.
#
# Usage:
#   sh launch_smoke_v9_mixed_snreq.sh --wave sanity   (4 runs, sigma=1.0 each config — gate check)
#   sh launch_smoke_v9_mixed_snreq.sh --wave all       (all 20 runs)
#   sh launch_smoke_v9_mixed_snreq.sh --wave hwhd      (9 runs, HW+HD combined sigma sweep)
#   sh launch_smoke_v9_mixed_snreq.sh --wave f9hw      (9 runs, F9+HW sigma sweep)
#   sh launch_smoke_v9_mixed_snreq.sh --wave f9hd      (1 run, sigma=1.0 only; already in sanity)
#   sh launch_smoke_v9_mixed_snreq.sh --wave f9hwhd    (1 run, sigma=1.0 only; already in sanity)
#   sh launch_smoke_v9_mixed_snreq.sh --status
#   sh launch_smoke_v9_mixed_snreq.sh --dry-run --wave sanity
#
# Manual ICS-gate fallback (normally handled unattended by
# auto_sweep_monitor.sh -- use these only to intervene on a HALTed unit):
#   sh launch_smoke_v9_mixed_snreq.sh --ics-scan CFG_SIGMA
#   sh launch_smoke_v9_mixed_snreq.sh --fix-ics CFG_SIGMA LEVEL
#   sh launch_smoke_v9_mixed_snreq.sh --resume CFG_SIGMA
#   (CFG_SIGMA example: hwhd_sigma1p0)

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ENVS_DIR="${SCRIPT_DIR}/envs/smoke_v9_mixed_snreq"
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
  tmp_dir="/tmp/smoke_v9_mixed_snreq_single_$$_${name}"
  mkdir -p "${tmp_dir}"
  cp "${env_file}" "${tmp_dir}/"
  sh "${SCRIPT_DIR}/run_sandboxes.sh" \
    --envs-dir "${tmp_dir}" \
    --ssh IDP
  rm -rf "${tmp_dir}"
}

launch_mode() {
  cfg="$1"
  echo "=== smoke-v9 mixed-snreq: all ${cfg} runs (9 sigmas) ==="
  tmp_dir="/tmp/smoke_v9_mixed_snreq_mode_$$_${cfg}"
  mkdir -p "${tmp_dir}"
  for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
    cp "${ENVS_DIR}/.env_smoke_v9_mixed_snreq_${cfg}_sigma${sig}" "${tmp_dir}/"
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
  echo "=== Smoke v9 mixed-snreq status ==="
  echo ""
  ssh IDP '
for cfg_sigmas in "hwhd:0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0" "f9hw:0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0" "f9hd:1p0" "f9hwhd:1p0"; do
  cfg=$(echo "$cfg_sigmas" | cut -d: -f1)
  sigmas=$(echo "$cfg_sigmas" | cut -d: -f2)
  for sig in $sigmas; do
    sb=/storage/ge96pug/Projects_SHA3_sandbox_smoke_v9_mixed_snreq_${cfg}_sigma${sig}
    plr="$sb/project_SHA3-32bit/pipeline_runner"
    log="$plr/sandbox_smoke_v9_mixed_snreq_${cfg}_sigma${sig}.log"
    if [ ! -f "$log" ]; then
      echo "  not_started ${cfg}_sigma${sig}"
      continue
    fi
    if grep -q "COMPLETE" "$log" 2>/dev/null; then
      echo "  DONE     ${cfg}_sigma${sig}"
    elif grep -q "\[MOVE:DN\]" "$log" 2>/dev/null; then
      last=$(tail -1 "$log" 2>/dev/null | cut -c1-80)
      echo "  training ${cfg}_sigma${sig}: $last"
    else
      last=$(tail -1 "$log" 2>/dev/null | cut -c1-80)
      echo "  detect   ${cfg}_sigma${sig}: $last"
    fi
  done
done'
}

# ── manual ICS-gate fallback (delegates to ics_gate_lib.sh) ──────────────────

label_from_cfg_sigma() {
  printf "smoke_v9_mixed_snreq_%s" "$1"
}

env_file_from_cfg_sigma() {
  printf "%s/.env_%s" "${ENVS_DIR}" "$(label_from_cfg_sigma "$1")"
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
  ics_scan) ics_scan_label "$(label_from_cfg_sigma "${ICS_SCAN_ARG}")"; exit 0 ;;
  fix_ics)
    fix_ics_label "$(label_from_cfg_sigma "${FIX_ARG}")" "$(env_file_from_cfg_sigma "${FIX_ARG}")" "${FIX_LEVEL}"
    echo "  Updated sandbox and local env file. Resume with --resume ${FIX_ARG}."
    exit 0
    ;;
  resume)
    resume_label "$(label_from_cfg_sigma "${RESUME_ARG}")"
    exit 0
    ;;
esac

# ── wave launches ─────────────────────────────────────────────────────────────

case "${WAVE}" in
  sanity)
    echo "=== Smoke v9 mixed-snreq sanity check: 4 configs at sigma=1.0 ==="
    echo "Gate: verify ICS levels are non-empty per config (check_ics_archive.py,"
    echo "scan 90 down) and SASCA starts, before launching the batched waves."
    launch_single "${ENVS_DIR}/.env_smoke_v9_mixed_snreq_hwhd_sigma1p0"
    launch_single "${ENVS_DIR}/.env_smoke_v9_mixed_snreq_f9hw_sigma1p0"
    launch_single "${ENVS_DIR}/.env_smoke_v9_mixed_snreq_f9hd_sigma1p0"
    launch_single "${ENVS_DIR}/.env_smoke_v9_mixed_snreq_f9hwhd_sigma1p0"
    ;;
  all)
    echo "=== Smoke v9 mixed-snreq: all 20 runs ==="
    launch_mode hwhd
    launch_mode f9hw
    launch_single "${ENVS_DIR}/.env_smoke_v9_mixed_snreq_f9hd_sigma1p0"
    launch_single "${ENVS_DIR}/.env_smoke_v9_mixed_snreq_f9hwhd_sigma1p0"
    ;;
  hwhd)
    launch_mode hwhd
    ;;
  f9hw)
    launch_mode f9hw
    ;;
  f9hd)
    launch_single "${ENVS_DIR}/.env_smoke_v9_mixed_snreq_f9hd_sigma1p0"
    ;;
  f9hwhd)
    launch_single "${ENVS_DIR}/.env_smoke_v9_mixed_snreq_f9hwhd_sigma1p0"
    ;;
  *)
    echo "Unknown wave: ${WAVE}. Use: sanity, all, hwhd, f9hw, f9hd, f9hwhd." >&2
    exit 1
    ;;
esac

echo ""
echo "Monitor: sh ${SCRIPT_DIR}/launch_smoke_v9_mixed_snreq.sh --status"
