#!/usr/bin/env sh
#
# Snapshot a completed-or-killed pipeline run into runs_archive/<date>_<label>/
# so it can be compared against other runs with compare_runs.py.
#
# Captures only what is needed for comparison: the env used, the quality
# report from 0004, Iteration_Scan/Rate_Scan partial results from 0005, and
# (optionally) a gzipped run log. Heavy artifacts (HDF5, Raw zips, templateLDA)
# are intentionally excluded — the point of the archive is quick re-plotting,
# not bit-exact reruns.

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"

print_help() {
  cat <<'EOF'
Usage:
  sh archive_run.sh --name LABEL [options]

Required:
  --name LABEL       Short human label for this run (appended to date prefix).

Options:
  --env-file PATH    Env profile to archive alongside the run.
                     Default: $PROJECT_DIR/.env (the file the pipeline sourced).
  --log PATH         Log file to gzip into the archive. Default: none.
  --note TEXT        One-line note for the README (status / context).
  --out-dir PATH     Destination parent dir. Default: pipeline_runner/runs_archive
  --force            Overwrite if the destination already exists.
  -h, --help         Show this help.

What gets archived:
  pipeline_runner/<env>                 # the env file used
  pipeline_runner/global_config.py      # snapshot of defaults
  log/<basename>.gz                     # if --log given
  0004_validation/quality_report/       # report.txt + 3 CSVs (regenerated
                                        # from Result_Tables.zip if missing)
  0004_validation/Result_Tables.zip     # if present
  0005_SASCA/Iteration_Scan/iteration_scan_{2,3,4}R_B.npy
  0005_SASCA/Rate_Scan/{2,3,4}R_Success/success_????.npy
  0003_training/profiling_bytes_listing.txt
  README.md                             # timestamp + progress + one-line verdict

The script is idempotent: rerunning with --force on the same data reproduces
the same archive (modulo timestamps in README).
EOF
}

NAME=""
ENV_FILE="${PROJECT_DIR}/.env"
LOG_FILE=""
NOTE=""
OUT_DIR="${SCRIPT_DIR}/runs_archive"
FORCE=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --name)      NAME="$2"; shift 2 ;;
    --env-file)  ENV_FILE="$2"; shift 2 ;;
    --log)       LOG_FILE="$2"; shift 2 ;;
    --note)      NOTE="$2"; shift 2 ;;
    --out-dir)   OUT_DIR="$2"; shift 2 ;;
    --force)     FORCE=1; shift ;;
    -h|--help)   print_help; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; print_help; exit 2 ;;
  esac
done

if [ -z "${NAME}" ]; then
  echo "Error: --name is required" >&2
  exit 2
fi

STAMP="$(date +%Y-%m-%d)"
DEST="${OUT_DIR}/${STAMP}_${NAME}"

if [ -e "${DEST}" ]; then
  if [ "${FORCE}" -eq 1 ]; then
    rm -rf "${DEST}"
  else
    echo "Error: ${DEST} already exists (pass --force to overwrite)" >&2
    exit 3
  fi
fi

mkdir -p "${DEST}/pipeline_runner" \
         "${DEST}/0003_training" \
         "${DEST}/0004_validation" \
         "${DEST}/0005_SASCA/Iteration_Scan" \
         "${DEST}/0005_SASCA/Rate_Scan" \
         "${DEST}/log"

# --- env + global_config ---
if [ -f "${ENV_FILE}" ]; then
  cp "${ENV_FILE}" "${DEST}/pipeline_runner/$(basename "${ENV_FILE}")"
  echo "archived env: $(basename "${ENV_FILE}")"
else
  echo "warn: env file not found at ${ENV_FILE}"
fi

if [ -f "${PROJECT_DIR}/global_config.py" ]; then
  cp "${PROJECT_DIR}/global_config.py" "${DEST}/pipeline_runner/"
fi

# --- log ---
if [ -n "${LOG_FILE}" ]; then
  if [ -f "${LOG_FILE}" ]; then
    gzip -c "${LOG_FILE}" > "${DEST}/log/$(basename "${LOG_FILE}").gz"
    echo "archived log: $(basename "${LOG_FILE}").gz"
  else
    echo "warn: --log path not found: ${LOG_FILE}"
  fi
fi

# --- 0004 Result_Tables.zip + quality_report ---
RT_ZIP="${PROJECT_DIR}/0004_validation/template_validation_bytes/Result_Tables.zip"
QR_SRC="${PROJECT_DIR}/0004_validation/template_validation_bytes/quality_report"
QR_DEST="${DEST}/0004_validation/quality_report"

if [ -f "${RT_ZIP}" ]; then
  cp "${RT_ZIP}" "${DEST}/0004_validation/Result_Tables.zip"
  echo "archived: Result_Tables.zip"
fi

if [ -d "${QR_SRC}" ]; then
  cp -r "${QR_SRC}" "${QR_DEST}"
  echo "archived: quality_report/ (existing)"
elif [ -f "${RT_ZIP}" ]; then
  # Regenerate if the zip is there but the report isn't
  ANALYZER="${PROJECT_DIR}/0004_validation/template_validation_bytes/analyze_result_tables_zip.py"
  if [ -f "${ANALYZER}" ]; then
    if [ -x "${PROJECT_DIR}/../.venv/bin/python" ]; then PY="${PROJECT_DIR}/../.venv/bin/python"
    elif [ -x "${PROJECT_DIR}/../venv/bin/python" ]; then PY="${PROJECT_DIR}/../venv/bin/python"
    else PY="python3"
    fi
    mkdir -p "${QR_DEST}"
    "${PY}" "${ANALYZER}" "${RT_ZIP}" --out "${QR_DEST}" > /dev/null
    echo "archived: quality_report/ (regenerated via analyze_result_tables_zip.py)"
  fi
fi

# --- 0005 Iteration_Scan ---
for R in 2R 3R 4R; do
  F="${PROJECT_DIR}/0005_SASCA/Iteration_Scan_${R}/iteration_scan_${R}_B.npy"
  if [ -f "${F}" ]; then
    cp "${F}" "${DEST}/0005_SASCA/Iteration_Scan/"
  fi
done

# --- 0005 Rate_Scan: summary npy + (if present) per-trace Success/ ---
RATE_COUNTS=""
for R in 2R 3R 4R; do
  SCAN="${PROJECT_DIR}/0005_SASCA/Rate_Scan_${R}"
  OUT="${DEST}/0005_SASCA/Rate_Scan/${R}_Success"
  SUMMARY="${SCAN}/rate_scan_${R}_B.npy"
  if [ -f "${SUMMARY}" ]; then
    mkdir -p "${DEST}/0005_SASCA/Rate_Scan"
    cp "${SUMMARY}" "${DEST}/0005_SASCA/Rate_Scan/"
  fi
  SUCC="${SCAN}/Success"
  if [ -d "${SUCC}" ] && [ -n "$(ls -A "${SUCC}" 2>/dev/null || true)" ]; then
    mkdir -p "${OUT}"
    cp -r "${SUCC}/." "${OUT}/"
    N=$(ls "${OUT}" 2>/dev/null | wc -l | tr -d ' ')
    RATE_COUNTS="${RATE_COUNTS}${R}/Success=${N}  "
  elif [ -f "${SUMMARY}" ]; then
    RATE_COUNTS="${RATE_COUNTS}${R}=summary  "
  fi
done

# --- 0003 profiling listing ---
PROF_DIR="${PROJECT_DIR}/0003_training/template_profiling_bytes"
if [ -d "${PROF_DIR}" ]; then
  ls -lR "${PROF_DIR}" > "${DEST}/0003_training/profiling_bytes_listing.txt" 2>/dev/null || true
fi

# --- README ---
BEST_WORST=""
CSV="${QR_DEST}/summary_family_round.csv"
if [ -f "${CSV}" ]; then
  # best = max combined_score_avg, worst = min
  # columns: family_round,groups,sr_mean_avg,ge_mean_avg,combined_score_avg,best_label,worst_label
  BEST=$(tail -n +2 "${CSV}" | awk -F',' 'NF>=5 {printf "%s %.4f %.2f %.4f %s\n",$1,$3,$4,$5,$6}' | sort -k4 -g -r | head -1 || true)
  WORST=$(tail -n +2 "${CSV}" | awk -F',' 'NF>=5 {printf "%s %.4f %.2f %.4f %s\n",$1,$3,$4,$5,$7}' | sort -k4 -g       | head -1 || true)
  BEST_WORST="best  (by score): ${BEST}
worst (by score): ${WORST}
(fmt: family_round  SR_mean  GE_mean  score  label)"
fi

{
  echo "# Run snapshot — ${STAMP} — ${NAME}"
  echo
  echo "Captured at: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  if [ -n "${NOTE}" ]; then
    echo
    echo "**Note:** ${NOTE}"
  fi
  echo
  echo "## Env"
  echo "  - env file: $(basename "${ENV_FILE}")"
  if [ -n "${LOG_FILE}" ]; then
    echo "  - log:      $(basename "${LOG_FILE}").gz"
  fi
  echo
  echo "## Rate_Scan progress (success_*.npy count per depth, target = SHA3_SASCA_TRACE_COUNT)"
  if [ -n "${RATE_COUNTS}" ]; then
    echo "  - ${RATE_COUNTS}"
  else
    echo "  - (no Rate_Scan results captured)"
  fi
  echo
  echo "## Template quality (from 0004 quality_report)"
  if [ -n "${BEST_WORST}" ]; then
    echo '```'
    printf '%s\n' "${BEST_WORST}"
    echo '```'
  else
    echo "  - (no quality_report captured)"
  fi
  echo
  echo "## Layout"
  echo '```'
  echo "pipeline_runner/        -- env file + global_config.py"
  echo "log/                    -- run log (gzipped) if --log was given"
  echo "0003_training/          -- template_profiling_bytes listing (not the templates)"
  echo "0004_validation/        -- Result_Tables.zip + quality_report/"
  echo "0005_SASCA/             -- Iteration_Scan/*.npy + Rate_Scan/{2,3,4}R_Success/"
  echo '```'
} > "${DEST}/README.md"

echo
echo "archive written: ${DEST}"
du -sh "${DEST}"
