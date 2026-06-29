#!/usr/bin/env sh
# monitor_snr_sweep.sh
#
# Automated wave sequencer for smoke_v6 + paperscale_v5 SNR-equalized sweep.
# Runs ON IDP in a tmux session. Creates sandboxes from a pre-deployed project
# source and sequences all waves automatically.
#
# Setup: run deploy_monitor.sh from local machine first to populate:
#   /storage/ge96pug/Projects_SHA3_src/    — project source (rsynced)
#   /storage/ge96pug/envs_smoke_v6/        — smoke_v6 env files
#   /storage/ge96pug/envs_paperscale_v5/   — paperscale_v5 env files (sigma subdirs)
#
# Phase sequence:
#   S:      launch smoke_v6 sanity (f9+id σ=0.1)
#   Gate:   poll until ICS level 90 valid in both sanity sandboxes
#   SR+A1:  launch smoke_v6 remaining (f9+id σ=0.5-4.0) + paperscale A1 (f9 σ=0.1/0.5/1.0)
#   B1:     [R2 ≤ 6] paperscale B1 (id σ=0.1/0.5/1.0)
#   A2:     [R2 ≤ 6] paperscale A2 (f9 σ=1.5/2.0/2.5)
#   B2:     [R2 ≤ 6] paperscale B2 (id σ=1.5/2.0/2.5)
#   A3:     [R2 ≤ 6] paperscale A3 (f9 σ=3.0/3.5/4.0)
#   B3:     [R2 ≤ 6] paperscale B3 (id σ=3.0/3.5/4.0)
#
# Usage:
#   sh monitor_snr_sweep.sh [OPTIONS]
#   Options:
#     --skip-smoke          skip Phase S + ICS gate + SR; launch A1 directly
#     --start-wave WAVE     skip to paperscale wave (A1 B1 A2 B2 A3 B3); implies --skip-smoke
#     --dry-run             print actions without launching or creating dirs
#     --no-ics-gate         skip ICS archive validation (proceed even on failure)
#     --log FILE            log file (default: /storage/ge96pug/monitor_snr_sweep_TIMESTAMP.log)

set -eu

# ── configuration ─────────────────────────────────────────────────────────────

STORAGE=/storage/ge96pug
SRC="${STORAGE}/Projects_SHA3_src"
ENVS_SMOKE="${STORAGE}/envs_smoke_v6"
ENVS_PS5="${STORAGE}/envs_paperscale_v5"

R2_CAP=6
POLL_INTERVAL=300
ICS_POLL=120

DRY_RUN=0
SKIP_SMOKE=0
START_WAVE=""
NO_ICS_GATE=0
LOG="${STORAGE}/monitor_snr_sweep_$(date '+%Y%m%d_%H%M%S').log"

# ── arg parsing ───────────────────────────────────────────────────────────────

while [ "$#" -gt 0 ]; do
  case "$1" in
    --skip-smoke)   SKIP_SMOKE=1; shift ;;
    --start-wave)   START_WAVE="$2"; SKIP_SMOKE=1; shift 2 ;;
    --dry-run)      DRY_RUN=1; shift ;;
    --no-ics-gate)  NO_ICS_GATE=1; shift ;;
    --log)          LOG="$2"; shift 2 ;;
    --help|-h)
      sed -n '2,/^set -eu/{ /^set -eu/d; s/^# \{0,1\}//; p }' "$0"
      exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# ── helpers ───────────────────────────────────────────────────────────────────

log() {
  ts="[$(date '+%Y-%m-%d %H:%M:%S')]"
  echo "${ts} $*"
  mkdir -p "$(dirname "${LOG}")" 2>/dev/null || true
  echo "${ts} $*" >> "${LOG}" 2>/dev/null || true
}

count_procs() { pgrep -f "$1" 2>/dev/null | wc -l | tr -d ' '; }

get_r2_count() { count_procs detect_script; }

wait_for_r2_capacity() {
  label="$1"
  if [ "${DRY_RUN}" -eq 1 ]; then
    r2=$(get_r2_count)
    log "[DRY-RUN] Would wait R2 ≤ ${R2_CAP} before: ${label} (currently ${r2})"
    return 0
  fi
  log "Waiting for R2 ≤ ${R2_CAP} before: ${label}"
  while true; do
    r2=$(get_r2_count)
    sim=$(count_procs KeccakSim)
    log "  R2=${r2}  KeccakSim=${sim}"
    if [ "${r2}" -le "${R2_CAP}" ]; then
      log "Capacity OK (R2=${r2}). Proceeding: ${label}"
      return 0
    fi
    sleep "${POLL_INTERVAL}"
  done
}

wait_for_ics_gate() {
  if [ "${NO_ICS_GATE}" -eq 1 ]; then
    log "[ICS-GATE BYPASSED via --no-ics-gate]"
    return 0
  fi
  if [ "${DRY_RUN}" -eq 1 ]; then
    log "[DRY-RUN] Would wait for ICS level 90 in f9+id σ=0.1 sanity sandboxes"
    return 0
  fi
  log "ICS gate: waiting for ics_original_090.zip in both sanity sandboxes..."
  for mode in f9 id; do
    sb="${STORAGE}/Projects_SHA3_sandbox_smoke_v6_${mode}_sigma0p1"
    zip="${sb}/project_SHA3-32bit/0002_detection/Code_extract_ics/ics_original_090.zip"
    log "  Polling for: ${zip}"
    while [ ! -f "${zip}" ]; do
      log "  Not yet present. Sleeping ${ICS_POLL}s..."
      sleep "${ICS_POLL}"
    done
    log "  Found: ${zip} — validating..."
    checker="${sb}/project_SHA3-32bit/pipeline_runner/check_ics_archive.py"
    result=$(python3 "${checker}" --ics-zip "${zip}" 2>&1) || true
    if echo "${result}" | grep -q "^OK:"; then
      log "  ICS gate PASSED: smoke_v6_${mode}_sigma0p1 (level 90)"
    else
      log "  ICS gate FAILED: smoke_v6_${mode}_sigma0p1"
      log "  Output: ${result}"
      log "  Use --no-ics-gate to bypass. Aborting."
      exit 1
    fi
  done
  log "ICS gate passed for both sanity runs."
}

launch_run() {
  mode="$1"; sigma="$2"; version="$3"

  if [ "${version}" = "smoke_v6" ]; then
    env_src="${ENVS_SMOKE}/.env_smoke_v6_${mode}_sigma${sigma}"
    sandbox="${STORAGE}/Projects_SHA3_sandbox_smoke_v6_${mode}_sigma${sigma}"
    traces_dir="${STORAGE}/traces_smoke_v6_${mode}_sigma${sigma}"
    env_name="smoke_v6_${mode}_sigma${sigma}"
  else
    env_src="${ENVS_PS5}/sigma${sigma}/.env_paperscale_v5_${mode}_sigma${sigma}"
    sandbox="${STORAGE}/Projects_SHA3_sandbox_paperscale_v5_${mode}_sigma${sigma}"
    traces_dir="${STORAGE}/traces_paperscale_v5_${mode}_sigma${sigma}"
    env_name="paperscale_v5_${mode}_sigma${sigma}"
  fi

  label="sandbox_${env_name}"
  proj="${sandbox}/project_SHA3-32bit"
  env_dest="${proj}/pipeline_runner/envs/.env_${env_name}"
  log_file="${proj}/pipeline_runner/${label}.log"

  if [ "${DRY_RUN}" -eq 1 ]; then
    log "[DRY-RUN] launch_run: ${env_name}"
    log "  sandbox:    ${sandbox}"
    log "  traces_dir: ${traces_dir}"
    log "  env_src:    ${env_src}"
    return 0
  fi

  log "Setting up sandbox: ${label}"
  mkdir -p "${sandbox}"
  rsync -a --delete "${SRC}/" "${proj}/"
  mkdir -p "${traces_dir}"
  mkdir -p "$(dirname "${env_dest}")"
  cp "${env_src}" "${env_dest}"

  inner_cmd="cd '${proj}/pipeline_runner' && export TRACES_DIR='${traces_dir}' && sh run_full_pipeline.sh --env-file 'envs/.env_${env_name}'"
  tmux kill-session -t "${label}" 2>/dev/null || true
  tmux new-session -d -s "${label}" sh -lc "${inner_cmd}"
  i=0
  while ! tmux has-session -t "${label}" 2>/dev/null && [ "${i}" -lt 10 ]; do
    i=$((i + 1)); sleep 0.3
  done
  tmux pipe-pane -o -t "${label}:0.0" "cat >> '${log_file}'"
  log "Launched: ${label}"
}

launch_ps5_wave() {
  wave_label="$1"; mode="$2"; s1="$3"; s2="$4"; s3="$5"
  log "=== Paperscale v5 wave ${wave_label}: ${mode} σ=${s1}/${s2}/${s3} ==="
  r2=$(get_r2_count)
  log "  R2 before launch: ${r2}"
  launch_run "${mode}" "${s1}" paperscale_v5
  launch_run "${mode}" "${s2}" paperscale_v5
  launch_run "${mode}" "${s3}" paperscale_v5
}

# ── phase functions ───────────────────────────────────────────────────────────

phase_s() {
  log "=== Phase S: smoke_v6 sanity (f9+id σ=0.1) ==="
  launch_run f9 0p1 smoke_v6
  launch_run id 0p1 smoke_v6
}

phase_sr() {
  log "=== Phase SR: smoke_v6 remaining (f9+id σ=0.5..4.0, 16 runs) ==="
  for sig in 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
    launch_run f9 "${sig}" smoke_v6
    launch_run id "${sig}" smoke_v6
  done
}

phase_a1() {
  launch_ps5_wave A1 f9 0p1 0p5 1p0
}

phase_b1() {
  wait_for_r2_capacity "B1 id σ=0.1/0.5/1.0"
  launch_ps5_wave B1 id 0p1 0p5 1p0
}

phase_a2() {
  wait_for_r2_capacity "A2 f9 σ=1.5/2.0/2.5"
  launch_ps5_wave A2 f9 1p5 2p0 2p5
}

phase_b2() {
  wait_for_r2_capacity "B2 id σ=1.5/2.0/2.5"
  launch_ps5_wave B2 id 1p5 2p0 2p5
}

phase_a3() {
  wait_for_r2_capacity "A3 f9 σ=3.0/3.5/4.0"
  launch_ps5_wave A3 f9 3p0 3p5 4p0
}

phase_b3() {
  wait_for_r2_capacity "B3 id σ=3.0/3.5/4.0"
  launch_ps5_wave B3 id 3p0 3p5 4p0
}

# ── pre-flight checks ─────────────────────────────────────────────────────────

preflight_check() {
  if [ "${DRY_RUN}" -eq 0 ]; then
    for d in "${SRC}" "${ENVS_SMOKE}" "${ENVS_PS5}"; do
      if [ ! -d "${d}" ]; then
        echo "ERROR: Required directory not found: ${d}" >&2
        echo "Run deploy_monitor.sh from local machine first." >&2
        exit 1
      fi
    done
  fi
}

# ── main ──────────────────────────────────────────────────────────────────────

preflight_check

log "=== SNR-equalized sweep monitor ==="
[ "${DRY_RUN}"   -eq 1 ] && log "*** DRY-RUN MODE — no launches ***"
[ "${SKIP_SMOKE}" -eq 1 ] && log "*** --skip-smoke: skipping Phase S + ICS gate + SR ***"
[ -n "${START_WAVE}" ]    && log "*** --start-wave ${START_WAVE} ***"
log "R2_CAP=${R2_CAP}  POLL=${POLL_INTERVAL}s  ICS_POLL=${ICS_POLL}s"
log "Log: ${LOG}"

if [ "${SKIP_SMOKE}" -eq 0 ]; then
  phase_s
  wait_for_ics_gate
  phase_sr
  phase_a1
  phase_b1
  phase_a2
  phase_b2
  phase_a3
  phase_b3
else
  # Run paperscale waves from START_WAVE onwards (default A1 = all waves).
  START="${START_WAVE:-A1}"
  reached=0
  for wave_id in A1 B1 A2 B2 A3 B3; do
    [ "${wave_id}" = "${START}" ] && reached=1
    [ "${reached}" -eq 0 ] && continue
    case "${wave_id}" in
      A1) phase_a1 ;;
      B1) phase_b1 ;;
      A2) phase_a2 ;;
      B2) phase_b2 ;;
      A3) phase_a3 ;;
      B3) phase_b3 ;;
    esac
  done
  if [ "${reached}" -eq 0 ]; then
    echo "Unknown --start-wave value: ${START_WAVE}. Use A1 B1 A2 B2 A3 B3." >&2
    exit 1
  fi
fi

log "=== All phases complete. Monitor done. ==="
