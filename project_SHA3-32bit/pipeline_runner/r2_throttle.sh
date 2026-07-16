#!/usr/bin/env sh
# One-shot rescue script for the 2026-07-14 R2 thread-oversubscription
# incident: detect_script.py fans out to ~1 BLAS thread per core (127
# threads observed on this 192-core host) with no cap, so as few as 2-3
# concurrent R2 processes already push load average past 1000. The already
# in-flight batch (launched before script_all.sh was patched to cap
# threads, see Code_detection_R2/script_all.sh) has ~26 detect_script
# processes paused via SIGSTOP (frozen mid-computation, zero progress
# lost -- NOT killed) plus 2 left running.
#
# This script keeps exactly TARGET detect_script processes actively
# runnable at a time, SIGCONT-ing one more from the paused pool whenever an
# active one exits (finishes or errors), until the whole paused backlog has
# drained. Self-contained -- runs directly on IDP in a detached tmux
# session, no ssh/polling dependency from the controlling machine.
#
# Usage (on IDP): sh r2_throttle.sh [TARGET]

set -eu
TARGET="${1:-2}"
POLL=15
LOG="$(dirname "$0")/r2_throttle.log"

logmsg() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "${LOG}"
}

logmsg "=== r2_throttle starting: target=${TARGET} poll=${POLL}s ==="

while :; do
  pids="$(pgrep -f detect_script || true)"
  if [ -z "${pids}" ]; then
    logmsg "no detect_script processes remain -- throttle finished, backlog fully drained"
    break
  fi

  active=0
  stopped_pids=""
  for pid in ${pids}; do
    stat="$(awk '{print $3}' "/proc/${pid}/stat" 2>/dev/null || echo '?')"
    case "${stat}" in
      T) stopped_pids="${stopped_pids} ${pid}" ;;
      *) active=$((active + 1)) ;;
    esac
  done

  need=$((TARGET - active))
  if [ "${need}" -gt 0 ] && [ -n "${stopped_pids}" ]; then
    n=0
    for pid in ${stopped_pids}; do
      [ "${n}" -ge "${need}" ] && break
      if kill -CONT "${pid}" 2>/dev/null; then
        logmsg "resumed pid=${pid} (active was ${active}, target ${TARGET})"
        n=$((n + 1))
      fi
    done
  fi

  sleep "${POLL}"
done
