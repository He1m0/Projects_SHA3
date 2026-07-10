#!/usr/bin/env sh
# paperscale_relaunch_monitor_v2_remote.sh
#
# Post-disk-incident restart monitor for paperscale v3 lower-sigma runs.
# Runs ON IDP directly. All sandboxes already exist; this script only
# restarts crashed pipelines within them.
#
# Phase 1: hw+f9 sigma1p5 — --skip-sim (simulation intact, detection crashed)
# Phase 2: f9  sigma1p0  — clear TRACES_DIR + full pipeline (simulation crashed)
# Phase 3: all sigma0p5  — clear TRACES_DIR + full pipeline (simulation crashed)
# Phase 4: all sigma0p1  — clear TRACES_DIR + full pipeline (simulation crashed)
#
# Safety: R2 + KeccakSim <= INFLIGHT_CAP before each launch batch.
# Usage: sh paperscale_relaunch_monitor_v2_remote.sh [--dry-run]

set -eu

STORAGE=/storage/ge96pug
INFLIGHT_CAP=6
POLL_INTERVAL=300
LOG=${STORAGE}/paperscale_monitor_v2_remote.log
DRY_RUN=0

if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
fi

log() {
  ts="[$(date '+%Y-%m-%d %H:%M:%S')]"
  echo "${ts} $*"
  echo "${ts} $*" >> "${LOG}"
}

count_procs() { pgrep -f "$1" 2>/dev/null | wc -l | tr -d ' '; }

get_inflight() {
  r2=$(count_procs detect_script)
  sim=$(count_procs KeccakSim)
  log "  R2=${r2}  KeccakSim=${sim}  in-flight=$((r2 + sim))" >&2
  echo $((r2 + sim))
}

wait_for_capacity() {
  local label="$1"
  if [ "${DRY_RUN}" -eq 1 ]; then
    inflight=$(get_inflight)
    log "[DRY-RUN] Would wait for in-flight <= ${INFLIGHT_CAP} before: ${label} (currently ${inflight})"
    return 0
  fi
  log "Waiting for in-flight <= ${INFLIGHT_CAP} before: ${label}"
  while true; do
    inflight=$(get_inflight)
    if [ "${inflight}" -le "${INFLIGHT_CAP}" ]; then
      log "Capacity OK (in-flight=${inflight}). Proceeding: ${label}"
      return 0
    fi
    sleep "${POLL_INTERVAL}"
  done
}

clear_traces() {
  local traces_dir="$1"
  if [ "${DRY_RUN}" -eq 1 ]; then
    local count
    count=$(find "${traces_dir}" -maxdepth 1 -not -name "$(basename "${traces_dir}")" 2>/dev/null | wc -l | tr -d ' ')
    log "[DRY-RUN] Would clear ${traces_dir} (${count} entries)"
    return 0
  fi
  log "Clearing TRACES_DIR: ${traces_dir}"
  rm -rf "${traces_dir:?}/"*
}

check_sandbox() {
  local mode="$1" sigma="$2"
  local sandbox="${STORAGE}/Projects_SHA3_sandbox_paperscale_v3_${mode}_sigma${sigma}"
  local env_file="${sandbox}/project_SHA3-32bit/pipeline_runner/envs/.env_paperscale_v3_${mode}_sigma${sigma}"
  local traces_dir="${STORAGE}/traces_paperscale_v3_${mode}_sigma${sigma}"
  if [ ! -d "${sandbox}" ]; then
    log "ERROR: sandbox missing: ${sandbox}"; exit 1
  fi
  if [ ! -f "${env_file}" ]; then
    log "ERROR: env file missing: ${env_file}"; exit 1
  fi
  if [ ! -d "${traces_dir}" ]; then
    log "ERROR: traces dir missing: ${traces_dir}"; exit 1
  fi
  log "  OK: ${mode} sigma${sigma} — sandbox, env, traces all present"
}

launch_run() {
  local mode="$1" sigma="$2" skip_sim="$3"
  local sandbox="${STORAGE}/Projects_SHA3_sandbox_paperscale_v3_${mode}_sigma${sigma}"
  local pipeline_dir="${sandbox}/project_SHA3-32bit/pipeline_runner"
  local tmux_label="sandbox_paperscale_v3_${mode}_sigma${sigma}"
  local log_path="${pipeline_dir}/${tmux_label}.log"
  local traces_dir="${STORAGE}/traces_paperscale_v3_${mode}_sigma${sigma}"
  local extra_flags=""
  [ "${skip_sim}" -eq 1 ] && extra_flags="--skip-sim"
  if [ "${DRY_RUN}" -eq 1 ]; then
    log "[DRY-RUN] Would launch: tmux session=${tmux_label} skip_sim=${skip_sim}"
    log "  cmd: cd ${pipeline_dir} && sh run_full_pipeline.sh --env-file envs/.env_paperscale_v3_${mode}_sigma${sigma} ${extra_flags}"
    return 0
  fi
  local inner_cmd="cd \"${pipeline_dir}\" && export TRACES_DIR=\"${traces_dir}\" && sh run_full_pipeline.sh --env-file \"envs/.env_paperscale_v3_${mode}_sigma${sigma}\" ${extra_flags}"
  tmux kill-session -t "${tmux_label}" 2>/dev/null || true
  tmux new-session -d -s "${tmux_label}" sh -lc "${inner_cmd}"
  i=0
  while ! tmux has-session -t "${tmux_label}" 2>/dev/null && [ "${i}" -lt 10 ]; do
    i=$((i + 1)); sleep 0.2
  done
  tmux pipe-pane -o -t "${tmux_label}:0.0" "cat >> '${log_path}'"
  log "Launched: ${mode} sigma${sigma} (skip_sim=${skip_sim})"
}

log "=== Paperscale v3 restart monitor v2 (remote) ==="
[ "${DRY_RUN}" -eq 1 ] && log "*** DRY-RUN MODE — no launches or deletions ***"
log "Phases: hw+f9/1p5(skip-sim) -> f9/1p0(full) -> all/0p5(full) -> all/0p1(full)"
log "Cap: in-flight <= ${INFLIGHT_CAP}; poll every ${POLL_INTERVAL}s"

# Pre-flight: verify all sandboxes, env files, and traces dirs exist
log "=== Pre-flight checks ==="
check_sandbox hw 1p5
check_sandbox f9 1p5
check_sandbox f9 1p0
for mode in hd hw id f9; do
  check_sandbox "${mode}" 0p5
  check_sandbox "${mode}" 0p1
done
log "Pre-flight OK."

# Phase 1: hw+f9 sigma1p5, --skip-sim (simulation done, detection crashed)
log "=== Phase 1: hw+f9 sigma1p5 (--skip-sim) ==="
wait_for_capacity "hw+f9 sigma1p5 --skip-sim"
launch_run hw 1p5 1
launch_run f9 1p5 1
log "Phase 1 done. Pausing 90s..."
[ "${DRY_RUN}" -eq 0 ] && sleep 90

# Phase 2: f9 sigma1p0, full restart (simulation crashed)
log "=== Phase 2: f9 sigma1p0 (full) ==="
wait_for_capacity "f9 sigma1p0 full"
clear_traces "${STORAGE}/traces_paperscale_v3_f9_sigma1p0"
launch_run f9 1p0 0
log "Phase 2 done. Pausing 90s..."
[ "${DRY_RUN}" -eq 0 ] && sleep 90

# Phase 3: sigma0p5 all 4 modes, full restart (simulation crashed)
log "=== Phase 3: all sigma0p5 (full) ==="
wait_for_capacity "all sigma0p5 full"
for mode in hd hw id f9; do
  clear_traces "${STORAGE}/traces_paperscale_v3_${mode}_sigma0p5"
done
for mode in hd hw id f9; do
  launch_run "${mode}" 0p5 0
done
log "Phase 3 done. Pausing 90s..."
[ "${DRY_RUN}" -eq 0 ] && sleep 90

# Phase 4: sigma0p1 all 4 modes, full restart (simulation crashed)
log "=== Phase 4: all sigma0p1 (full) ==="
wait_for_capacity "all sigma0p1 full"
for mode in hd hw id f9; do
  clear_traces "${STORAGE}/traces_paperscale_v3_${mode}_sigma0p1"
done
for mode in hd hw id f9; do
  launch_run "${mode}" 0p1 0
done
log "Phase 4 done."

log "=== All phases complete. Monitor v2 done. ==="
