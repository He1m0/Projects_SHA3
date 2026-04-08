SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}" || exit 1

mkdir -p Bit_Tables/
mkdir -p Bit_Tables/Tables_INP/
mkdir -p Bit_Tables/Tables_A00/
mkdir -p Bit_Tables/Tables_A01/
mkdir -p Bit_Tables/Tables_A02/
mkdir -p Bit_Tables/Tables_A03/
mkdir -p Bit_Tables/Tables_B00/
mkdir -p Bit_Tables/Tables_B01/
mkdir -p Bit_Tables/Tables_B02/
mkdir -p Bit_Tables/Tables_B03/
mkdir -p Bit_Tables/Tables_C00/
mkdir -p Bit_Tables/Tables_C01/
mkdir -p Bit_Tables/Tables_C02/
mkdir -p Bit_Tables/Tables_C03/
mkdir -p Bit_Tables/Tables_D00/
mkdir -p Bit_Tables/Tables_D01/
mkdir -p Bit_Tables/Tables_D02/
mkdir -p Bit_Tables/Tables_D03/
TAGS=$(python3 - <<'PY'
import os
import sys
sys.path.append(os.path.abspath('../../'))
import global_config as gc
print(gc.SASCA_TEMPLATE_TAG, gc.SASCA_ICS_TAG)
PY
)
set -- ${TAGS}
template_tag=$1
ics_tag=$2
unzip -o -q ../../0002_detection/Code_extract_ics/ics_original_${ics_tag}.zip
unzip -o -q ../../0003_training/template_profiling_bytes/templateLDA_O${template_tag}.zip
unzip -o -q ../get_answers/answer_bit.zip
