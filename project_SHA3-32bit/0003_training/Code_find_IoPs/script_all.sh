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
"${PYTHON_BIN}" get_IoPs.py 0
"${PYTHON_BIN}" get_IoPs.py 1
"${PYTHON_BIN}" get_IoPs.py 2
"${PYTHON_BIN}" get_IoPs.py 3
./pack.sh
