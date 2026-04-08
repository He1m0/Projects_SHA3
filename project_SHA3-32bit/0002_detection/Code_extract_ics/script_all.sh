set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHONPATH_CFG="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

if [ -x "${ROOT_DIR}/../.venv/bin/python" ]; then
	PYTHON_BIN="${ROOT_DIR}/../.venv/bin/python"
else
	PYTHON_BIN="python3"
fi

cd "${SCRIPT_DIR}"

unzip ../Code_detection_R2/detect_results_32.zip

if ! find detect_results_32 -type f -name '*.npy' -print -quit | grep -q .; then
	echo "Error: detect_results_32.zip contains no .npy result files."
	exit 1
fi

mkdir Tables/
thresholds=$(PYTHONPATH="${PYTHONPATH_CFG}" "${PYTHON_BIN}" -c "import global_config as cfg; print(' '.join(str(x) for x in cfg.DETECTION_ICS_THRESHOLDS))")
for bnd in ${thresholds}; do
	"${PYTHON_BIN}" ics_detect.py "${bnd}"
done
"${PYTHON_BIN}" draw_tables.py
zip -qq Tables.zip -r Tables/
rm -r detect_results_*/ Tables/
