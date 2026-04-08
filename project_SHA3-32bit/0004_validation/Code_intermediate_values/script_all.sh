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
mkdir -p intermediate_values/
mkdir -p Invocation_IO/
unzip -oq ../Code_preprocessing/data_raw_in.zip
unzip -oq ../Code_preprocessing/data_raw_out.zip
"${PYTHON_BIN}" get_invoc_io.py cal
"${PYTHON_BIN}" get_invoc_io.py check
"${PYTHON_BIN}" get_invoc_io.py check > check_report_IO.txt
"${PYTHON_BIN}" get_invoc_intermediate.py
"${PYTHON_BIN}" intermediate_H2B.py cal
"${PYTHON_BIN}" intermediate_H2B.py check
"${PYTHON_BIN}" intermediate_H2B.py check > check_report_bytes.txt
zip -q -r Invocation_IO.zip Invocation_IO/
zip -q -r intermediate_values.zip intermediate_values/
rm -rf data_raw_in/ data_raw_out/ Invocation_IO/ intermediate_values/ __pycache__/

