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
"$PYTHON" -W ignore Template_profiling_round.py 0
"$PYTHON" -W ignore Template_profiling_round.py 1
"$PYTHON" -W ignore Template_profiling_round.py 2
"$PYTHON" -W ignore Template_profiling_round.py 3
./pack.sh

