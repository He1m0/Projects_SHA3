#!/usr/bin/env sh
# Launch smoke-v6 sigma sweep (18 runs: 9 sigmas × 2 SNR-equalized modes).
#
# SNR-equalized: f9_scale=√3≈1.7321, id_scale≈0.01913 — both match HW SNR_var=2/σ².
# ICS level 90 used uniformly. Comparable to smoke-v5 (HW/HD).
#
# Purpose: sanity check before committing paperscale-v5. Smoke runs are fast
# (~minutes for detection, ~1-2h total). Always run --wave sanity FIRST.
#
# Usage:
#   sh launch_smoke_v6.sh --wave sanity     (f9+id σ=0.1 only — 2 runs, gate check)
#   sh launch_smoke_v6.sh --wave all        (all 18 runs)
#   sh launch_smoke_v6.sh --wave f9         (all 9 f9 runs)
#   sh launch_smoke_v6.sh --wave id         (all 9 id runs)
#   sh launch_smoke_v6.sh --status
#   sh launch_smoke_v6.sh --dry-run --wave all

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ENVS_DIR="${SCRIPT_DIR}/envs/smoke_v6_sigma_sweep"
DRY_RUN=0

# ── helpers ──────────────────────────────────────────────────────────────────

print_help() {
  sed -n '2,/^set -eu/{ /^set -eu/d; s/^# \{0,1\}//; p }' "$0"
  exit 0
}

launch_envs_dir() {
  dir="$1"
  echo "  Launching from: ${dir}"
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  [DRY RUN] run_sandboxes.sh --envs-dir ${dir} --ssh IDP"
    ls "${dir}"/".env_"* 2>/dev/null | while read -r f; do
      echo "    would launch: $(basename "$f")"
    done
    return
  fi
  sh "${SCRIPT_DIR}/run_sandboxes.sh" \
    --envs-dir "${dir}" \
    --ssh IDP
}

launch_single() {
  env_file="$1"
  name=$(basename "${env_file}" | sed 's/^\.env_//')
  echo "  Launching: ${name}"
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "    [DRY RUN] run_sandboxes.sh --ssh IDP ${env_file}"
    return
  fi
  tmp_dir="/tmp/smoke_v6_single_$$_${name}"
  mkdir -p "${tmp_dir}"
  cp "${env_file}" "${tmp_dir}/"
  sh "${SCRIPT_DIR}/run_sandboxes.sh" \
    --envs-dir "${tmp_dir}" \
    --ssh IDP
  rm -rf "${tmp_dir}"
}

launch_mode() {
  mode="$1"
  echo "=== smoke-v6: all ${mode} runs (9 sigmas) ==="
  tmp_dir="/tmp/smoke_v6_mode_$$_${mode}"
  mkdir -p "${tmp_dir}"
  for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
    cp "${ENVS_DIR}/.env_smoke_v6_${mode}_sigma${sig}" "${tmp_dir}/"
  done
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  [DRY RUN] would launch 9 runs from ${tmp_dir}"
    ls "${tmp_dir}"
    rm -rf "${tmp_dir}"
    return
  fi
  sh "${SCRIPT_DIR}/run_sandboxes.sh" \
    --envs-dir "${tmp_dir}" \
    --ssh IDP
  rm -rf "${tmp_dir}"
}

# ── status ────────────────────────────────────────────────────────────────────

show_status() {
  echo "=== Smoke v6 status ==="
  echo ""
  ssh IDP '
for mode in f9 id; do
  for sig in 0p1 0p5 1p0 1p5 2p0 2p5 3p0 3p5 4p0; do
    sb=/storage/ge96pug/Projects_SHA3_sandbox_smoke_v6_${mode}_sigma${sig}
    plr="$sb/project_SHA3-32bit/pipeline_runner"
    log="$plr/sandbox_smoke_v6_${mode}_sigma${sig}.log"
    if [ ! -f "$log" ]; then
      echo "  not_started ${mode}_sigma${sig}"
      continue
    fi
    if grep -q "COMPLETE" "$log" 2>/dev/null; then
      echo "  DONE     ${mode}_sigma${sig}"
    elif grep -q "\[MOVE:DN\]" "$log" 2>/dev/null; then
      last=$(tail -1 "$log" 2>/dev/null | cut -c1-80)
      echo "  training ${mode}_sigma${sig}: $last"
    else
      last=$(tail -1 "$log" 2>/dev/null | cut -c1-80)
      echo "  detect   ${mode}_sigma${sig}: $last"
    fi
  done
done'
}

# ── argument parsing ──────────────────────────────────────────────────────────

if [ "$#" -eq 0 ]; then print_help; fi

WAVE=""
ACTION="wave"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --wave)    WAVE="$2"; shift 2 ;;
    --status)  ACTION="status"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --help|-h) print_help ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

case "${ACTION}" in
  status) show_status; exit 0 ;;
esac

# ── wave launches ─────────────────────────────────────────────────────────────

case "${WAVE}" in
  sanity)
    echo "=== Smoke v6 sanity check: f9+id σ=0.1 (2 runs) ==="
    echo "Gate: verify ICS level 90 is non-empty and SASCA starts before launching paperscale."
    launch_single "${ENVS_DIR}/.env_smoke_v6_f9_sigma0p1"
    launch_single "${ENVS_DIR}/.env_smoke_v6_id_sigma0p1"
    ;;
  all)
    echo "=== Smoke v6: all 18 runs ==="
    launch_mode f9
    launch_mode id
    ;;
  f9)
    launch_mode f9
    ;;
  id)
    launch_mode id
    ;;
  *)
    echo "Unknown wave: ${WAVE}. Use: sanity, all, f9, id." >&2
    exit 1
    ;;
esac

echo ""
echo "Monitor: sh ${SCRIPT_DIR}/launch_smoke_v6.sh --status"
