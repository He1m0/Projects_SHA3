set -euo pipefail

./init.sh
# detect_script.py's numpy/BLAS calls fan out to ~1 thread per core by
# default (observed: 127 threads for a single process on a 192-core host).
# Capped so multiple R2 stages can run concurrently (sweep monitors launch
# many sigmas in parallel) without oversubscribing the host -- uncapped, as
# few as 2-3 concurrent R2 processes already thrash the scheduler.
OMP_NUM_THREADS="${SHA3_R2_THREADS:-4}" \
OPENBLAS_NUM_THREADS="${SHA3_R2_THREADS:-4}" \
MKL_NUM_THREADS="${SHA3_R2_THREADS:-4}" \
NUMEXPR_NUM_THREADS="${SHA3_R2_THREADS:-4}" \
VECLIB_MAXIMUM_THREADS="${SHA3_R2_THREADS:-4}" \
python3 detect_script.py
./pack.sh
