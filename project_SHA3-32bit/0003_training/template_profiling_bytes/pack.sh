#!/usr/bin/env sh

set -eu

zip templateLDA_O010.zip -r templateLDA_O010/
rm -rf __pycache__/ intermediate_values/ templateLDA_O010/

