#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHONPATH_CFG="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

if [ -x "${ROOT_DIR}/../.venv/bin/python" ]; then
	PYTHON_BIN="${ROOT_DIR}/../.venv/bin/python"
else
	PYTHON_BIN="python3"
fi

cd "${SCRIPT_DIR}"

lower=0
upper=$(PYTHONPATH="${PYTHONPATH_CFG}" "${PYTHON_BIN}" -c "import global_config as cfg; print(cfg.TRAINING_SET_COUNT)")
sets_per_part=$(PYTHONPATH="${PYTHONPATH_CFG}" "${PYTHON_BIN}" -c "import global_config as cfg; print(cfg.TRAINING_SETS_PER_PART)")
corr_bound=$(PYTHONPATH="${PYTHONPATH_CFG}" "${PYTHON_BIN}" -c "import global_config as cfg; print(cfg.TRAINING_CORR_BOUND)")
part=$(( (upper + sets_per_part - 1) / sets_per_part ))
mkdir -p ../Processed_HDF5/
mkdir -p Corrcoefs/
mkdir -p data_raw_in/
mkdir -p data_raw_out/
"${PYTHON_BIN}" pre_processing.py ${lower} ${upper}
"${PYTHON_BIN}" check_corr.py ${corr_bound} ${lower} ${upper}
"${PYTHON_BIN}" check_corr.py ${corr_bound} ${lower} ${upper} > check_report.txt
zip Corrcoefs.zip -r Corrcoefs/
zip data_raw_in.zip -r data_raw_in/
zip data_raw_out.zip -r data_raw_out/
rm -r Corrcoefs/ data_raw_in/ data_raw_out/ __pycache__/
"${PYTHON_BIN}" combine.py combine 0 ${part}
"${PYTHON_BIN}" combine.py check 0 ${part}
"${PYTHON_BIN}" combine.py check 0 ${part} >> check_report.txt
rm ../Processed_HDF5/Processed_*.hdf5
