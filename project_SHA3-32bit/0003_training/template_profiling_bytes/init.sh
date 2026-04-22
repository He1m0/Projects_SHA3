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
DETECTION_ROUNDS="${SHA3_DETECTION_ROUNDS:-4}"

cd "$SCRIPT_DIR"

unzip -oq ../Code_intermediate_values/intermediate_values.zip

mkdir -p "templateLDA_O${TEMPLATE_TAG}"
rd=0
while [ "$rd" -lt "$DETECTION_ROUNDS" ]; do
  rd_tag="$(printf '%02d' "$rd")"
  for fam in A B C D; do
    mkdir -p "templateLDA_O${TEMPLATE_TAG}/template_${fam}${rd_tag}"
  done
  rd=$((rd+1))
done
