#!/usr/bin/env bash
# Launch paperscale_v4 Iteration Scan reruns on IDP.
#
# Reuses existing paperscale_v3 sandboxes (templates + bit tables already built).
# Only the Iteration_Scan_2R/3R/4R stages are rerun with SHA3_SASCA_ITERATION_COUNT=200.
# Rate Scan results are left untouched.
#
# Usage: bash launch_paperscale_v4_iter_scan.sh [--dry-run]
#
set -euo pipefail

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

LOCAL_SRC="${HOME}/Documents/Uni/IDP/Projects_SHA3/project_SHA3-32bit"
REMOTE_USER="ge96pug"
REMOTE_HOST="IDP"
REMOTE_BASE="/storage/${REMOTE_USER}"

RUNS=(
    "hw_sigma0p1"
    "hw_sigma0p5"
    "hw_sigma1p0"
    "hd_sigma0p1"
    "hd_sigma0p5"
    "hd_sigma1p0"
)

log() { echo "[$(date '+%H:%M:%S')] $*"; }

for run in "${RUNS[@]}"; do
    sandbox="${REMOTE_BASE}/Projects_SHA3_sandbox_paperscale_v3_${run}"
    proj="${sandbox}/project_SHA3-32bit"
    log_file="${proj}/pipeline_runner/sandbox_paperscale_v4_${run}_iter_scan.log"

    log "=== ${run} ==="

    # Step 1: rsync updated code (skip large data and sandbox .env)
    log "  rsyncing code..."
    if [ "${DRY_RUN}" -eq 1 ]; then
        echo "    [dry-run] rsync -a --delete [excludes] ${LOCAL_SRC}/ ${REMOTE_USER}@${REMOTE_HOST}:${proj}/"
    else
        rsync -a --delete \
            --exclude='Raw/' \
            --exclude='Raw_*/' \
            --exclude='*.zip' \
            --exclude='*.hdf5' \
            --exclude='*.npy' \
            --exclude='__pycache__/' \
            --exclude='.env' \
            --exclude='Predictions/' \
            --exclude='Success/' \
            "${LOCAL_SRC}/" \
            "${REMOTE_USER}@${REMOTE_HOST}:${proj}/"
    fi

    # Step 2: patch SHA3_SASCA_ITERATION_COUNT in the sandbox .env (40 → 200)
    log "  patching .env..."
    if [ "${DRY_RUN}" -eq 1 ]; then
        echo "    [dry-run] sed -i SHA3_SASCA_ITERATION_COUNT=200 in ${proj}/pipeline_runner/.env"
    else
        ssh "${REMOTE_HOST}" "sed -i 's/^SHA3_SASCA_ITERATION_COUNT=.*/SHA3_SASCA_ITERATION_COUNT=200/' ${proj}/.env"
        result=$(ssh "${REMOTE_HOST}" "grep SHA3_SASCA_ITERATION_COUNT ${proj}/.env")
        log "  verified: ${result}"
    fi

    # Step 3: write a per-run launch script to the remote sandbox and execute it in background
    remote_launch="${proj}/pipeline_runner/run_v4_iter_scan.sh"
    log "  writing remote launch script to ${remote_launch}..."

    if [ "${DRY_RUN}" -eq 1 ]; then
        echo "    [dry-run] would write and execute ${remote_launch}"
    else
        ssh "${REMOTE_HOST}" "cat > ${remote_launch}" <<REMOTE_SCRIPT
#!/usr/bin/env bash
set -euo pipefail
base="${proj}"
log_file="${log_file}"
cd "\${base}"
source .env 2>/dev/null || true

echo "[\$(date '+%Y-%m-%d %H:%M:%S')] Starting paperscale_v4 iteration scan: ${run}"
echo "  SHA3_SASCA_ITERATION_COUNT=\${SHA3_SASCA_ITERATION_COUNT:-unset}"

for depth in 2R 3R 4R; do
    dir="\${base}/0005_SASCA/Iteration_Scan_\${depth}"
    echo "[\$(date '+%H:%M:%S')] Cleaning Iteration_Scan_\${depth}..."
    cd "\${dir}" && bash clean.sh
    echo "[\$(date '+%H:%M:%S')] Running Iteration_Scan_\${depth}..."
    bash script_all.sh
    echo "[\$(date '+%H:%M:%S')] Iteration_Scan_\${depth} DONE"
done

echo "[\$(date '+%Y-%m-%d %H:%M:%S')] COMPLETE: paperscale_v4 iteration scan ${run}"
REMOTE_SCRIPT

        ssh "${REMOTE_HOST}" "chmod +x ${remote_launch} && nohup bash ${remote_launch} > ${log_file} 2>&1 &"
        log "  launched. Log: ${log_file}"
    fi
done

log ""
log "All 6 runs launched."
log ""
log "Monitor progress with:"
log "  ssh IDP 'for r in hw_sigma0p1 hw_sigma0p5 hw_sigma1p0 hd_sigma0p1 hd_sigma0p5 hd_sigma1p0; do echo \"=== \$r ===\"; tail -2 /storage/ge96pug/Projects_SHA3_sandbox_paperscale_v3_\${r}/project_SHA3-32bit/pipeline_runner/sandbox_paperscale_v4_\${r}_iter_scan.log 2>/dev/null; done'"
