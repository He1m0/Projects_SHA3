#!/usr/bin/env bash
# Set up paperscale_v4 iteration scan reruns in tmux sessions on IDP.
#
# Run locally: bash pipeline_runner/setup_v4iter_tmux.sh
#
# What it does:
#   1. Kills any leftover nohup v4 iteration scan processes
#   2. Cleans partial results from previous nohup runs (Iteration_Scan_*/Success/ etc.)
#   3. Creates 6 tmux sessions named v4iter_{mode}_sigma{x}
#   4. Each session runs all three depths (2R, 3R, 4R) sequentially:
#        clean.sh → script_all.sh per depth
#   5. A trailing `bash` keeps the window open after completion
#
# Monitor:  ssh IDP 'tmux list-sessions | grep v4iter'
# Attach:   ssh IDP -t 'tmux attach -t v4iter_hw_sigma0p1'

set -euo pipefail

REMOTE="IDP"
BASE="/storage/ge96pug"
RUNS=(hw_sigma0p1 hw_sigma0p5 hw_sigma1p0 hd_sigma0p1 hd_sigma0p5 hd_sigma1p0)

ssh "${REMOTE}" bash << 'REMOTE_BLOCK'
set -euo pipefail
BASE=/storage/ge96pug
RUNS=(hw_sigma0p1 hw_sigma0p5 hw_sigma1p0 hd_sigma0p1 hd_sigma0p5 hd_sigma1p0)

# ── 1. Kill any leftover nohup processes ──────────────────────────────────────
echo "[1/3] Killing leftover v4 nohup processes..."
pkill -f "run_v4_iter_scan.sh"  2>/dev/null && echo "  killed run_v4_iter_scan.sh" || echo "  (none running)"
pkill -f "Iteration_scan.py 0 1000" 2>/dev/null && echo "  killed Iteration_scan.py" || echo "  (none running)"

# ── 2. Create tmux sessions ───────────────────────────────────────────────────
echo "[2/3] Creating tmux sessions..."
for run in "${RUNS[@]}"; do
    proj="${BASE}/Projects_SHA3_sandbox_paperscale_v3_${run}/project_SHA3-32bit"
    sname="v4iter_${run}"

    # Kill stale session if any
    tmux kill-session -t "${sname}" 2>/dev/null && echo "  killed stale session: ${sname}" || true

    # Inline command: clean + run each depth, keep window open after
    cmd="cd '${proj}' && source .env && "
    for d in 2R 3R 4R; do
        cmd+="echo ''; echo '════ Iteration_Scan_${d} ════'; "
        cmd+="cd '${proj}/0005_SASCA/Iteration_Scan_${d}' && bash clean.sh && bash script_all.sh; "
    done
    cmd+="echo ''; echo 'COMPLETE: ${run}'; bash"

    tmux new-session -d -s "${sname}" -x 220 -y 50 "bash -c \"${cmd}\""
    echo "  created: ${sname}"
done

# ── 3. Verify ─────────────────────────────────────────────────────────────────
echo ""
echo "[3/3] Active v4iter sessions:"
tmux list-sessions 2>/dev/null | grep v4iter || echo "  (none found — something went wrong)"

echo ""
echo "Done. Attach with:  ssh IDP -t 'tmux attach -t v4iter_hw_sigma0p1'"
echo "Monitor tail:       ssh IDP 'for s in \$(tmux list-sessions -F \"#S\" | grep v4iter); do echo \"=== \$s ===\"; tmux capture-pane -t \"\$s\" -p | tail -3; done'"
REMOTE_BLOCK
