#!/usr/bin/env sh
# 2026-07-14 R2 thread-oversubscription incident: kill+relaunch variant.
#
# Supersedes r2_throttle.sh for this incident. r2_throttle.sh assumed the
# in-flight backlog of unpatched (127-BLAS-thread) detect_script.py
# processes had to be drained slowly via SIGCONT at low concurrency
# (target=2) because killing them would waste real progress. Investigation
# showed the opposite: none of the affected sandboxes had finished R2 yet
# (all started within the last few minutes to ~35 min of a ~26-min solo R2
# stage), and script_all.sh was patched to cap BLAS threads to 4 (commit
# deployed to the master repo at 14:47, too late for these already-created
# sandboxes, each of which carries its own unpatched script_all.sh copy).
#
# So: kill every detect_script.py process that belongs to a
# Projects_SHA3_sandbox_* tree, then relaunch each one's run_full_pipeline
# with the thread-cap env vars exported directly (sidesteps needing to sync
# the patch into every sandbox's own script_all.sh copy), gated behind a
# concurrency cap that's now safe because every relaunched process is
# 4-thread-capped (TARGET x 4 threads vs 192 cores).
#
# 2026-07-14 follow-up fix: active_count() originally counted marker tmux
# sessions that only exit once a label's ENTIRE pipeline finishes (hours),
# not once its R2 stage finishes (minutes) -- so after the first TARGET
# relaunches it wedged forever, "active >= target", and the remaining
# labels were never relaunched (confirmed: 24 of the 44 killed sandboxes
# sat dead for hours). Fixed to track R2 completion via the label's own log
# instead of a full-pipeline-lifetime marker session.
#
# Usage (on IDP):
#   sh r2_kill_relaunch.sh [TARGET]                    -- discover live
#     detect_script processes, kill them, relaunch their labels (original
#     incident-response mode)
#   sh r2_kill_relaunch.sh [TARGET] --labels LBL...     -- skip discovery/kill
#     entirely and just relaunch the given (already-dead, no live process)
#     labels -- for finishing off labels a wedged prior run never got to

set -eu
TARGET="${1:-20}"
shift || true
POLL=10
LOG="$(dirname "$0")/r2_kill_relaunch.log"
BASE=/storage/ge96pug

logmsg() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "${LOG}"
}

if [ "${1:-}" = "--labels" ]; then
  shift
  labels="$*"
  n_labels=$(printf '%s\n' ${labels} | wc -w)
  logmsg "=== r2_kill_relaunch starting: target=${TARGET} (labels-only mode, no discovery/kill) ==="
  logmsg "relaunching ${n_labels} explicitly-given labels:${labels}"
else

# ── Step 1: snapshot affected sandboxes + kill their detect_script procs ────

logmsg "=== r2_kill_relaunch starting: target=${TARGET} ==="

labels=""
killed=0
for pid in $(pgrep -f detect_script || true); do
  cwd="$(readlink "/proc/${pid}/cwd" 2>/dev/null || true)"
  case "${cwd}" in
    "${BASE}"/Projects_SHA3_sandbox_*/project_SHA3-32bit/0002_detection/Code_detection_R2)
      sandbox_dir="${cwd%/project_SHA3-32bit/0002_detection/Code_detection_R2}"
      label="$(basename "${sandbox_dir}" | sed 's/^Projects_SHA3_sandbox_//')"
      labels="${labels} ${label}"
      kill -9 "${pid}" 2>/dev/null && killed=$((killed + 1)) || true
      ;;
    *)
      logmsg "skipping pid=${pid} cwd=${cwd:-<none>} -- not a sandbox R2 process, not touching"
      ;;
  esac
done

# de-dup labels (a sandbox can have >1 detect_script pid, though normally 1)
labels="$(printf '%s\n' ${labels} | sort -u | tr '\n' ' ')"
n_labels=$(printf '%s\n' ${labels} | wc -w)
logmsg "killed ${killed} unpatched detect_script processes across ${n_labels} sandboxes"
logmsg "affected labels:${labels}"

fi

# ── Step 2: relaunch each affected sandbox, thread-capped, behind TARGET ────

active_count() {
  # A label only holds a concurrency slot once THIS script has relaunched
  # it (tracked in launched_labels) and until ITS OWN R2 stage is done --
  # NOT until its whole pipeline (training/SASCA/rate-scan, hours) is done,
  # and NOT before it's even been relaunched (every not-yet-reached label
  # is also sitting at "not done R2" in its stale log, which would
  # otherwise make active_count() >= the full label count before anything
  # is even launched). Checked via the label's own log, not a marker
  # tmux session.
  n=0
  for l in ${launched_labels}; do
    log="${BASE}/Projects_SHA3_sandbox_${l}/project_SHA3-32bit/pipeline_runner/sandbox_${l}.log"
    if [ -f "${log}" ] && grep -q 'DONE : 0002 detection R2' "${log}" 2>/dev/null; then
      continue
    fi
    n=$((n + 1))
  done
  echo "${n}"
}

launched_labels=""
for label in ${labels}; do
  while :; do
    active="$(active_count)"
    [ "${active}" -lt "${TARGET}" ] && break
    logmsg "active relaunches=${active} >= target ${TARGET}, waiting before launching ${label}"
    sleep "${POLL}"
  done

  sandbox="${BASE}/Projects_SHA3_sandbox_${label}"
  plr="${sandbox}/project_SHA3-32bit/pipeline_runner"
  traces="${BASE}/traces_${label}"
  envf="envs/.env_${label}"
  log="${plr}/sandbox_${label}.log"
  tmux_name="sandbox_${label}"

  if [ ! -f "${plr}/${envf}" ]; then
    logmsg "SKIP ${label}: no ${envf} found under ${plr}, not relaunching"
    continue
  fi

  tmux kill-session -t "${tmux_name}" 2>/dev/null || true

  cmd="cd '${plr}' && printf '\n[%s] === r2_kill_relaunch: restarting (thread-capped) ===\n' \"\$(date '+%Y-%m-%d %H:%M:%S')\" >> '${log}' && TRACES_DIR='${traces}' OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4 NUMEXPR_NUM_THREADS=4 VECLIB_MAXIMUM_THREADS=4 sh run_full_pipeline.sh --skip-sim --env-file '${envf}' >> '${log}' 2>&1"

  tmux new-session -d -s "${tmux_name}" "${cmd}"
  launched_labels="${launched_labels} ${label}"

  logmsg "relaunched ${label} (TRACES_DIR=${traces}, 4-thread cap)"
done

logmsg "=== r2_kill_relaunch: all ${n_labels} sandboxes relaunched ==="
