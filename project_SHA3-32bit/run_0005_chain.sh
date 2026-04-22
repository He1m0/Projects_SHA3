#!/usr/bin/env sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"

print_help() {
  cat <<'EOF'
Usage:
  sh run_0005_chain.sh

Description:
  Runs the full 0005 SASCA chain in order:
    1) get_answers
    2) bit_table_generation
    3) Iteration_Scan_2R
    4) Iteration_Scan_3R
    5) Iteration_Scan_4R
    6) Rate_Scan_2R
    7) Rate_Scan_3R
    8) Rate_Scan_4R
    9) plot_scans
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  print_help
  exit 0
fi

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

run_stage() {
  LABEL="$1"
  REL_DIR="$2"

  log "START: ${LABEL}"
  (
    cd "${PROJECT_DIR}/${REL_DIR}"
    if [ -x "./clean.sh" ]; then
      ./clean.sh || true
    fi
    ./script_all.sh
  )
  log "DONE : ${LABEL}"
}

run_stage_bg() {
  LABEL="$1"
  REL_DIR="$2"

  (
    log "START: ${LABEL}"
    (
      cd "${PROJECT_DIR}/${REL_DIR}"
      if [ -x "./clean.sh" ]; then
        ./clean.sh || true
      fi
      ./script_all.sh
    )
    log "DONE : ${LABEL}"
  ) &
  LAST_BG_PID="$!"
}

wait_for_pids() {
  GROUP_LABEL="$1"
  PIDS="$2"
  FAIL=0

  for PID in ${PIDS}; do
    if ! wait "${PID}"; then
      FAIL=1
    fi
  done

  if [ "${FAIL}" -ne 0 ]; then
    echo "Error: one or more jobs failed in ${GROUP_LABEL}" >&2
    exit 1
  fi
}

run_stage "0005 SASCA answers" "0005_SASCA/get_answers"
run_stage "0005 SASCA bit tables" "0005_SASCA/bit_table_generation"

SCAN_PIDS=""
run_stage_bg "0005 SASCA iteration scan 2R" "0005_SASCA/Iteration_Scan_2R"
SCAN_PIDS="${SCAN_PIDS} ${LAST_BG_PID}"
run_stage_bg "0005 SASCA iteration scan 3R" "0005_SASCA/Iteration_Scan_3R"
SCAN_PIDS="${SCAN_PIDS} ${LAST_BG_PID}"
run_stage_bg "0005 SASCA iteration scan 4R" "0005_SASCA/Iteration_Scan_4R"
SCAN_PIDS="${SCAN_PIDS} ${LAST_BG_PID}"
run_stage_bg "0005 SASCA rate scan 2R" "0005_SASCA/Rate_Scan_2R"
SCAN_PIDS="${SCAN_PIDS} ${LAST_BG_PID}"
run_stage_bg "0005 SASCA rate scan 3R" "0005_SASCA/Rate_Scan_3R"
SCAN_PIDS="${SCAN_PIDS} ${LAST_BG_PID}"
run_stage_bg "0005 SASCA rate scan 4R" "0005_SASCA/Rate_Scan_4R"
SCAN_PIDS="${SCAN_PIDS} ${LAST_BG_PID}"
wait_for_pids "0005 scans" "${SCAN_PIDS}"

run_stage "0005 SASCA plot scans" "0005_SASCA/plot_scans"

log "COMPLETE: 0005 SASCA chain finished"
