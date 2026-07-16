SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}" || exit 1

lower=0
upper=$(python3 - <<'PY'
import os
import sys
sys.path.append(os.path.abspath('../../'))
import global_config as gc
print(gc.SASCA_TRACE_COUNT)
PY
)
PYTHON_BIN="../../../.venv/bin/python"
if [ ! -x "${PYTHON_BIN}" ]; then
	PYTHON_BIN="../../../venv/bin/python"
fi
if [ ! -x "${PYTHON_BIN}" ]; then
	PYTHON_BIN="../../.venv/bin/python"
fi
if [ ! -x "${PYTHON_BIN}" ]; then
	PYTHON_BIN="../../venv/bin/python"
fi
if [ ! -x "${PYTHON_BIN}" ]; then
	PYTHON_BIN="python3"
fi

# Iteration_scan.py/Rate_scan.py's numpy calls fan out to ~1 BLAS thread
# per core by default (same mechanism as Code_detection_R2's
# detect_script.py -- see that script_all.sh for the incident this
# guards against). Capped so multiple SASCA stages can run concurrently
# without oversubscribing the host.
export OMP_NUM_THREADS="${SHA3_R2_THREADS:-4}"
export OPENBLAS_NUM_THREADS="${SHA3_R2_THREADS:-4}"
export MKL_NUM_THREADS="${SHA3_R2_THREADS:-4}"
export NUMEXPR_NUM_THREADS="${SHA3_R2_THREADS:-4}"
export VECLIB_MAXIMUM_THREADS="${SHA3_R2_THREADS:-4}"
./init.sh
"${PYTHON_BIN}" Rate_scan.py ${lower} ${upper}
"${PYTHON_BIN}" get_results.py ${lower} ${upper}
./pack.sh
