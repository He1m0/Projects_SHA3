#!/usr/bin/env sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)"

if [ -x "${PROJECT_DIR}/../.venv/bin/python" ]; then
	PYTHON_BIN="${PROJECT_DIR}/../.venv/bin/python"
else
	PYTHON_BIN="python3"
fi

ICS_LEVEL="$(${PYTHON_BIN} -c "import sys; sys.path.insert(0, '${PROJECT_DIR}'); import global_config as cfg; print(str(cfg.TRAINING_ICS_LEVEL).zfill(3))")"
ICS_ZIP="${SCRIPT_DIR}/../../0002_detection/Code_extract_ics/ics_original_${ICS_LEVEL}.zip"

if [ ! -f "${ICS_ZIP}" ]; then
	echo "Missing ICS archive: ${ICS_ZIP}" >&2
	echo "Generate it first in 0002_detection/Code_extract_ics (threshold ${ICS_LEVEL})." >&2
	exit 1
fi

cd "${SCRIPT_DIR}"
unzip -oq "${ICS_ZIP}"
mkdir -p IoPs/
