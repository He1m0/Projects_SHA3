#!/usr/bin/env sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"

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

# Validate ICS archive before training — prevents silent template corruption from empty arrays.
# Sources .env to read SHA3_TRAINING_ICS_LEVEL and SHA3_DETECTION_* params.
if [ -f "${PROJECT_DIR}/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "${PROJECT_DIR}/.env"
  set +a
fi
ICS_LEVEL_STR="$(printf '%03d' "$((10#${SHA3_TRAINING_ICS_LEVEL:-10}))")"
ICS_ZIP="${PROJECT_DIR}/0002_detection/Code_extract_ics/ics_original_${ICS_LEVEL_STR}.zip"
log "CHECK: validating training ICS archive (level=${ICS_LEVEL_STR})"
if [ ! -f "${ICS_ZIP}" ]; then
  echo "Error: ICS archive not found: ${ICS_ZIP}" >&2
  echo "Hint: run check_ics_archive.py to find the highest valid level, then update SHA3_TRAINING_ICS_LEVEL." >&2
  exit 1
fi
python3 "${SCRIPT_DIR}/check_ics_archive.py" \
  --ics-zip "${ICS_ZIP}" \
  --round-count "${SHA3_DETECTION_ROUNDS:-4}" \
  --ab-words "${SHA3_DETECTION_ICS_WORDS_AB:-50}" \
  --cd-words "${SHA3_DETECTION_ICS_WORDS_CD:-10}" \
  --max-empty 0 \
  --max-missing 0

run_stage "0003 training preprocessing" "0003_training/Code_preprocessing"
run_stage "0003 training intermediate values" "0003_training/Code_intermediate_values"
run_stage "0003 training IoPs" "0003_training/Code_find_IoPs"
run_stage "0003 training template profiling" "0003_training/template_profiling_bytes"

log "COMPLETE: 0003 training chain finished"
