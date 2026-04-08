SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}" || exit 1

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
"${PYTHON_BIN}" plot_SR_over_Rates.py
"${PYTHON_BIN}" plot_SR_over_Iterations.py
