#!/usr/bin/env sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"

print_help() {
  cat <<'EOF'
Usage:
  sh run_0001_chain.sh

Description:
  Runs the 0001 reference stage:
    1) Code_reference  (produces ref_trace.npy)

Assumption:
  0001_reference/Raw already contains reference trace archives (*.zip).
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

require_non_empty_raw "${PROJECT_DIR}/0001_reference/Raw"

run_stage "0001 reference" "0001_reference/Code_reference"

log "COMPLETE: 0001 reference chain finished"
