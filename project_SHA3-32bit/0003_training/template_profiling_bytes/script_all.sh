#!/usr/bin/env sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

PYTHON=""
SEARCH_DIR="$SCRIPT_DIR"
while [ "$SEARCH_DIR" != "/" ]; do
	if [ -x "$SEARCH_DIR/.venv/bin/python" ]; then
		PYTHON="$SEARCH_DIR/.venv/bin/python"
		break
	fi
	SEARCH_DIR="$(dirname "$SEARCH_DIR")"
done

if [ -z "$PYTHON" ]; then
	PYTHON="${PYTHON:-python3}"
fi

cd "$SCRIPT_DIR"

"$PYTHON" -c "import sklearn" >/dev/null 2>&1 || {
	echo "Missing dependency: scikit-learn is required for Template_profiling_round.py" >&2
	echo "Interpreter: $PYTHON" >&2
	exit 1
}

./init.sh
# Template_profiling_round.py's numpy/sklearn calls fan out to ~1 BLAS
# thread per core by default (same mechanism as Code_detection_R2's
# detect_script.py -- see that script_all.sh for the incident this guards
# against). Capped so multiple training stages can run concurrently without
# oversubscribing the host.
export OMP_NUM_THREADS="${SHA3_R2_THREADS:-4}"
export OPENBLAS_NUM_THREADS="${SHA3_R2_THREADS:-4}"
export MKL_NUM_THREADS="${SHA3_R2_THREADS:-4}"
export NUMEXPR_NUM_THREADS="${SHA3_R2_THREADS:-4}"
export VECLIB_MAXIMUM_THREADS="${SHA3_R2_THREADS:-4}"
"$PYTHON" -W ignore Template_profiling_round.py 0
"$PYTHON" -W ignore Template_profiling_round.py 1
"$PYTHON" -W ignore Template_profiling_round.py 2
"$PYTHON" -W ignore Template_profiling_round.py 3
./pack.sh

