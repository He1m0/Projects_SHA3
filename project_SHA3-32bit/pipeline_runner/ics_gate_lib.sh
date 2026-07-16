#!/usr/bin/env sh
# Shared ICS-gate automation library, extracted from launch_paperscale_v6.sh's
# ics_scan()/fix_ics()/resume()/check_r2_warn_only() (proven manually on
# paperscale_v6_hd_pure and smoke_v8_granularity_word_id_sigma1p0).
#
# Every function here is parameterized by a sandbox "label" (the env name,
# e.g. "smoke_v8_granularity_word_hd_sigma1p0" -- matches run_sandboxes.sh's
# ENV_NAME/DIR_LABEL) and, where needed, the local env file path -- no
# hardcoded family name, unlike the paperscale_v6 original.
#
# Dual execution mode via SSH_TARGET:
#   - SSH_TARGET set (e.g. "IDP"): every check/mutation goes over ssh from
#     wherever this is sourced. Used for local-machine validation/dry-run
#     against real remote state (see Task #6) without needing to be on IDP.
#   - SSH_TARGET unset/empty: runs directly (sh -c, no ssh) -- this is the
#     mode auto_sweep_monitor.sh uses when it runs natively inside a tmux
#     session ON IDP itself, so the unattended sweep has zero ssh dependency
#     and survives ssh disconnects / local-machine/session churn.
#
# Usage: . "${SCRIPT_DIR}/ics_gate_lib.sh"

: "${SSH_TARGET:=}"

remote_exec() {
  # Run $1 either via ssh SSH_TARGET, or directly if SSH_TARGET is empty.
  if [ -n "${SSH_TARGET}" ]; then
    ssh "${SSH_TARGET}" "$1"
  else
    sh -c "$1"
  fi
}

# ── remote path helpers ──────────────────────────────────────────────────────
#
# Its TMUX_LABEL and log file both carry a "sandbox_" prefix that the
# sandbox dir name does not -- verified against live tmux sessions/log paths
# on IDP (run_sandboxes.sh: TMUX_LABEL="sandbox_${ENV_NAME}",
# log_path="${pipeline_dir}/${TMUX_LABEL}.log"). Do not drop this prefix on
# the log/tmux side -- launch_paperscale_v6.sh's own (never-yet-exercised)
# resume() gets this wrong (uses an unprefixed log path), which is exactly
# the kind of drift this shared lib exists to avoid.

sandbox_dir_for() {
  # label -> /storage/ge96pug/Projects_SHA3_sandbox_<label>
  printf "/storage/ge96pug/Projects_SHA3_sandbox_%s" "$1"
}

pipeline_runner_dir_for() {
  printf "%s/project_SHA3-32bit/pipeline_runner" "$(sandbox_dir_for "$1")"
}

tmux_label_for() {
  printf "sandbox_%s" "$1"
}

log_path_for() {
  printf "%s/%s.log" "$(pipeline_runner_dir_for "$1")" "$(tmux_label_for "$1")"
}

# ── state detection (always re-derive from the log, never cache) ────────────

is_complete() {
  label="$1"
  log="$(log_path_for "${label}")"
  remote_exec "[ -f '${log}' ] && grep -q 'COMPLETE: run_full_pipeline finished' '${log}' 2>/dev/null"
}

ics_gate_failed() {
  # A resumed run appends to the SAME log file (never truncated), so a stale
  # ERROR line from an earlier, since-fixed attempt would otherwise look
  # like an ongoing failure forever (verified: this is a real, not
  # hypothetical, false positive against the live id_sigma1p0 sandbox, whose
  # log still carries the original level=090 failure even though the
  # level=030 resume succeeded and is progressing). Only count the ERROR
  # line if it comes at-or-after the LAST "CHECK: validating training ICS
  # archive" line, i.e. it belongs to the most recent attempt.
  label="$1"
  log="$(log_path_for "${label}")"
  remote_exec "[ -f '${log}' ] && awk '
    /CHECK: validating training ICS archive/ { last_check = NR }
    /ERROR: ICS archive validation failed\./ { last_error = NR }
    END { exit !(last_error > last_check) }
  ' '${log}'"
}


has_other_error() {
  # Any hard failure that is NOT the (recoverable) ICS gate error.
  label="$1"
  log="$(log_path_for "${label}")"
  remote_exec "[ -f '${log}' ] && grep -qE '^Error:' '${log}' 2>/dev/null && ! grep -q 'ERROR: ICS archive validation failed.' '${log}' 2>/dev/null"
}

not_started() {
  label="$1"
  sb="$(sandbox_dir_for "${label}")"
  ! remote_exec "[ -d '${sb}' ]"
}

is_orphaned() {
  # A sandbox that is not_started/complete/ics_gate_failed/has_other_error
  # reads as plain "running" from log content alone -- but if its driving
  # tmux session has already died (process killed, host issue, etc.)
  # without ever writing an "Error:" line, it is actually dead, not running.
  # This is exactly the blind spot that let the 24-sandbox incident
  # (RUN_LOG_auto_sweep.md, 2026-07-14) sit unnoticed for hours: the
  # relaunch script's own log ended in "Killed" with no Error: line to grep.
  # Callers should only check this for labels already past not_started and
  # not yet complete/errored, since a legitimately finished session also has
  # no tmux session left.
  label="$1"
  tmux_label="$(tmux_label_for "${label}")"
  ! remote_exec "tmux has-session -t '${tmux_label}' 2>/dev/null"
}

# ── fine-grained pipeline position (which stage a "running" sandbox is at) ──
# run_full_pipeline.sh's log() prefixes every stage-transition line with a
# "[YYYY-MM-DD HH:MM:SS]" timestamp (START/DONE per run_stage, CHECK before
# training, SIM/ZIP/MOVE/INFO during deploy, COMPLETE at the very end) --
# unlike the noisier untimestamped python/zip output interleaved in the same
# log. The last such line is the current pipeline position.

last_stage_for() {
  label="$1"
  log="$(log_path_for "${label}")"
  remote_exec "[ -f '${log}' ] && grep '^\[20' '${log}' 2>/dev/null | tail -1"
}

# ── concurrency gate ──────────────────────────────────────────────────────────

r2_count() {
  remote_exec "pgrep -c -f detect_script 2>/dev/null || echo 0"
}

r2_pressure() {
  # r2_count() alone only sees detect_script processes that have already
  # started, but a freshly launched sigma doesn't reach R2 for several
  # minutes (reference sim -> detection preprocessing -> intermediate
  # values run first). A burst of near-simultaneous launches all pass a
  # real-time r2_count() check -- none of them are visible yet -- and then
  # pile onto R2 together once they all arrive minutes later (verified: a
  # real ~40-launch batch stayed at r2_count()=0 for 6+ minutes post-launch
  # while all 40 were racing toward R2 at once).
  #
  # Host-wide (not just this monitor's own family/units), so smoke_v8,
  # smoke_v9, and any manually-launched paperscale sandboxes all count
  # against the same shared cap, matching r2_count()'s pgrep being
  # host-wide too. Counts every sandbox that is launched (dir exists), not
  # complete/halted, and hasn't yet finished its R2 stage -- accurate the
  # instant a sandbox dir is created, with no process-visibility lag.
  remote_exec "
    total=0
    for d in /storage/ge96pug/Projects_SHA3_sandbox_*/; do
      [ -d \"\$d\" ] || continue
      label=\$(basename \"\$d\" | sed 's/^Projects_SHA3_sandbox_//')
      log=\"\${d}project_SHA3-32bit/pipeline_runner/sandbox_\${label}.log\"
      if [ ! -f \"\$log\" ]; then total=\$((total+1)); continue; fi
      grep -q 'COMPLETE: run_full_pipeline finished' \"\$log\" 2>/dev/null && continue
      if grep -qE '^Error:' \"\$log\" 2>/dev/null && ! grep -q 'ERROR: ICS archive validation failed.' \"\$log\" 2>/dev/null; then continue; fi
      grep -q 'DONE : 0002 detection R2' \"\$log\" 2>/dev/null && continue
      total=\$((total+1))
    done
    echo \$total
  "
}

# ── ICS boundary scan (all 9 threshold zips already exist after detection,
#    regardless of which level is configured -- no detection rerun needed) ──

ics_scan_label() {
  label="$1"
  sb="$(sandbox_dir_for "${label}")/project_SHA3-32bit"
  remote_exec "
sb='${sb}'
if [ ! -d \"\$sb/0002_detection/Code_extract_ics\" ]; then
  echo 'NO valid level found (detection not complete)'
  exit 0
fi
found=0
for level in 090 080 070 060 050 040 030 020 010; do
  zipf=\"\$sb/0002_detection/Code_extract_ics/ics_original_\${level}.zip\"
  if [ ! -f \"\$zipf\" ]; then continue; fi
  result=\$(python3 \"\$sb/pipeline_runner/check_ics_archive.py\" --ics-zip \"\$zipf\" 2>&1)
  if echo \"\$result\" | grep -q '^OK:'; then
    echo \"\$level\"
    found=1
    break
  fi
done
if [ \"\$found\" -eq 0 ]; then echo 'NO valid level found'; fi
"
}

# ── ICS level fix (after detection, before training) ─────────────────────────
# Patches the sandbox's active .env, the sandbox's deployed envs/ copy, and
# the local env file the launcher will use for any not-yet-launched sigmas.

fix_ics_label() {
  label="$1"; env_file="$2"; level="$3"
  sb="$(sandbox_dir_for "${label}")/project_SHA3-32bit"
  env_base="$(basename "${env_file}")"
  echo "  Applying ICS fix: ${label} -> level ${level}"
  for f in "${sb}/.env" "${sb}/pipeline_runner/envs/${env_base}"; do
    remote_exec "[ -f $(printf "'%s'" "$f") ] && sed -i \
      -e 's/SHA3_TRAINING_ICS_LEVEL=.*/SHA3_TRAINING_ICS_LEVEL=${level}/' \
      -e 's/SHA3_VALIDATION_TEMPLATE_TAG=.*/SHA3_VALIDATION_TEMPLATE_TAG=${level}/' \
      -e 's/SHA3_VALIDATION_ICS_TAG=.*/SHA3_VALIDATION_ICS_TAG=${level}/' \
      -e 's/SHA3_SASCA_TEMPLATE_TAG=.*/SHA3_SASCA_TEMPLATE_TAG=${level}/' \
      -e 's/SHA3_SASCA_ICS_TAG=.*/SHA3_SASCA_ICS_TAG=${level}/' \
      $(printf "'%s'" "$f") || true"
  done
  if [ -f "${env_file}" ]; then
    sed -i \
      -e "s/SHA3_TRAINING_ICS_LEVEL=.*/SHA3_TRAINING_ICS_LEVEL=${level}/" \
      -e "s/SHA3_VALIDATION_TEMPLATE_TAG=.*/SHA3_VALIDATION_TEMPLATE_TAG=${level}/" \
      -e "s/SHA3_VALIDATION_ICS_TAG=.*/SHA3_VALIDATION_ICS_TAG=${level}/" \
      -e "s/SHA3_SASCA_TEMPLATE_TAG=.*/SHA3_SASCA_TEMPLATE_TAG=${level}/" \
      -e "s/SHA3_SASCA_ICS_TAG=.*/SHA3_SASCA_ICS_TAG=${level}/" \
      "${env_file}"
  fi
}

# ── WORKSPACE_DIR placeholder fix (retroactive, pre-deploy_env_file fix) ─────
# Some gen_envs.py scripts (e.g. smoke_v10_word_mix) embed a
# ${WORKSPACE_DIR} placeholder in SIM_SCRIPT_OVERRIDE, meant to be resolved
# to the sandbox's own absolute path. run_sandboxes.sh's deploy_env_file()
# now resolves it for every *new* deploy; this patches sandboxes deployed
# before that fix existed. Unlike fix_ics_label(), does NOT touch the local
# template file -- WORKSPACE_DIR is sandbox-specific, not a value that
# should be baked into the portable, not-yet-deployed template.

fix_workspace_dir_label() {
  label="$1"; env_base="$2"
  ws="$(sandbox_dir_for "${label}")"
  sb="${ws}/project_SHA3-32bit"
  echo "  Applying WORKSPACE_DIR fix: ${label} -> ${ws}"
  for f in "${sb}/.env" "${sb}/pipeline_runner/envs/${env_base}"; do
    remote_exec "[ -f $(printf "'%s'" "$f") ] && sed -i \
      -e 's#\${WORKSPACE_DIR}#${ws}#g' \
      $(printf "'%s'" "$f") || true"
  done
}

# ── resume: training onward, same tmux session label ──────────────────────────

resume_label() {
  label="$1"
  plr="$(pipeline_runner_dir_for "${label}")"
  log="$(log_path_for "${label}")"
  tmux_label="$(tmux_label_for "${label}")"
  cmd="cd ${plr} && sh run_full_pipeline.sh --skip-detection --env-file ../.env"
  # The original run already exited (it died at the ICS gate under set -eu),
  # but kill any lingering session with the same name defensively before
  # reusing the label -- never silently no-op a resume.
  remote_exec "tmux kill-session -t '${tmux_label}' 2>/dev/null; tmux new-session -d -s '${tmux_label}' \"${cmd} > '${log}' 2>&1\""
}
