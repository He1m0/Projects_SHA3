#!/usr/bin/env sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"

print_help() {
  cat <<'EOF'
Usage:
  sh run_0002_chain.sh

Description:
  Runs the full 0002 detection chain in order:
    1) Code_preprocessing
    2) Code_intermediate_values
    3) Code_detection_R2
    4) Code_extract_ics

Assumption:
  0002_detection/Raw already contains detection trace archives (*.zip).
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  print_help
  exit 0
fi

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

require_non_empty_raw() {
  RAW_DIR="$1"
  if [ ! -d "${RAW_DIR}" ]; then
    echo "Error: Raw directory not found: ${RAW_DIR}" >&2
    exit 1
  fi

  ZIP_COUNT="$(find "${RAW_DIR}" -maxdepth 1 -type f -name '*.zip' | wc -l | tr -d ' ')"
  if [ "${ZIP_COUNT}" -eq 0 ]; then
    echo "Error: no .zip trace archives found in ${RAW_DIR}" >&2
    exit 1
  fi
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

require_non_empty_raw "${PROJECT_DIR}/0002_detection/Raw"

run_stage "0002 detection preprocessing" "0002_detection/Code_preprocessing"
run_stage "0002 detection intermediate values" "0002_detection/Code_intermediate_values"
run_stage "0002 detection R2" "0002_detection/Code_detection_R2"
run_stage "0002 detection ICS extraction" "0002_detection/Code_extract_ics"

log "COMPLETE: 0002 detection chain finished"
