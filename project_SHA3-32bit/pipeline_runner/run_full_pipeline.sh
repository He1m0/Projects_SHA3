#!/usr/bin/env sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE_DIR="$(CDPATH= cd -- "${PROJECT_DIR}/.." && pwd)"
SIM_SCRIPT="${WORKSPACE_DIR}/KeccakSim_BI_TA.py"
ICS_CHECK_SCRIPT="${SCRIPT_DIR}/check_ics_archive.py"

ENV_FILE="${PROJECT_DIR}/.env_debug"
SKIP_SIM=0
SKIP_CHAIN=0
KEEP_LOCAL_ZIPS=0
PARALLEL_SCANS=1
CLI_TRACES_DIR=""

if [ -x "${WORKSPACE_DIR}/.venv/bin/python" ]; then
  PATH="${WORKSPACE_DIR}/.venv/bin:${PATH}"
  export PATH
elif [ -x "${WORKSPACE_DIR}/venv/bin/python" ]; then
  PATH="${WORKSPACE_DIR}/venv/bin:${PATH}"
  export PATH
fi

print_help() {
  cat <<'EOF'
Usage:
  sh run_full_pipeline.sh [options]

Options:
  --env-file PATH     Env profile to apply as project .env (default: ../.env_debug)
  --traces-dir PATH   Explicit TRACES_DIR for this run (overrides shell env)
  --skip-sim          Skip trace simulation/zip/deploy and only run 0001-0005 chain
  --skip-chain        Only simulate+deploy traces, do not run 0001-0005 chain
  --keep-local-zips   Keep generated zip files in TRACES_DIR as copies
  --serial-scans      Run 0005 scan stages serially instead of in parallel (parallel is default)
  -h, --help          Show this help

Required:
  TRACES_DIR must be set in your shell environment.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --env-file)
      if [ "$#" -lt 2 ]; then
        echo "Error: --env-file requires a path" >&2
        exit 2
      fi
      ENV_FILE="$2"
      shift 2
      ;;
    --traces-dir)
      if [ "$#" -lt 2 ]; then
        echo "Error: --traces-dir requires a path" >&2
        exit 2
      fi
      CLI_TRACES_DIR="$2"
      shift 2
      ;;
    --skip-sim)
      SKIP_SIM=1
      shift
      ;;
    --skip-chain)
      SKIP_CHAIN=1
      shift
      ;;
    --keep-local-zips)
      KEEP_LOCAL_ZIPS=1
      shift
      ;;
    --serial-scans)
      PARALLEL_SCANS=0
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      echo "Error: unknown option: $1" >&2
      print_help >&2
      exit 2
      ;;
  esac
done

if [ ! -f "${ENV_FILE}" ]; then
  echo "Error: env file not found: ${ENV_FILE}" >&2
  exit 1
fi

if [ ! -f "${SIM_SCRIPT}" ]; then
  echo "Error: simulator not found: ${SIM_SCRIPT}" >&2
  exit 1
fi

if [ -n "${CLI_TRACES_DIR}" ]; then
  TRACES_DIR="${CLI_TRACES_DIR}"
  export TRACES_DIR
fi

if [ -z "${TRACES_DIR:-}" ] && [ "$SKIP_SIM" -eq 0 ]; then
  echo "Error: TRACES_DIR is not set" >&2
  exit 1
fi

# Apply selected environment profile for all project scripts.
cp "${ENV_FILE}" "${PROJECT_DIR}/.env"

set -a
# shellcheck disable=SC1090
. "${ENV_FILE}"
set +a

if [ -n "${CLI_TRACES_DIR}" ]; then
  TRACES_DIR="${CLI_TRACES_DIR}"
  export TRACES_DIR
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

validate_training_ics_archive() {
  ICS_LEVEL_STR="$(printf '%03d' "${SHA3_TRAINING_ICS_LEVEL:-10}")"
  ICS_ZIP="${PROJECT_DIR}/0002_detection/Code_extract_ics/ics_original_${ICS_LEVEL_STR}.zip"

  if [ ! -f "${ICS_CHECK_SCRIPT}" ]; then
    echo "Error: ICS check script not found: ${ICS_CHECK_SCRIPT}" >&2
    exit 1
  fi

  if [ ! -f "${ICS_ZIP}" ]; then
    echo "Error: ICS archive not found: ${ICS_ZIP}" >&2
    exit 1
  fi

  log "CHECK: validating training ICS archive (level=${ICS_LEVEL_STR})"
  python3 "${ICS_CHECK_SCRIPT}" \
    --ics-zip "${ICS_ZIP}" \
    --round-count "${SHA3_DETECTION_ROUNDS:-4}" \
    --ab-words "${SHA3_DETECTION_ICS_WORDS_AB:-50}" \
    --cd-words "${SHA3_DETECTION_ICS_WORDS_CD:-10}" \
    --max-empty 0 \
    --max-missing 0
}

zip_sim_dirs() {
  BASE_DIR="$1"
  PREFIX="$2"

  if [ ! -d "${BASE_DIR}" ]; then
    echo "Error: simulation output directory does not exist: ${BASE_DIR}" >&2
    exit 1
  fi

  find "${BASE_DIR}" -maxdepth 1 -type f -name "${PREFIX}_*.zip" -delete

  for d in "${BASE_DIR}/${PREFIX}_"*/; do
    if [ ! -d "$d" ]; then
      continue
    fi
    folder_name="$(basename "$d")"
    (
      cd "${BASE_DIR}"
      zip -qr "${folder_name}.zip" "${folder_name}"
    )
  done
}

move_zips_to_raw() {
  SRC_DIR="$1"
  PREFIX="$2"
  DEST_DIR="$3"

  mkdir -p "${DEST_DIR}"
  find "${DEST_DIR}" -maxdepth 1 -type f -name "${PREFIX}_*.zip" -delete

  moved=0
  for z in "${SRC_DIR}/${PREFIX}_"*.zip; do
    if [ ! -f "$z" ]; then
      continue
    fi
    cp "$z" "${DEST_DIR}/"
    if [ "$KEEP_LOCAL_ZIPS" -eq 0 ]; then
      rm -f "$z"
    fi
    moved=1
  done

  if [ "$moved" -eq 0 ]; then
    echo "Error: no zip files found for ${PREFIX} in ${SRC_DIR}" >&2
    exit 1
  fi
}

simulate_group() {
  GROUP="$1"
  FOLDERS="$2"
  TRACES_PER_FOLDER="$3"
  SEED="$4"

  if [ "$FOLDERS" -le 0 ]; then
    echo "Error: folder count for ${GROUP} must be > 0" >&2
    exit 1
  fi
  if [ "$TRACES_PER_FOLDER" -le 0 ]; then
    echo "Error: traces per folder for ${GROUP} must be > 0" >&2
    exit 1
  fi

  BASE_DIR="${TRACES_DIR}/Raw_${GROUP}"
  INDEX_DIR="${TRACES_DIR}/Raw_${GROUP}_indexes"
  mkdir -p "${BASE_DIR}" "${INDEX_DIR}"

  # SIM_PBW_SHARED is opt-in (legacy collapsed-pbw mode). Recognised truthy
  # values: 1, true, yes, on. Anything else (including unset and "0") leaves
  # the simulator in default per-leakage-point F_9 mode.
  PBW_SHARED_FLAG=""
  case "${SIM_PBW_SHARED:-0}" in
    1|true|yes|on|TRUE|YES|ON) PBW_SHARED_FLAG="--pbw-shared" ;;
  esac

  log "SIM  : ${GROUP} (folders=${FOLDERS}, traces/folder=${TRACES_PER_FOLDER}, seed=${SEED})"
  python3 "${SIM_SCRIPT}" \
    --algorithm "${SIM_ALGORITHM:-sha3-512}" \
    --trace \
    --bulk-invocations "${SHA3_INVOCATIONS}" \
    --bulk-traces-per-folder "${TRACES_PER_FOLDER}" \
    --bulk-folders "${FOLDERS}" \
    --bulk-output-dir "${BASE_DIR}/Raw_${GROUP}_" \
    --bulk-index-dir "${INDEX_DIR}" \
    --trace-format "${SIM_TRACE_FORMAT:-bin}" \
    --trace-dtype "${SIM_TRACE_DTYPE:-float64}" \
    --bulk-data-format "${SIM_BULK_DATA_FORMAT:-hex}" \
    --noise-sigma "${SIM_NOISE_SIGMA:-0.01}" \
    --gain-jitter-sigma "${SIM_GAIN_JITTER_SIGMA:-0.001}" \
    --offset-jitter-sigma "${SIM_OFFSET_JITTER_SIGMA:-0.01}" \
    --smooth-window "${SIM_SMOOTH_WINDOW:-1}" \
    --bulk-seed "${SEED}" \
    --leakage-profile "${SIM_LEAKAGE_PROFILE:-full}" \
    --leakage-granularity "${SIM_LEAKAGE_GRANULARITY:-word}" \
    --seed-pbw "${SIM_SEED_PBW:-2839}" \
    --pbw-c8-range "${SIM_PBW_C8_RANGE:-0.5}" \
    ${PBW_SHARED_FLAG} \
    --common-wave-scope "${SIM_COMMON_WAVE_SCOPE:-invocation}" \
    --hw-ratio "${SIM_HW_RATIO:-0.65}"

  log "ZIP  : ${GROUP}"
  zip_sim_dirs "${BASE_DIR}" "Raw_${GROUP}"

  case "${GROUP}" in
    RE)
      DEST="${PROJECT_DIR}/0001_reference/Raw"
      ;;
    DN)
      DEST="${PROJECT_DIR}/0002_detection/Raw"
      ;;
    TR)
      DEST="${PROJECT_DIR}/0003_training/Raw"
      ;;
    TS)
      DEST="${PROJECT_DIR}/0004_validation/Raw"
      ;;
    *)
      echo "Error: unsupported group: ${GROUP}" >&2
      exit 1
      ;;
  esac

  log "MOVE : ${GROUP} -> ${DEST}"
  move_zips_to_raw "${BASE_DIR}" "Raw_${GROUP}" "${DEST}"
}

if [ "$SKIP_SIM" -eq 0 ]; then
  log "INFO : using TRACES_DIR=${TRACES_DIR}"
  simulate_group "RE" "${SHA3_REFERENCE_FOLDERS}" "${SHA3_INPUTS}" "${SIM_SEED_RE:-128}"
  simulate_group "DN" "${SHA3_DETECTION_SET_COUNT}" "${SHA3_INPUTS}" "${SIM_SEED_DN:-256}"
  simulate_group "TR" "${SHA3_TRAINING_SET_COUNT}" "${SHA3_INPUTS}" "${SIM_SEED_TR:-512}"
  simulate_group "TS" "${SHA3_VALIDATION_SET_COUNT}" "${SHA3_VALIDATION_INPUTS}" "${SIM_SEED_TS:-1024}"
fi

if [ "$SKIP_CHAIN" -eq 0 ]; then
  run_stage "0001 reference" "0001_reference/Code_reference"

  run_stage "0002 detection preprocessing" "0002_detection/Code_preprocessing"
  run_stage "0002 detection intermediate values" "0002_detection/Code_intermediate_values"
  run_stage "0002 detection R2" "0002_detection/Code_detection_R2"
  run_stage "0002 detection ICS extraction" "0002_detection/Code_extract_ics"
  validate_training_ics_archive

  run_stage "0003 training preprocessing" "0003_training/Code_preprocessing"
  run_stage "0003 training intermediate values" "0003_training/Code_intermediate_values"
  run_stage "0003 training IoPs" "0003_training/Code_find_IoPs"
  run_stage "0003 training template profiling" "0003_training/template_profiling_bytes"

  run_stage "0004 validation preprocessing" "0004_validation/Code_preprocessing"
  run_stage "0004 validation intermediate values" "0004_validation/Code_intermediate_values"
  run_stage "0004 validation template validation" "0004_validation/template_validation_bytes"

  if [ -f "${PROJECT_DIR}/0004_validation/template_validation_bytes/Result_Tables.zip" ]; then
    log "INFO : generating validation quality report"
    (
      cd "${PROJECT_DIR}/0004_validation/template_validation_bytes"
      python3 analyze_result_tables_zip.py Result_Tables.zip --out quality_report
    )
  fi

  run_stage "0005 SASCA answers" "0005_SASCA/get_answers"
  run_stage "0005 SASCA bit tables" "0005_SASCA/bit_table_generation"

  if [ "${PARALLEL_SCANS}" -eq 1 ]; then
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
  else
    run_stage "0005 SASCA iteration scan 2R" "0005_SASCA/Iteration_Scan_2R"
    run_stage "0005 SASCA iteration scan 3R" "0005_SASCA/Iteration_Scan_3R"
    run_stage "0005 SASCA iteration scan 4R" "0005_SASCA/Iteration_Scan_4R"
    run_stage "0005 SASCA rate scan 2R" "0005_SASCA/Rate_Scan_2R"
    run_stage "0005 SASCA rate scan 3R" "0005_SASCA/Rate_Scan_3R"
    run_stage "0005 SASCA rate scan 4R" "0005_SASCA/Rate_Scan_4R"
  fi

  run_stage "0005 SASCA plot scans" "0005_SASCA/plot_scans"
fi

log "COMPLETE: run_full_pipeline finished"
