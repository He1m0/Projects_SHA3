#!/usr/bin/env sh
#
# Create a self-contained pipeline sandbox on the remote host (IDP).
# Run this ON the remote host, not locally.
#
# Copies code-only files from the canonical repo into a new sandbox dir,
# optionally creates a matching traces/ dir and a tmux session.
#
# Prerequisites:
#   - <base-dir>/Projects_SHA3 must exist and be up-to-date (git pull first)
#   - Run as the same user that owns the storage tree

set -eu

BASE_DIR="/storage/ge96pug"
REPO_SRC=""
LABEL=""
WITH_TRACES=0
WITH_TMUX=0
FORCE=0

print_help() {
  cat <<'EOF'
Usage:
  sh setup_sandbox.sh --label LABEL [options]

Required:
  --label LABEL     Short run identifier (e.g. f9_noise).
                    Creates Projects_SHA3_sandbox_<LABEL>/ under --base-dir.

Options:
  --base-dir PATH   Parent directory for sandboxes (default: /storage/ge96pug)
  --repo-src PATH   Source repo to copy from (default: <base-dir>/Projects_SHA3)
  --with-traces     Also create traces_<LABEL>/ directory
  --with-tmux       Start a detached tmux session named <LABEL>
  --force           Overwrite if the sandbox already exists
  -h, --help        Show this help

What gets copied (code-only; Raw/, *.hdf5, templateLDA/ are excluded):
  KeccakSim_v2.py / KeccakSim_BI_TA.py         at sandbox root
  project_SHA3-32bit/global_config.py
  project_SHA3-32bit/run_*.sh
  project_SHA3-32bit/pipeline_runner/ (scripts + envs, no runs_archive)
  project_SHA3-32bit/Bit_Tables/
  project_SHA3-32bit/000{1..5}_*/Code_*  and  template_*  and
      get_answers / bit_table_generation / plot_scans /
      Iteration_Scan_* / Rate_Scan_*  subdirs

After creation:
  cd <sandbox>/project_SHA3-32bit/pipeline_runner
  export TRACES_DIR=<base-dir>/traces_<LABEL>
  sh run_full_pipeline.sh --env-file envs/<profile>.env
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --label)       LABEL="$2";    shift 2 ;;
    --base-dir)    BASE_DIR="$2"; shift 2 ;;
    --repo-src)    REPO_SRC="$2"; shift 2 ;;
    --with-traces) WITH_TRACES=1; shift ;;
    --with-tmux)   WITH_TMUX=1;   shift ;;
    --force)       FORCE=1;       shift ;;
    -h|--help)     print_help; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; print_help >&2; exit 2 ;;
  esac
done

if [ -z "${LABEL}" ]; then
  echo "Error: --label is required" >&2; exit 2
fi

REPO_SRC="${REPO_SRC:-${BASE_DIR}/Projects_SHA3}"
if [ ! -d "${REPO_SRC}" ]; then
  echo "Error: repo source not found: ${REPO_SRC}" >&2; exit 1
fi

SANDBOX="${BASE_DIR}/Projects_SHA3_sandbox_${LABEL}"
TRACES="${BASE_DIR}/traces_${LABEL}"

if [ -e "${SANDBOX}" ]; then
  if [ "${FORCE}" -eq 1 ]; then
    echo "Removing existing sandbox: ${SANDBOX}"
    rm -rf "${SANDBOX}"
  else
    echo "Error: ${SANDBOX} already exists (pass --force to overwrite)" >&2; exit 3
  fi
fi

echo "Creating sandbox: ${SANDBOX}"
mkdir -p "${SANDBOX}"

# --- simulator scripts at sandbox root ---
for SIM in "${REPO_SRC}/KeccakSim_v2.py" "${REPO_SRC}/KeccakSim_BI_TA.py"; do
  if [ -f "${SIM}" ]; then
    cp "${SIM}" "${SANDBOX}/"
    echo "  copied $(basename "${SIM}")"
  fi
done

# --- project_SHA3-32bit tree ---
PROJ_SRC="${REPO_SRC}/project_SHA3-32bit"
PROJ_DEST="${SANDBOX}/project_SHA3-32bit"
mkdir -p "${PROJ_DEST}"

# top-level config and chain scripts
for F in "${PROJ_SRC}/global_config.py" "${PROJ_SRC}/"run_*.sh; do
  [ -f "$F" ] && cp "$F" "${PROJ_DEST}/" && echo "  copied $(basename "${F}")"
done

# pipeline_runner: scripts + envs, no runs_archive or heavy trace dirs
mkdir -p "${PROJ_DEST}/pipeline_runner/envs"
for F in "${PROJ_SRC}/pipeline_runner/"*.sh \
          "${PROJ_SRC}/pipeline_runner/"*.py \
          "${PROJ_SRC}/pipeline_runner/"*.md; do
  [ -f "$F" ] && cp "$F" "${PROJ_DEST}/pipeline_runner/"
done
# Use find to include dotfiles (.env_*) which shell glob * misses.
find "${PROJ_SRC}/pipeline_runner/envs/" -maxdepth 1 -type f \
  -exec cp {} "${PROJ_DEST}/pipeline_runner/envs/" \;

# Bit_Tables
if [ -d "${PROJ_SRC}/Bit_Tables" ]; then
  cp -r "${PROJ_SRC}/Bit_Tables" "${PROJ_DEST}/"
  echo "  copied Bit_Tables/"
fi

# pipeline stages: code subdirs only; Raw/ is created empty as a placeholder
for STAGE_DIR in "${PROJ_SRC}/0001_reference" \
                 "${PROJ_SRC}/0002_detection" \
                 "${PROJ_SRC}/0003_training" \
                 "${PROJ_SRC}/0004_validation" \
                 "${PROJ_SRC}/0005_SASCA"; do
  [ -d "${STAGE_DIR}" ] || continue
  STAGE_NAME="$(basename "${STAGE_DIR}")"
  STAGE_DEST="${PROJ_DEST}/${STAGE_NAME}"
  mkdir -p "${STAGE_DEST}/Raw"

  for SUBDIR in "${STAGE_DIR}"/Code_* \
                "${STAGE_DIR}"/template_* \
                "${STAGE_DIR}"/get_answers \
                "${STAGE_DIR}"/bit_table_generation \
                "${STAGE_DIR}"/plot_scans \
                "${STAGE_DIR}"/Iteration_Scan_* \
                "${STAGE_DIR}"/Rate_Scan_*; do
    [ -d "${SUBDIR}" ] || continue
    DEST_SUBDIR="${STAGE_DEST}/$(basename "${SUBDIR}")"
    mkdir -p "${DEST_SUBDIR}"
    # Copy only code/script files; skip data artifacts (*.zip, *.npy, *.hdf5)
    # so that pre-existing pipeline outputs in the source repo don't short-circuit
    # the pipeline's idempotency checks in the new sandbox.
    find "${SUBDIR}" -maxdepth 1 -type f ! -name '*.zip' ! -name '*.npy' ! -name '*.hdf5' \
      -exec cp {} "${DEST_SUBDIR}/" \;
  done
  echo "  copied ${STAGE_NAME}/"
done

# --- traces directory ---
if [ "${WITH_TRACES}" -eq 1 ]; then
  mkdir -p "${TRACES}"
  echo "Created traces dir: ${TRACES}"
fi

# --- tmux session ---
if [ "${WITH_TMUX}" -eq 1 ]; then
  if command -v tmux >/dev/null 2>&1; then
    tmux new-session -d -s "${LABEL}" 2>/dev/null || \
      echo "warn: tmux session '${LABEL}' already exists; skipping"
    echo "Started tmux session: ${LABEL}"
  else
    echo "warn: tmux not available; skipping session creation"
  fi
fi

echo
echo "Sandbox ready: ${SANDBOX}"
echo "Next:"
echo "  export TRACES_DIR=${TRACES}"
echo "  cd ${PROJ_DEST}/pipeline_runner"
echo "  sh run_full_pipeline.sh --env-file envs/<profile>.env"
