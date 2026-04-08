set -euo pipefail

./init.sh
python3 detect_script.py
./pack.sh
