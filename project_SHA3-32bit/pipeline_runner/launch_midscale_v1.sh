#!/usr/bin/env sh
# Launch midscale-v1 sigma sweep (36 runs: 9 sigmas × 4 modes), per-sigma-slice.
#
# TRACES_DIR is embedded in each env file, so no --traces-dir override needed.
# hd/hw/id and f9 sigma=3p0/3p5/4p0: --skip-sim (reuse paperscale trace dirs).
# f9 sigma=0p1..2p5: simulate (new traces dir, incomplete/absent paperscale TR).
#
# Usage:
#   sh launch_midscale_v1.sh [--wave A|B|Bf9|all]
#
#   Wave A  : hd/hw/id sigma=0p1..2p5 (18 runs, --skip-sim)
#             + f9 sigma=3p0/3p5/4p0 (3 runs, --skip-sim)        [21 concurrent]
#   Wave Af9: f9 sigma=0p1/0p5/1p0 simulate (3 concurrent sims)
#             then f9 sigma=1p5/2p0/2p5 simulate (after Af9 shows [MOVE:DN])
#   Wave B  : hd/hw/id sigma=3p0..4p0 (9 runs, --skip-sim)
#             launch after: ssh IDP "pgrep -c -f detect_script" <= 20
#   Wave Bf9: f9 sigma=0p1..2p5 (6 runs) into pipeline after simulation done
#   all     : A + Af9 + B + Bf9 (launches waves A and Af9 immediately, B/Bf9 after check)
#
# Before each wave, verify: ssh IDP "pgrep -c -f detect_script"  must be <= 20.
#
# Default (no args): launches Wave A + Wave Af9 immediately.

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ENVS_BASE="${SCRIPT_DIR}/envs/midscale_v1_sigma_sweep"

WAVE="${1:-A}"

run_slice_skip_sim() {
    sigma_dir="$1"
    echo "  Launching (--skip-sim): ${sigma_dir}"
    sh "${SCRIPT_DIR}/run_sandboxes.sh" \
        --envs-dir "${sigma_dir}" \
        --ssh IDP \
        -- --skip-sim
}

run_slice_simulate() {
    sigma_dir="$1"
    echo "  Launching (simulate): ${sigma_dir}"
    sh "${SCRIPT_DIR}/run_sandboxes.sh" \
        --envs-dir "${sigma_dir}" \
        --ssh IDP
}

run_single_env_skip_sim() {
    env_file="$1"
    tmp_dir="/tmp/midscale_v1_single_$$"
    mkdir -p "${tmp_dir}"
    cp "${env_file}" "${tmp_dir}/"
    sh "${SCRIPT_DIR}/run_sandboxes.sh" \
        --envs-dir "${tmp_dir}" \
        --ssh IDP \
        -- --skip-sim
    rm -rf "${tmp_dir}"
}

run_single_env_simulate() {
    env_file="$1"
    tmp_dir="/tmp/midscale_v1_single_$$"
    mkdir -p "${tmp_dir}"
    cp "${env_file}" "${tmp_dir}/"
    sh "${SCRIPT_DIR}/run_sandboxes.sh" \
        --envs-dir "${tmp_dir}" \
        --ssh IDP
    rm -rf "${tmp_dir}"
}

check_r2_count() {
    count=$(ssh IDP "pgrep -c -f detect_script 2>/dev/null || echo 0")
    echo "Current R2 processes on IDP: ${count}"
    if [ "${count}" -gt 20 ]; then
        echo "WARNING: ${count} > 20 concurrent R2 processes. Wait before launching Wave B."
        return 1
    fi
    return 0
}

# ── Wave A: hd/hw/id sigma=0p1..2p5, plus f9 skip-sim sigma=3p0..4p0 ──────────
if [ "${WAVE}" = "A" ] || [ "${WAVE}" = "all" ]; then
    echo "=== Wave A: hd/hw/id sigma=0p1..2p5 (18 runs, --skip-sim) ==="
    for sigma in 0p1 0p5 1p0 1p5 2p0 2p5; do
        sigma_dir="${ENVS_BASE}/sigma${sigma}"
        # Launch only hd/hw/id (not f9) from this slice — f9 handled separately
        for mode in hd hw id; do
            run_single_env_skip_sim "${sigma_dir}/.env_midscale_v1_${mode}_sigma${sigma}"
        done
    done

    echo ""
    echo "=== Wave A (f9 skip-sim): f9 sigma=3p0/3p5/4p0 (3 runs, --skip-sim) ==="
    for sigma in 3p0 3p5 4p0; do
        run_single_env_skip_sim "${ENVS_BASE}/sigma${sigma}/.env_midscale_v1_f9_sigma${sigma}"
    done

    echo ""
    echo "Wave A done. 21 runs launched."
    echo "Monitor: ssh IDP \"tail -1 /storage/ge96pug/Projects_SHA3_sandbox_midscale_v1_*/project_SHA3-32bit/pipeline_runner/sandbox_*.log 2>/dev/null\""
fi

# ── Wave A-f9: f9 simulation sigma=0p1/0p5/1p0 (3 concurrent), then 1p5/2p0/2p5 ──
if [ "${WAVE}" = "Af9" ] || [ "${WAVE}" = "all" ]; then
    echo ""
    echo "=== Wave Af9 batch 1: f9 sigma=0p1/0p5/1p0 (simulate, 3 concurrent) ==="
    for sigma in 0p1 0p5 1p0; do
        run_single_env_simulate "${ENVS_BASE}/sigma${sigma}/.env_midscale_v1_f9_sigma${sigma}"
    done
    echo ""
    echo "Batch 1 launched. Wait for [MOVE:DN] in all 3 before launching batch 2:"
    echo "  ssh IDP \"grep -l 'MOVE.*DN' /storage/ge96pug/Projects_SHA3_sandbox_midscale_v1_f9_sigma{0p1,0p5,1p0}/project_SHA3-32bit/pipeline_runner/sandbox_*.log 2>/dev/null | wc -l\""
    echo "  (need 3, then run:  sh launch_midscale_v1.sh --wave Af9b)"
fi

# ── Wave A-f9 batch 2: sigma=1p5/2p0/2p5 ─────────────────────────────────────
if [ "${WAVE}" = "Af9b" ]; then
    echo ""
    echo "=== Wave Af9 batch 2: f9 sigma=1p5/2p0/2p5 (simulate, 3 concurrent) ==="
    for sigma in 1p5 2p0 2p5; do
        run_single_env_simulate "${ENVS_BASE}/sigma${sigma}/.env_midscale_v1_f9_sigma${sigma}"
    done
fi

# ── Wave B: hd/hw/id sigma=3p0..4p0 (after R2 count drops) ──────────────────
if [ "${WAVE}" = "B" ]; then
    echo ""
    echo "=== Wave B: hd/hw/id sigma=3p0..4p0 (9 runs, --skip-sim) ==="
    if ! check_r2_count; then
        echo "Aborting Wave B — too many R2 processes. Re-run when count drops."
        exit 1
    fi
    for sigma in 3p0 3p5 4p0; do
        for mode in hd hw id; do
            run_single_env_skip_sim "${ENVS_BASE}/sigma${sigma}/.env_midscale_v1_${mode}_sigma${sigma}"
        done
    done
    echo "Wave B done. 9 runs launched."
fi

echo ""
echo "Quick status:"
echo "  ssh IDP \"tail -1 /storage/ge96pug/Projects_SHA3_sandbox_midscale_v1_*/project_SHA3-32bit/pipeline_runner/sandbox_*.log 2>/dev/null\""
echo "  ssh IDP \"pgrep -c -f detect_script 2>/dev/null\""
