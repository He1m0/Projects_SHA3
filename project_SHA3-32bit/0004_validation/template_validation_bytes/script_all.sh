#!/usr/bin/env sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)"

if [ -x "${PROJECT_DIR}/../.venv/bin/python" ]; then
	PYTHON_BIN="${PROJECT_DIR}/../.venv/bin/python"
else
	PYTHON_BIN="python3"
fi

TEMPLATE_TAG="$(${PYTHON_BIN} -c "import sys; sys.path.insert(0, '${PROJECT_DIR}'); import global_config as cfg; print(cfg.VALIDATION_TEMPLATE_TAG)")"
ICS_TAG="$(${PYTHON_BIN} -c "import sys; sys.path.insert(0, '${PROJECT_DIR}'); import global_config as cfg; print(cfg.VALIDATION_ICS_TAG)")"
PARTS="$(${PYTHON_BIN} -c "import sys; sys.path.insert(0, '${PROJECT_DIR}'); import global_config as cfg; print(cfg.VALIDATION_PART_COUNT)")"

cd "${SCRIPT_DIR}"
unzip -oq ../Code_intermediate_values/intermediate_values.zip
unzip -oq ../../0002_detection/Code_extract_ics/ics_original_${ICS_TAG}.zip
unzip -oq ../../0003_training/template_profiling_bytes/templateLDA_O${TEMPLATE_TAG}.zip
mkdir -p Rank_O${TEMPLATE_TAG}/
"${PYTHON_BIN}" validate_script.py 0 "${PARTS}"
zip -q -r Rank_O${TEMPLATE_TAG}.zip Rank_O${TEMPLATE_TAG}/
mkdir -p Result_Tables/
"${PYTHON_BIN}" draw_all.py "${PARTS}"
zip -q -r Result_Tables.zip Result_Tables/
rm -rf intermediate_values/ templateLDA_O*/ ics_*/ __pycache__/ Rank_O*/ Result_Tables/
