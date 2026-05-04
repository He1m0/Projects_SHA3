#!/usr/bin/env sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"

WITH_TRAINING=0

print_help() {
  cat <<'EOF'
Usage:
  sh run_overnight_chain.sh [--with-training]

Options:
  --with-training   Run 0003 training stages before validation/SASCA.
                    By default, the script starts at 0004 validation.
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  print_help
  exit 0
fi

if [ "${1:-}" = "--with-training" ]; then
  WITH_TRAINING=1
fi

run_stage() {
  LABEL="$1"
  REL_DIR="$2"

  echo "============================================================"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] START: ${LABEL}"
  (
    cd "${PROJECT_DIR}/${REL_DIR}"
    ./script_all.sh
  )
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] DONE : ${LABEL}"
}

if [ "$WITH_TRAINING" -eq 1 ]; then
  run_stage "0003 training preprocessing" "0003_training/Code_preprocessing"
  run_stage "0003 training intermediate values" "0003_training/Code_intermediate_values"
  run_stage "0003 training IoPs" "0003_training/Code_find_IoPs"
  run_stage "0003 training template profiling" "0003_training/template_profiling_bytes"
fi

run_stage "0004 validation preprocessing" "0004_validation/Code_preprocessing"
run_stage "0004 validation intermediate values" "0004_validation/Code_intermediate_values"
run_stage "0004 validation template evaluation" "0004_validation/template_validation_bytes"

# Optional quality report for quick morning inspection.
if [ -f "${PROJECT_DIR}/0004_validation/template_validation_bytes/Result_Tables.zip" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO : generating 0004 quality report"
  (
    cd "${PROJECT_DIR}/0004_validation/template_validation_bytes"
    python3 analyze_result_tables_zip.py Result_Tables.zip --out quality_report
  )
fi

run_stage "0005 answers extraction" "0005_SASCA/get_answers"
run_stage "0005 bit table generation" "0005_SASCA/bit_table_generation"
run_stage "0005 iteration scan 2R" "0005_SASCA/Iteration_Scan_2R"
run_stage "0005 iteration scan 3R" "0005_SASCA/Iteration_Scan_3R"
run_stage "0005 iteration scan 4R" "0005_SASCA/Iteration_Scan_4R"
run_stage "0005 rate scan 2R" "0005_SASCA/Rate_Scan_2R"
run_stage "0005 rate scan 3R" "0005_SASCA/Rate_Scan_3R"
run_stage "0005 rate scan 4R" "0005_SASCA/Rate_Scan_4R"
run_stage "0005 plot scans" "0005_SASCA/plot_scans"

echo "============================================================"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] COMPLETE: overnight chain finished"
