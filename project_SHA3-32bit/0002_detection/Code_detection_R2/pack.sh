set -euo pipefail

if ! find detect_results_08 -type f -name '*.npy' -print -quit | grep -q .; then
	echo "Error: detect_results_08 has no .npy files. Detection likely failed earlier."
	exit 1
fi

if ! find detect_results_32 -type f -name '*.npy' -print -quit | grep -q .; then
	echo "Error: detect_results_32 has no .npy files. Detection likely failed earlier."
	exit 1
fi

zip detect_results_08.zip -r detect_results_08/
zip detect_results_32.zip -r detect_results_32/
rm -vr __pycache__/ detect_results_*/ intermediate_values/

