#!/usr/bin/env sh
# One-shot detailed status snapshot across both auto_sweep_monitor.sh
# families (smoke_v8 pure modes, smoke_v9 mixed configs) plus the shared
# remote resources they compete for. Read-only, safe to run anytime.
#
# Usage:
#   sh sweep_status.sh                 (both families, per-sigma state + current
#                                        pipeline stage for every running sigma)
#   sh sweep_status.sh --family smoke_v8
#   sh sweep_status.sh --family smoke_v9
#   sh sweep_status.sh --no-detail     (state only, skip the per-sigma stage line
#                                        -- faster, coarser, matches the old output)
#   sh sweep_status.sh --halts-only    (just grep HALT: lines from both monitor logs)

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export SSH_TARGET=IDP
. "${SCRIPT_DIR}/ics_gate_lib.sh"

FAMILIES="smoke_v8 smoke_v9"
HALTS_ONLY=0
DETAIL_FLAG="--detailed"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --family)     FAMILIES="$2"; shift 2 ;;
    --halts-only) HALTS_ONLY=1; shift ;;
    --no-detail)  DETAIL_FLAG=""; shift ;;
    --help|-h)
      sed -n '2,/^set -eu/{ /^set -eu/d; s/^# \{0,1\}//; p }' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

MONITOR_DIR="/storage/ge96pug/Projects_SHA3/project_SHA3-32bit/pipeline_runner"

if [ "${HALTS_ONLY}" -eq 1 ]; then
  echo "=== HALT lines (both families) ==="
  for family in ${FAMILIES}; do
    lines="$(ssh IDP "grep 'HALT:' '${MONITOR_DIR}/auto_sweep_monitor_${family}.log' 2>/dev/null; true")"
    if [ -n "${lines}" ]; then
      echo "${lines}" | sed "s/^/[${family}] /"
    else
      echo "  [${family}] none"
    fi
  done
  exit 0
fi

echo "=== Remote resource snapshot ==="
r2="$(r2_count)"
pressure="$(r2_pressure)"
echo "  R2 (detect_script) processes running now: ${r2}"
echo "  R2 pressure (launched + not yet past R2, incl. imminent): ${pressure} / soft cap 20 before a new wave"
ssh IDP "df -h /storage/ge96pug 2>/dev/null | tail -1 | awk '{print \"  Disk: \" \$3 \" used / \" \$2 \" total (\" \$5 \" full, \" \$4 \" avail)\"}'"
echo ""

echo "=== Monitor tmux sessions ==="
for family in ${FAMILIES}; do
  case "${family}" in
    smoke_v8) tmux_name="auto_sweep_monitor" ;;
    smoke_v9) tmux_name="auto_sweep_monitor_v9" ;;
    *) echo "Unknown family: ${family}" >&2; exit 1 ;;
  esac
  if ssh IDP "tmux has-session -t '${tmux_name}' 2>/dev/null"; then
    echo "  ${family}: RUNNING (tmux session '${tmux_name}')"
  else
    echo "  ${family}: NOT RUNNING (tmux session '${tmux_name}' not found -- check for a crash)"
  fi
done
echo ""

for family in ${FAMILIES}; do
  echo "=== ${family}: per-sigma status ==="
  case "${family}" in
    smoke_v8) sh "${SCRIPT_DIR}/auto_sweep_monitor.sh" --family smoke_v8 --modes hw,hd,f9,id --status ${DETAIL_FLAG} ;;
    smoke_v9) sh "${SCRIPT_DIR}/auto_sweep_monitor.sh" --family smoke_v9 --configs hwhd,f9hw,f9hd,f9hwhd --status ${DETAIL_FLAG} ;;
    *) echo "Unknown family: ${family}" >&2; exit 1 ;;
  esac
  echo ""
  echo "=== ${family}: last 15 monitor decisions ==="
  ssh IDP "tail -15 '${MONITOR_DIR}/auto_sweep_monitor_${family}.log' 2>/dev/null" || echo "  (no log yet)"
  echo ""
  halts="$(ssh IDP "grep -c 'HALT:' '${MONITOR_DIR}/auto_sweep_monitor_${family}.log' 2>/dev/null; true")"
  halts="${halts:-0}"
  if [ "${halts}" -gt 0 ]; then
    echo "  !! ${halts} HALT line(s) in this family's log -- needs manual review (see --halts-only) !!"
  fi
  echo ""
done
