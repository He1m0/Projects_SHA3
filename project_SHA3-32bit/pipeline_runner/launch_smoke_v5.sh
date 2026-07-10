#!/usr/bin/env bash
# Launch all 18 smoke_v5 sigma-sweep runs (HW + HD, 9 sigma levels each) on IDP.
# Run this script FROM the local machine; it rsyncs and launches remotely.
# Usage: bash launch_smoke_v5.sh
set -euo pipefail

LOCAL_SRC="$HOME/Documents/Uni/IDP/Projects_SHA3/project_SHA3-32bit"
REMOTE_USER="ge96pug"
REMOTE_HOST="IDP"
REMOTE_STORAGE="/storage/ge96pug"

SPECS=(
  "hw 0p1" "hw 0p5" "hw 1p0" "hw 1p5" "hw 2p0" "hw 2p5" "hw 3p0" "hw 3p5" "hw 4p0"
  "hd 0p1" "hd 0p5" "hd 1p0" "hd 1p5" "hd 2p0" "hd 2p5" "hd 3p0" "hd 3p5" "hd 4p0"
)

echo "=== Phase 1: rsync all sandboxes in parallel ==="
RSYNC_PIDS=()
for SPEC in "${SPECS[@]}"; do
  MODE=$(echo "$SPEC" | cut -d' ' -f1)
  STAG=$(echo "$SPEC" | cut -d' ' -f2)
  SANDBOX="Projects_SHA3_sandbox_smoke_v5_${MODE}_sigma${STAG}"
  DEST="${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_STORAGE}/${SANDBOX}/project_SHA3-32bit/"
  echo "  rsync -> $SANDBOX"
  rsync -az --exclude='.git/' --exclude='runs_archive/' --exclude='Raw/' \
        --exclude='*.zip' --exclude='*.hdf5' --exclude='*.npy' \
        "${LOCAL_SRC}/" "${DEST}" &
  RSYNC_PIDS+=($!)
done

echo "  Waiting for all ${#RSYNC_PIDS[@]} rsyncs..."
for PID in "${RSYNC_PIDS[@]}"; do
  wait "$PID" || { echo "rsync pid $PID failed"; exit 1; }
done
echo "  All rsyncs done."

echo ""
echo "=== Phase 2: launch all 18 pipeline runs ==="
for SPEC in "${SPECS[@]}"; do
  MODE=$(echo "$SPEC" | cut -d' ' -f1)
  STAG=$(echo "$SPEC" | cut -d' ' -f2)
  TAG="smoke_v5_${MODE}_sigma${STAG}"
  SANDBOX="${REMOTE_STORAGE}/Projects_SHA3_sandbox_${TAG}"
  TRACES_DIR="${REMOTE_STORAGE}/traces_${TAG}"
  ENV_FILE="envs/smoke_v5_sigma_sweep/.env_smoke_v5_${MODE}_sigma${STAG}"
  LOG="${SANDBOX}/project_SHA3-32bit/pipeline_runner/sandbox_${TAG}.log"

  echo "  launching $TAG"
  ssh "${REMOTE_USER}@${REMOTE_HOST}" \
    "cd ${SANDBOX}/project_SHA3-32bit/pipeline_runner && \
     nohup bash run_full_pipeline.sh \
       --env-file ${ENV_FILE} \
       --traces-dir ${TRACES_DIR} \
       > ${LOG} 2>&1 &
     echo \"launched PID \$!\""
done

echo ""
echo "=== All 18 runs launched. Monitor with: ==="
echo "ssh IDP \"for d in /storage/ge96pug/Projects_SHA3_sandbox_smoke_v5_{hw,hd}_sigma{0p1,0p5,1p0,1p5,2p0,2p5,3p0,3p5,4p0}/project_SHA3-32bit/pipeline_runner; do tail -1 \\\"\$d\\\"/sandbox_smoke_v5_*.log 2>/dev/null; done\""
