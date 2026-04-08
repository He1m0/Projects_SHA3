#!/usr/bin/env sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)"

if [ -x "${PROJECT_DIR}/../.venv/bin/python" ]; then
	PYTHON_BIN="${PROJECT_DIR}/../.venv/bin/python"
else
	PYTHON_BIN="python3"
fi

LOWER=0
UPPER="$(${PYTHON_BIN} -c "import sys; sys.path.insert(0, '${PROJECT_DIR}'); import global_config as cfg; print(cfg.VALIDATION_SET_COUNT)")"
PARTS="$(${PYTHON_BIN} -c "import sys; sys.path.insert(0, '${PROJECT_DIR}'); import global_config as cfg; print(cfg.VALIDATION_PART_COUNT)")"
CORR_BOUND="$(${PYTHON_BIN} -c "import sys; sys.path.insert(0, '${PROJECT_DIR}'); import global_config as cfg; print(cfg.VALIDATION_CORR_BOUND)")"

cd "${SCRIPT_DIR}"
mkdir -p ../Processed_HDF5/
mkdir -p Corrcoefs/
mkdir -p data_raw_in/
mkdir -p data_raw_out/
"${PYTHON_BIN}" pre_processing.py "${LOWER}" "${UPPER}"
"${PYTHON_BIN}" check_corr.py "${CORR_BOUND}" "${LOWER}" "${UPPER}"
"${PYTHON_BIN}" check_corr.py "${CORR_BOUND}" "${LOWER}" "${UPPER}" > check_report.txt
zip -q -r Corrcoefs.zip Corrcoefs/
zip -q -r data_raw_in.zip data_raw_in/
zip -q -r data_raw_out.zip data_raw_out/
rm -rf Corrcoefs/ data_raw_in/ data_raw_out/ __pycache__/
"${PYTHON_BIN}" combine.py combine 0 "${PARTS}"
"${PYTHON_BIN}" combine.py check 0 "${PARTS}"
"${PYTHON_BIN}" combine.py check 0 "${PARTS}" >> check_report.txt
rm -f ../Processed_HDF5/Processed_*.hdf5
