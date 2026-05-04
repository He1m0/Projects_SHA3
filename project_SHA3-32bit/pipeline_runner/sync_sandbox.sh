#!/usr/bin/env sh
#
# Sync updated code files from the canonical repo into one or all sandboxes.
# Run this ON the remote host (IDP) after a git pull in Projects_SHA3.
#
# Only code-only files are synced (no Raw/, HDF5, templateLDA, runs_archive).
# This mirrors what setup_sandbox.sh installs but is safe to run on a live
# sandbox — it overwrites scripts without touching pipeline outputs.

set -eu

BASE_DIR="/storage/ge96pug"
REPO_SRC=""
LABEL=""
ALL=0
DRY_RUN=0

print_help() {
  cat <<'EOF'
Usage:
  sh sync_sandbox.sh --label LABEL [options]
  sh sync_sandbox.sh --all [options]

Required (one of):
  --label LABEL   Sync only Projects_SHA3_sandbox_<LABEL>
  --all           Sync every Projects_SHA3_sandbox_*/ found under --base-dir

Options:
  --base-dir PATH   Parent directory (default: /storage/ge96pug)
  --repo-src PATH   Source repo (default: <base-dir>/Projects_SHA3)
  --dry-run         Print what would be copied without changing anything
  -h, --help        Show this help

What gets synced:
  KeccakSim_v2.py, KeccakSim_BI_TA.py            (sandbox root)
  project_SHA3-32bit/global_config.py
  project_SHA3-32bit/run_*.sh
  project_SHA3-32bit/pipeline_runner/*.sh
  project_SHA3-32bit/pipeline_runner/*.py
  project_SHA3-32bit/pipeline_runner/*.md
  project_SHA3-32bit/pipeline_runner/envs/*

Typical workflow:
  git pull origin <branch>                       # in Projects_SHA3 on IDP
  sh sync_sandbox.sh --all                       # propagate to all sandboxes
  sh sync_sandbox.sh --label f9_noise --dry-run  # preview one sandbox
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --label)    LABEL="$2";    shift 2 ;;
    --all)      ALL=1;         shift ;;
    --base-dir) BASE_DIR="$2"; shift 2 ;;
    --repo-src) REPO_SRC="$2"; shift 2 ;;
    --dry-run)  DRY_RUN=1;    shift ;;
    -h|--help)  print_help; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; print_help >&2; exit 2 ;;
  esac
done

if [ -z "${LABEL}" ] && [ "${ALL}" -eq 0 ]; then
  echo "Error: --label or --all is required" >&2; exit 2
fi

REPO_SRC="${REPO_SRC:-${BASE_DIR}/Projects_SHA3}"
if [ ! -d "${REPO_SRC}" ]; then
  echo "Error: repo source not found: ${REPO_SRC}" >&2; exit 1
fi

maybe_cp() {
  SRC="$1"
  DEST="$2"
  [ -f "${SRC}" ] || return 0
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  [dry] $(basename "${SRC}") -> ${DEST}"
  else
    cp "${SRC}" "${DEST}"
    echo "  synced $(basename "${SRC}")"
  fi
}

sync_one() {
  SANDBOX="$1"
  if [ ! -d "${SANDBOX}" ]; then
    echo "warn: sandbox not found: ${SANDBOX}"; return
  fi
  echo "=== $(basename "${SANDBOX}") ==="

  PROJ_SRC="${REPO_SRC}/project_SHA3-32bit"
  PROJ_DEST="${SANDBOX}/project_SHA3-32bit"

  if [ ! -d "${PROJ_DEST}" ]; then
    echo "  warn: project dir missing in sandbox — run setup_sandbox.sh first"; return
  fi

  # simulator scripts at sandbox root
  for SIM in "${REPO_SRC}/KeccakSim_v2.py" "${REPO_SRC}/KeccakSim_BI_TA.py"; do
    maybe_cp "${SIM}" "${SANDBOX}/$(basename "${SIM}")"
  done

  # global_config and top-level chain scripts
  maybe_cp "${PROJ_SRC}/global_config.py" "${PROJ_DEST}/global_config.py"
  for F in "${PROJ_SRC}/"run_*.sh; do
    [ -f "$F" ] && maybe_cp "$F" "${PROJ_DEST}/$(basename "${F}")"
  done

  # pipeline_runner scripts (not runs_archive or trace cache dirs)
  for F in "${PROJ_SRC}/pipeline_runner/"*.sh \
            "${PROJ_SRC}/pipeline_runner/"*.py \
            "${PROJ_SRC}/pipeline_runner/"*.md; do
    [ -f "$F" ] || continue
    maybe_cp "$F" "${PROJ_DEST}/pipeline_runner/$(basename "${F}")"
  done

  # env profiles
  if [ -d "${PROJ_SRC}/pipeline_runner/envs" ]; then
    mkdir -p "${PROJ_DEST}/pipeline_runner/envs"
    for F in "${PROJ_SRC}/pipeline_runner/envs/"*; do
      [ -f "$F" ] && maybe_cp "$F" \
        "${PROJ_DEST}/pipeline_runner/envs/$(basename "${F}")"
    done
  fi
}

if [ "${ALL}" -eq 1 ]; then
  FOUND=0
  for SANDBOX in "${BASE_DIR}/Projects_SHA3_sandbox_"*/; do
    [ -d "${SANDBOX}" ] || continue
    FOUND=1
    sync_one "${SANDBOX%/}"
  done
  [ "${FOUND}" -eq 1 ] || echo "No sandboxes found under ${BASE_DIR}"
else
  sync_one "${BASE_DIR}/Projects_SHA3_sandbox_${LABEL}"
fi

echo
if [ "${DRY_RUN}" -eq 1 ]; then
  echo "Dry run complete — no files changed"
else
  echo "Sync complete"
fi
