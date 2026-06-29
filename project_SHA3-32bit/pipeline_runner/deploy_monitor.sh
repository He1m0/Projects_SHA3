#!/usr/bin/env sh
# deploy_monitor.sh
#
# One-time setup: run from local machine before shutting it down.
# Rsyncs project source + env files + monitor script to IDP so that
# monitor_snr_sweep.sh can run fully self-contained on IDP.
#
# Usage:
#   sh pipeline_runner/deploy_monitor.sh
#   sh pipeline_runner/deploy_monitor.sh --dry-run

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SRC="$(cd "${SCRIPT_DIR}/.." && pwd)"   # project_SHA3-32bit/
REMOTE="ge96pug@IDP"
STORAGE="${REMOTE}:/storage/ge96pug"
DRY_RUN=0

[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

rsync_cmd() {
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  [DRY-RUN] rsync $*"
  else
    rsync "$@"
  fi
}

scp_cmd() {
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  [DRY-RUN] scp $*"
  else
    scp "$@"
  fi
}

echo "=== Deploying monitor to IDP ==="
[ "${DRY_RUN}" -eq 1 ] && echo "  (DRY-RUN — no transfers)"
echo ""

echo "1/4  Project source → ${STORAGE}/Projects_SHA3_src/"
echo "     (excludes gitignored data files; uses .gitignore rules)"
rsync_cmd -a --delete \
  --filter=':- .gitignore' \
  --exclude='.git/' \
  "${SRC}/" "${STORAGE}/Projects_SHA3_src/"

echo ""
echo "2/4  smoke_v6 env files → ${STORAGE}/envs_smoke_v6/"
rsync_cmd -a \
  "${SCRIPT_DIR}/envs/smoke_v6_sigma_sweep/" \
  "${STORAGE}/envs_smoke_v6/"

echo ""
echo "3/4  paperscale_v5 env files → ${STORAGE}/envs_paperscale_v5/"
rsync_cmd -a \
  "${SCRIPT_DIR}/envs/paperscale_v5_sigma_sweep/" \
  "${STORAGE}/envs_paperscale_v5/"

echo ""
echo "4/4  monitor_snr_sweep.sh → ${STORAGE}/monitor_snr_sweep.sh"
scp_cmd "${SCRIPT_DIR}/monitor_snr_sweep.sh" \
        "${STORAGE}/monitor_snr_sweep.sh"

echo ""
echo "=== Deploy complete. ==="
echo ""
echo "Next steps:"
echo "  1. Dry-run the monitor to verify phase sequence:"
echo "       ssh IDP 'sh /storage/ge96pug/monitor_snr_sweep.sh --dry-run'"
echo ""
echo "  2. Start the monitor in a persistent tmux session on IDP:"
echo "       ssh IDP 'tmux new-session -d -s snr_monitor \"sh /storage/ge96pug/monitor_snr_sweep.sh 2>&1\"'"
echo "       ssh IDP 'tmux attach -t snr_monitor'"
echo ""
echo "  3. To resume from a specific wave (if monitor was interrupted):"
echo "       ssh IDP 'sh /storage/ge96pug/monitor_snr_sweep.sh --start-wave B1'"
