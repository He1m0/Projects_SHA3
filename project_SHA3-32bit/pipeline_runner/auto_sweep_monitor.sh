#!/usr/bin/env sh
# Unattended ICS-gate-and-launch orchestrator for the word-granularity smoke
# sweeps (smoke_v8 pure modes, smoke_v9 mixed configs). Generalizes the
# proven-manual gate/fix/resume triad in ics_gate_lib.sh (itself extracted
# from launch_paperscale_v6.sh) into a loop that runs unattended.
#
# Intended deployment: sync this file + ics_gate_lib.sh + the updated
# launchers + env dirs to the master repo copy on IDP
# (/storage/ge96pug/Projects_SHA3/project_SHA3-32bit/pipeline_runner/), then
# run it INSIDE a detached tmux session ON IDP itself (SSH_TARGET unset ->
# ics_gate_lib.sh's remote_exec runs directly, no ssh dependency) so the
# sweep survives ssh disconnects and local-machine/session churn:
#
#   ssh IDP "tmux new-session -d -s auto_sweep_monitor \
#     'cd /storage/ge96pug/Projects_SHA3/project_SHA3-32bit/pipeline_runner && \
#      sh auto_sweep_monitor.sh --family smoke_v8 --modes hw,hd,f9,id'"
#
# Can also be run from the local machine with SSH_TARGET=IDP (ssh-wrapped)
# for --dry-run validation against real remote state before trusting it live
# -- see ics_gate_lib.sh's dual-mode remote_exec.
#
# Per unit (mode for smoke_v8, config for smoke_v9; SIGMA TIER for smoke_v10
# -- see below), all run concurrently (one background subshell per unit):
#   1. Launch every sigma of the unit, ascending, one at a time, each waited
#      behind a soft R2-pressure cap (launched + not-yet-past-R2 sandboxes,
#      host-wide -- NOT a live detect_script process count, which lags
#      several minutes behind a fresh launch and would let a burst of
#      launches all pass the check before any of them are actually visible,
#      only to pile onto R2 together later). Launching stays sequential
#      (one decision at a time) specifically to avoid a burst of concurrent
#      launches all passing the pressure check in the same instant, before
#      any of them has created its sandbox dir yet.
#   2. Each launched sigma gets its OWN independent watcher (watch_sigma(),
#      run concurrently, one per sigma): poll for COMPLETE, a non-ICS error,
#      or the ICS gate error. On the ICS gate error: scan that sigma's own
#      already-computed threshold zips for the highest non-empty level,
#      patch that sigma's env, resume it. One fix attempt only -- a second
#      failure halts that sigma (not the whole unit) for manual review.
#
# Every sigma determines its own ICS level independently -- there is no
# "gate sigma decides for the whole unit" step. Noise directly changes how
# many points clear a given R^2 threshold, so the correct level is a
# property of that specific sigma's detection output, not of the mode as a
# whole; earlier versions of this script inherited one sigma's confirmed
# level into every other sigma's env file unconditionally, which is wrong
# in general (see RUN_LOG_auto_sweep.md "ICS level is not actually
# re-verified per sigma"). Every env file should start at the maximum level
# (090) so a sigma that passes immediately is automatically optimal (090 is
# the ceiling), and a sigma that fails gets the same honest 090-down scan
# the old code only ever ran for the lowest sigma.
#
# Every decision is logged with a timestamp to
# auto_sweep_monitor_<family>.log (same dir as this script) via logmsg().
#
# smoke_v10 batches by SIGMA TIER instead of mode (all 4 modes at one noise
# level launch together, tiers processed ascending -- see
# launch_smoke_v10_word_mix.sh) -- "unit" there is a sigma, and each unit's
# inner ascending loop runs the 4 modes instead of the 9 sigmas.
#
# Usage:
#   sh auto_sweep_monitor.sh --family smoke_v8 --modes hw,hd,f9,id [--dry-run]
#   sh auto_sweep_monitor.sh --family smoke_v9 --configs hwhd,f9hw,f9hd,f9hwhd [--dry-run]
#   sh auto_sweep_monitor.sh --family smoke_v10 --sigmas 0p1,0p5,1p0,1p5,2p0,2p5,3p0,3p5,4p0 [--dry-run]
#   sh auto_sweep_monitor.sh --family smoke_v8 --modes hw,hd,f9,id --status
#   sh auto_sweep_monitor.sh --family smoke_v8 --modes hw,hd,f9,id --status --detailed
#
# Options:
#   --poll-interval SEC   Polling cadence (default 60)
#   --r2-cap N            Soft R2-process concurrency cap before a new wave (default 20;
#                          host has 192 cores / 428GB free, empirically far from the old
#                          6/10 caps sized off an unverified per-process RAM estimate)
#   --detailed            With --status: also show each running sigma's current
#                          pipeline stage (last timestamped log line -- which
#                          of reference/detection/R2/ICS/training/IoP/validation/
#                          SASCA/rate-scan it's actually at, not just "running")

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
. "${SCRIPT_DIR}/ics_gate_lib.sh"

FAMILY=""
UNITS=""
DRY_RUN=0
POLL_INTERVAL=60
R2_CAP=20
ACTION="run"
DETAILED=0

print_help() {
  sed -n '2,/^set -eu/{ /^set -eu/d; s/^# \{0,1\}//; p }' "$0"
  exit 0
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --family)        FAMILY="$2"; shift 2 ;;
    --modes)         UNITS="$2"; shift 2 ;;
    --configs)       UNITS="$2"; shift 2 ;;
    --sigmas)        UNITS="$2"; shift 2 ;;
    --poll-interval) POLL_INTERVAL="$2"; shift 2 ;;
    --r2-cap)        R2_CAP="$2"; shift 2 ;;
    --dry-run)       DRY_RUN=1; shift ;;
    --status)        ACTION="status"; shift ;;
    --detailed)      DETAILED=1; shift ;;
    --help|-h)        print_help ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [ -z "${FAMILY}" ] || [ -z "${UNITS}" ]; then
  echo "Error: --family and --modes/--configs/--sigmas are required" >&2
  exit 2
fi

case "${FAMILY}" in
  smoke_v8) ENVS_DIR="${SCRIPT_DIR}/envs/smoke_v8_granularity_word_sigma_sweep" ;;
  smoke_v9) ENVS_DIR="${SCRIPT_DIR}/envs/smoke_v9_mixed_snreq" ;;
  smoke_v10) ENVS_DIR="${SCRIPT_DIR}/envs/smoke_v10_word_mix" ;;
  *) echo "Unknown family: ${FAMILY}. Use smoke_v8, smoke_v9, or smoke_v10." >&2; exit 1 ;;
esac

LOGFILE="${SCRIPT_DIR}/auto_sweep_monitor_${FAMILY}.log"
SIGMAS_ASC="0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0"

logmsg() {
  unit_tag="${1:-}"
  shift || true
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  if [ -n "${unit_tag}" ]; then
    printf '[%s] [%s] %s\n' "${ts}" "${unit_tag}" "$*" | tee -a "${LOGFILE}"
  else
    printf '[%s] %s\n' "${ts}" "$*" | tee -a "${LOGFILE}"
  fi
}

# ── family-aware naming ───────────────────────────────────────────────────────

MODES_ASC="hw hd f9 id"

sigmas_for_unit() {
  family="$1"; unit="$2"
  if [ "${family}" = "smoke_v9" ]; then
    case "${unit}" in
      f9hd|f9hwhd) echo "1p0"; return ;;
    esac
  fi
  if [ "${family}" = "smoke_v10" ]; then
    # smoke_v10 batches by sigma tier: "unit" is a sigma, and the inner
    # ascending loop runs the 4 modes instead of the 9 sigmas.
    echo "${MODES_ASC}"
    return
  fi
  echo "${SIGMAS_ASC}"
}

label_for_unit() {
  family="$1"; unit="$2"; sigma="$3"
  case "${family}" in
    smoke_v8) printf "smoke_v8_granularity_word_%s_sigma%s" "${unit}" "${sigma}" ;;
    smoke_v9) printf "smoke_v9_mixed_snreq_%s_sigma%s" "${unit}" "${sigma}" ;;
    # smoke_v10: unit is a sigma, sigma (from sigmas_for_unit above) is
    # actually a mode -- swapped positions vs. smoke_v8/v9.
    smoke_v10) printf "smoke_v10_word_mix_%s_sigma%s" "${sigma}" "${unit}" ;;
  esac
}

env_file_for_unit() {
  family="$1"; unit="$2"; sigma="$3"
  label="$(label_for_unit "${family}" "${unit}" "${sigma}")"
  printf "%s/.env_%s" "${ENVS_DIR}" "${label}"
}

# ── launch a single env file (mirrors launch_single() in the family launchers,
#    dual-mode: ssh from local machine, or direct local invocation on IDP) ───

launch_env() {
  env_file="$1"
  name="$(basename "${env_file}" | sed 's/^\.env_//')"
  logmsg "" "launching: ${name}"
  if [ "${DRY_RUN}" -eq 1 ]; then
    logmsg "" "  [DRY RUN] would launch ${name}"
    return
  fi
  tmp_dir="/tmp/auto_sweep_monitor_$$_${name}"
  mkdir -p "${tmp_dir}"
  cp "${env_file}" "${tmp_dir}/"
  if [ -n "${SSH_TARGET}" ]; then
    sh "${SCRIPT_DIR}/run_sandboxes.sh" --envs-dir "${tmp_dir}" --ssh "${SSH_TARGET}"
  else
    sh "${SCRIPT_DIR}/run_sandboxes.sh" --envs-dir "${tmp_dir}" \
      --base-dir /storage/ge96pug --repo-src /storage/ge96pug/Projects_SHA3
  fi
  rm -rf "${tmp_dir}"
}

# ── status (quick, no launches) ───────────────────────────────────────────────

show_status() {
  old_ifs="${IFS}"
  IFS=,
  for unit in ${UNITS}; do
    IFS="${old_ifs}"
    echo "=== ${unit} ==="
    for sig in $(sigmas_for_unit "${FAMILY}" "${unit}"); do
      label="$(label_for_unit "${FAMILY}" "${unit}" "${sig}")"
      if not_started "${label}"; then
        echo "  not_started ${label}"
      elif is_complete "${label}"; then
        echo "  DONE        ${label}"
      elif ics_gate_failed "${label}"; then
        echo "  ics_gate_failed ${label}"
      elif has_other_error "${label}"; then
        echo "  HALT        ${label}"
      elif is_orphaned "${label}"; then
        echo "  ORPHANED    ${label}  (tmux session gone, no COMPLETE/error in log -- see RUN_LOG_auto_sweep.md 24-sandbox incident)"
      else
        if [ "${DETAILED}" -eq 1 ]; then
          stage="$(last_stage_for "${label}")"
          echo "  running     ${label}"
          echo "                ${stage}"
        else
          echo "  running     ${label}"
        fi
      fi
    done
    IFS=,
  done
  IFS="${old_ifs}"
}

if [ "${ACTION}" = "status" ]; then
  show_status
  exit 0
fi

# ── per-sigma independent ICS watcher ────────────────────────────────────────
# Polls one sigma until COMPLETE or HALT, fixing its own ICS level (one
# attempt) if it hits the gate error. Never trusts an inherited level from
# any other sigma -- this is the only place a level is ever confirmed.

watch_sigma() {
  unit="$1"; label="$2"; env_f="$3"
  fixed=0
  while :; do
    if is_complete "${label}"; then
      logmsg "${unit}" "${label} COMPLETE"
      return 0
    fi
    if has_other_error "${label}"; then
      logmsg "${unit}" "HALT: ${label} hit a non-ICS error -- manual investigation needed"
      return 1
    fi
    if ics_gate_failed "${label}"; then
      if [ "${fixed}" -eq 1 ]; then
        logmsg "${unit}" "HALT: ${label} failed the ICS gate again after a fix attempt -- manual investigation needed, not retrying again"
        return 1
      fi
      logmsg "${unit}" "${label} hit the ICS gate error, scanning threshold levels..."
      level="$(ics_scan_label "${label}" | tail -1)"
      case "${level}" in
        [0-9][0-9][0-9]) ;;
        *) logmsg "${unit}" "HALT: no valid ICS level found for ${label} (scan said: ${level})"; return 1 ;;
      esac
      logmsg "${unit}" "confirmed level=${level} for ${label} -- patching and resuming"
      fix_ics_label "${label}" "${env_f}" "${level}"
      resume_label "${label}"
      fixed=1
      continue
    fi
    sleep "${POLL_INTERVAL}"
  done
}

# ── per-unit launch/watch loop ───────────────────────────────────────────────
# Launches every sigma of the unit sequentially (ascending, behind the R2
# pressure cap -- kept sequential so multiple sigmas can't all pass the
# pressure check in the same instant before any of them has created its
# sandbox dir), then hands each one to its own concurrent watch_sigma().

process_unit() {
  family="$1"; unit="$2"
  sigmas="$(sigmas_for_unit "${family}" "${unit}")"
  watcher_pids=""

  for sig in ${sigmas}; do
    label="$(label_for_unit "${family}" "${unit}" "${sig}")"
    env_f="$(env_file_for_unit "${family}" "${unit}" "${sig}")"

    if not_started "${label}"; then
      while :; do
        [ "${DRY_RUN}" -eq 1 ] && break
        pressure="$(r2_pressure)"
        if [ "${pressure}" -le "${R2_CAP}" ]; then
          break
        fi
        logmsg "${unit}" "r2_pressure=${pressure} > cap ${R2_CAP}, waiting before launching ${label}"
        sleep "${POLL_INTERVAL}"
      done
      launch_env "${env_f}"
    else
      logmsg "${unit}" "${label} already exists, not relaunching"
    fi

    [ "${DRY_RUN}" -eq 1 ] && { logmsg "${unit}" "[DRY RUN] would watch ${label}"; continue; }

    watch_sigma "${unit}" "${label}" "${env_f}" &
    watcher_pids="${watcher_pids} $!"
  done

  [ "${DRY_RUN}" -eq 1 ] && { logmsg "${unit}" "[DRY RUN] skipping final wait"; return 0; }

  fail=0
  for pid in ${watcher_pids}; do
    wait "${pid}" || fail=1
  done
  logmsg "${unit}" "unit loop finished (check log above for any HALT lines)"
  return "${fail}"
}

logmsg "" "=== auto_sweep_monitor starting: family=${FAMILY} units=${UNITS} dry_run=${DRY_RUN} ==="

PIDS=""
old_ifs="${IFS}"
IFS=,
for unit in ${UNITS}; do
  IFS="${old_ifs}"
  process_unit "${FAMILY}" "${unit}" &
  PIDS="${PIDS} $!"
  IFS=,
done
IFS="${old_ifs}"

FAIL=0
for pid in ${PIDS}; do
  wait "${pid}" || FAIL=1
done

logmsg "" "=== auto_sweep_monitor finished: family=${FAMILY} (fail=${FAIL} -- check log for HALT lines) ==="
