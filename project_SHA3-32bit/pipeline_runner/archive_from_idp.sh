#!/usr/bin/env sh
#
# Stage a minimal local mirror of a completed pipeline run's sandbox on a
# remote host (IDP) and archive it via the existing archive_run.sh.
#
# archive_run.sh only operates on a local project_SHA3-32bit/ tree (it
# resolves PROJECT_DIR relative to its own invocation location, no SSH
# support). This script rsyncs just the files archive_run.sh actually reads
# into a temp tree shaped like project_SHA3-32bit/, copies the local
# (version-controlled) archive_run.sh into it, and runs it from there.
#
# Usage:
#   sh archive_from_idp.sh --version smoke_v6 --mode f9 --sigma 0.1
#   sh archive_from_idp.sh --version smoke_v6 --mode id --sigma 1.5 --force

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)"

VERSION=""
MODE=""
SIGMA=""
REMOTE_HOST="IDP"
REMOTE_BASE="/storage/ge96pug"
OUT_DIR=""
FORCE=0
KEEP_TMP=0

print_help() {
  sed -n '2,/^set -eu/{ /^set -eu/d; s/^# \{0,1\}//; p }' "$0"
  exit 0
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version)      VERSION="$2"; shift 2 ;;
    --mode)         MODE="$2"; shift 2 ;;
    --sigma)        SIGMA="$2"; shift 2 ;;
    --remote-host)  REMOTE_HOST="$2"; shift 2 ;;
    --remote-base)  REMOTE_BASE="$2"; shift 2 ;;
    --out-dir)      OUT_DIR="$2"; shift 2 ;;
    --force)        FORCE=1; shift ;;
    --keep-tmp)     KEEP_TMP=1; shift ;;
    -h|--help)      print_help ;;
    *) echo "Unknown arg: $1" >&2; print_help; exit 2 ;;
  esac
done

if [ -z "${VERSION}" ] || [ -z "${MODE}" ] || [ -z "${SIGMA}" ]; then
  echo "Error: --version, --mode, and --sigma are required" >&2
  exit 2
fi

SIGMA_STR="$(printf '%s' "${SIGMA}" | sed 's/\./p/')"
SANDBOX_NAME="Projects_SHA3_sandbox_${VERSION}_${MODE}_sigma${SIGMA_STR}"
RUN_NAME="${VERSION}_${MODE}_sigma${SIGMA_STR}"
REMOTE_PROJECT="${REMOTE_HOST}:${REMOTE_BASE}/${SANDBOX_NAME}/project_SHA3-32bit"

[ -z "${OUT_DIR}" ] && OUT_DIR="${REPO_ROOT}/project_SHA3-32bit/pipeline_runner/runs_archive/${VERSION}"

TMPDIR_STAGE="$(mktemp -d)"
cleanup() {
  if [ "${KEEP_TMP}" -eq 0 ]; then
    rm -rf "${TMPDIR_STAGE}"
  else
    echo "Kept staging dir: ${TMPDIR_STAGE}"
  fi
}
trap cleanup EXIT

STAGE="${TMPDIR_STAGE}/project_SHA3-32bit"
mkdir -p \
  "${STAGE}/pipeline_runner" \
  "${STAGE}/0003_training/template_profiling_bytes" \
  "${STAGE}/0004_validation/template_validation_bytes" \
  "${STAGE}/0005_SASCA/Iteration_Scan_2R" \
  "${STAGE}/0005_SASCA/Iteration_Scan_3R" \
  "${STAGE}/0005_SASCA/Iteration_Scan_4R" \
  "${STAGE}/0005_SASCA/Rate_Scan_2R" \
  "${STAGE}/0005_SASCA/Rate_Scan_3R" \
  "${STAGE}/0005_SASCA/Rate_Scan_4R" \
  "${STAGE}/0005_SASCA/get_answers"

echo "=== Archiving ${RUN_NAME} from ${REMOTE_HOST} ==="

# --- .env: prefer the local repo's env profile (byte-identical, no network) ---
LOCAL_ENV="${REPO_ROOT}/project_SHA3-32bit/pipeline_runner/envs/${VERSION}_sigma_sweep/.env_${VERSION}_${MODE}_sigma${SIGMA_STR}"
if [ -f "${LOCAL_ENV}" ]; then
  cp "${LOCAL_ENV}" "${STAGE}/.env"
  echo "  .env: copied from local repo profile"
else
  echo "  .env: local profile not found (${LOCAL_ENV}), falling back to remote rsync"
  rsync -a "${REMOTE_PROJECT}/.env" "${STAGE}/.env"
fi

# --- global_config.py: differs per run, must come from remote ---
rsync -a "${REMOTE_PROJECT}/global_config.py" "${STAGE}/global_config.py"

# --- 0003_training/template_profiling_bytes: whole dir (archive_run.sh does ls -lR on it) ---
rsync -a "${REMOTE_PROJECT}/0003_training/template_profiling_bytes/" \
         "${STAGE}/0003_training/template_profiling_bytes/"

# --- 0004_validation: Result_Tables.zip + quality_report/ ---
rsync -a "${REMOTE_PROJECT}/0004_validation/template_validation_bytes/Result_Tables.zip" \
         "${STAGE}/0004_validation/template_validation_bytes/Result_Tables.zip" || \
  echo "  warn: Result_Tables.zip not found on remote"
rsync -a "${REMOTE_PROJECT}/0004_validation/template_validation_bytes/quality_report/" \
         "${STAGE}/0004_validation/template_validation_bytes/quality_report/" || \
  echo "  warn: quality_report/ not found on remote"

# --- 0005_SASCA: Iteration_Scan_{2,3,4}R, Rate_Scan_{2,3,4}R (summary + Predictions) ---
for R in 2R 3R 4R; do
  rsync -a "${REMOTE_PROJECT}/0005_SASCA/Iteration_Scan_${R}/iteration_scan_${R}_B.npy" \
           "${STAGE}/0005_SASCA/Iteration_Scan_${R}/" || \
    echo "  warn: iteration_scan_${R}_B.npy not found on remote"
  rsync -a "${REMOTE_PROJECT}/0005_SASCA/Rate_Scan_${R}/rate_scan_${R}_B.npy" \
           "${STAGE}/0005_SASCA/Rate_Scan_${R}/" || \
    echo "  warn: rate_scan_${R}_B.npy not found on remote"
  rsync -a "${REMOTE_PROJECT}/0005_SASCA/Rate_Scan_${R}/Predictions/" \
           "${STAGE}/0005_SASCA/Rate_Scan_${R}/Predictions/" 2>/dev/null || \
    echo "  note: Rate_Scan_${R}/Predictions/ not present on remote (skipped)"
done

# --- ground truth: get_answers/answer_bit.zip (archive_run.sh unzips it itself) ---
rsync -a "${REMOTE_PROJECT}/0005_SASCA/get_answers/answer_bit.zip" \
         "${STAGE}/0005_SASCA/get_answers/answer_bit.zip" || \
  echo "  warn: answer_bit.zip not found on remote"

# --- run the local, version-controlled archive_run.sh from inside the staged tree ---
cp "${SCRIPT_DIR}/archive_run.sh" "${STAGE}/pipeline_runner/archive_run.sh"

( cd "${STAGE}/pipeline_runner" && \
  sh archive_run.sh \
    --name "${RUN_NAME}" \
    --out-dir "${OUT_DIR}" \
    $( [ "${FORCE}" -eq 1 ] && echo --force ) )

echo "=== Done: ${RUN_NAME} ==="
