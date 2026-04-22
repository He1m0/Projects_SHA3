#!/usr/bin/env sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"

print_help() {
  cat <<'EOF'
Usage:
  sh run_0003_chain.sh

Description:
  Runs the full 0003 training chain in order:
    1) Code_preprocessing
    2) Code_intermediate_values
    3) Code_find_IoPs
    4) template_profiling_bytes

Assumptions:
  0003_training/Raw already contains training trace archives (*.zip).
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

require_non_empty_raw "${PROJECT_DIR}/0003_training/Raw"

run_stage "0003 training preprocessing" "0003_training/Code_preprocessing"
run_stage "0003 training intermediate values" "0003_training/Code_intermediate_values"
run_stage "0003 training IoPs" "0003_training/Code_find_IoPs"
run_stage "0003 training template profiling" "0003_training/template_profiling_bytes"

log "COMPLETE: 0003 training chain finished"
