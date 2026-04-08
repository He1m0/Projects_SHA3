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
PARTS="$(${PYTHON_BIN} -c "import sys; sys.path.insert(0, '${PROJECT_DIR}'); import global_config as cfg; print(cfg.VALIDATION_PART_COUNT)")"

cd "${SCRIPT_DIR}"
unzip -oq Rank_O${TEMPLATE_TAG}.zip
mkdir -p Result_Tables/
"${PYTHON_BIN}" draw_all.py "${PARTS}"
zip -q -r Result_Tables.zip Result_Tables/
rm -rf Rank_O*/ Result_Tables/
