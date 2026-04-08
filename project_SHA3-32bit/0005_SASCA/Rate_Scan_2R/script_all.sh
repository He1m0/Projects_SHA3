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
./init.sh
"${PYTHON_BIN}" Rate_scan.py ${lower} ${upper}
"${PYTHON_BIN}" get_results.py ${lower} ${upper}
./pack.sh
