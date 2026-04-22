#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

PROJ_DIR="$SCRIPT_DIR"
while [ ! -f "$PROJ_DIR/global_config.py" ] && [ "$PROJ_DIR" != "/" ]; do
  PROJ_DIR="$(dirname "$PROJ_DIR")"
done

if [ -f "$PROJ_DIR/.env" ]; then
  set -a
  . "$PROJ_DIR/.env"
  set +a
fi

TEMPLATE_TAG="$(printf '%03d' "${SHA3_VALIDATION_TEMPLATE_TAG:-10}")"

cd "$SCRIPT_DIR"

rm -rf __pycache__/ intermediate_values/ "templateLDA_O${TEMPLATE_TAG}"*
