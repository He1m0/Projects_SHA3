#!/usr/bin/env sh
# deploy_monitor.sh
#
# One-time setup: run from local machine before shutting it down.
# Pulls the latest commits into the IDP repo so env files and scripts are
# up to date, then copies monitor_snr_sweep.sh to the stable IDP launch path.
#
# Usage:
#   sh pipeline_runner/deploy_monitor.sh
#   sh pipeline_runner/deploy_monitor.sh --dry-run

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REMOTE="ge96pug@IDP"
REMOTE_REPO="/storage/ge96pug/Projects_SHA3"
MONITOR_DEST="/storage/ge96pug/monitor_snr_sweep.sh"
DRY_RUN=0

[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

echo "=== Deploying monitor to IDP ==="
[ "${DRY_RUN}" -eq 1 ] && echo "  (DRY-RUN — no transfers)"
echo ""

echo "1/2  git pull on IDP repo (${REMOTE_REPO})"
if [ "${DRY_RUN}" -eq 1 ]; then
  echo "  [DRY-RUN] ssh ${REMOTE} 'cd ${REMOTE_REPO} && git pull'"
else
  ssh "${REMOTE}" "cd '${REMOTE_REPO}' && git pull"
fi

echo ""
echo "2/2  monitor_snr_sweep.sh → ${REMOTE}:${MONITOR_DEST}"
if [ "${DRY_RUN}" -eq 1 ]; then
  echo "  [DRY-RUN] scp ${SCRIPT_DIR}/monitor_snr_sweep.sh ${REMOTE}:${MONITOR_DEST}"
else
  scp "${SCRIPT_DIR}/monitor_snr_sweep.sh" "${REMOTE}:${MONITOR_DEST}"
fi

echo ""
echo "=== Deploy complete. ==="
echo ""
echo "Verify monitor can find the repo:"
echo "  ssh IDP 'sh ${MONITOR_DEST} --dry-run'"
echo ""
echo "Start the monitor in a persistent tmux session on IDP:"
echo "  ssh IDP 'tmux new-session -d -s snr_monitor \"sh ${MONITOR_DEST} 2>&1\"'"
echo "  ssh IDP 'tmux attach -t snr_monitor'"
echo ""
echo "Resume from a specific wave (if monitor was interrupted):"
echo "  ssh IDP 'sh ${MONITOR_DEST} --start-wave B1'"
