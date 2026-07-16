#!/usr/bin/env sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)"

if [ -x "${PROJECT_DIR}/../.venv/bin/python" ]; then
	PYTHON_BIN="${PROJECT_DIR}/../.venv/bin/python"
else
	PYTHON_BIN="python3"
fi

cd "${SCRIPT_DIR}"

./init.sh
# get_IoPs.py's numpy calls fan out to ~1 BLAS thread per core by default
# (same mechanism as Code_detection_R2's detect_script.py -- see that
# script_all.sh for the incident this guards against). Capped so multiple
# IoP-discovery stages can run concurrently without oversubscribing the
# host.
export OMP_NUM_THREADS="${SHA3_R2_THREADS:-4}"
export OPENBLAS_NUM_THREADS="${SHA3_R2_THREADS:-4}"
export MKL_NUM_THREADS="${SHA3_R2_THREADS:-4}"
export NUMEXPR_NUM_THREADS="${SHA3_R2_THREADS:-4}"
export VECLIB_MAXIMUM_THREADS="${SHA3_R2_THREADS:-4}"
"${PYTHON_BIN}" get_IoPs.py 0
"${PYTHON_BIN}" get_IoPs.py 1
"${PYTHON_BIN}" get_IoPs.py 2
"${PYTHON_BIN}" get_IoPs.py 3
./pack.sh
