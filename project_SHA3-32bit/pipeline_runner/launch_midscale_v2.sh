#!/usr/bin/env bash
# Launch midscale_v2 pilot runs (HW + HD, sigma 0.1/0.5/1.0) on IDP.
# 200 BP iterations — corrected rerun of midscale_v1 which used 40 iters.
# Run this script FROM the local machine; it rsyncs and launches remotely.
# Usage: bash launch_midscale_v2.sh
set -euo pipefail

LOCAL_SRC="$HOME/Documents/Uni/IDP/Projects_SHA3/project_SHA3-32bit"
REMOTE_USER="ge96pug"
REMOTE_HOST="IDP"
REMOTE_STORAGE="/storage/ge96pug"

SPECS=(
  "hw 0p1" "hw 0p5" "hw 1p0"
  "hd 0p1" "hd 0p5" "hd 1p0"
)

echo "=== Phase 0: create sandbox structure on IDP (sequential) ==="
for SPEC in "${SPECS[@]}"; do
  MODE=$(echo "$SPEC" | cut -d' ' -f1)
  STAG=$(echo "$SPEC" | cut -d' ' -f2)
  TAG="midscale_v2_${MODE}_sigma${STAG}"
  SANDBOX="${REMOTE_STORAGE}/Projects_SHA3_sandbox_${TAG}"
  echo "  setup $TAG (removing broken sandbox if present)"
  ssh "${REMOTE_USER}@${REMOTE_HOST}" \
    "rm -rf '${SANDBOX}' && sh ${REMOTE_STORAGE}/Projects_SHA3/project_SHA3-32bit/pipeline_runner/setup_sandbox.sh --label ${TAG}"
done
echo "  All sandboxes created."

echo ""
echo "=== Phase 1: rsync local project_SHA3-32bit to all sandboxes in parallel ==="
RSYNC_PIDS=()
for SPEC in "${SPECS[@]}"; do
  MODE=$(echo "$SPEC" | cut -d' ' -f1)
  STAG=$(echo "$SPEC" | cut -d' ' -f2)
  SANDBOX="Projects_SHA3_sandbox_midscale_v2_${MODE}_sigma${STAG}"
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
echo "=== Phase 2: launch all 6 pipeline runs ==="
for SPEC in "${SPECS[@]}"; do
  MODE=$(echo "$SPEC" | cut -d' ' -f1)
  STAG=$(echo "$SPEC" | cut -d' ' -f2)
  TAG="midscale_v2_${MODE}_sigma${STAG}"
  SANDBOX="${REMOTE_STORAGE}/Projects_SHA3_sandbox_${TAG}"
  TRACES_DIR="${REMOTE_STORAGE}/traces_${TAG}"
  ENV_FILE="envs/midscale_v2_sigma_sweep/.env_midscale_v2_${MODE}_sigma${STAG}"
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
echo "=== All 6 runs launched. Monitor with: ==="
echo "ssh IDP \"for d in /storage/ge96pug/Projects_SHA3_sandbox_midscale_v2_{hw,hd}_sigma{0p1,0p5,1p0}/project_SHA3-32bit/pipeline_runner; do tail -1 \\\"\$d\\\"/sandbox_midscale_v2_*.log 2>/dev/null; done\""
