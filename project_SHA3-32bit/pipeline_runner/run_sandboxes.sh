#!/usr/bin/env sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)"
DEFAULT_LOCAL_BASE_DIR="$(CDPATH= cd -- "${REPO_ROOT}/.." && pwd)"

ENVS_DIR=""
LOGS_DIR=""
SSH_TARGET=""
BASE_DIR=""
REPO_SRC=""
FORCE=0
PIPELINE_ARGS=""

print_help() {
	cat <<'EOF'
Usage:
	sh run_sandboxes.sh --envs-dir PATH [options] [-- <run_full_pipeline args>]

Required:
	--envs-dir PATH   Folder containing .env_* files to run (non-recursive)

Options:
	--ssh TARGET      Run on remote host via ssh (e.g. user@host)
	--base-dir PATH   Base dir for sandboxes/traces (default: local repo parent; remote: /storage/ge96pug)
	--repo-src PATH   Repo source to copy from (default: local repo root; remote: <base-dir>/Projects_SHA3)
	--logs-dir PATH   Write all logs to this folder (default: per-sandbox pipeline_runner/<tmux_label>.log)
	--force           Overwrite existing sandbox and tmux session
	-h, --help        Show this help

Notes:
	- Each env creates Projects_SHA3_sandbox_<env_name> and traces_<env_name>.
	- tmux session name is sandbox_<env_name>.
	- Pass extra run_full_pipeline.sh options after -- (e.g. --serial-scans).
EOF
}

while [ "$#" -gt 0 ]; do
	case "$1" in
		--envs-dir) ENVS_DIR="$2"; shift 2 ;;
		--logs-dir) LOGS_DIR="$2"; shift 2 ;;
		--ssh) SSH_TARGET="$2"; shift 2 ;;
		--base-dir) BASE_DIR="$2"; shift 2 ;;
		--repo-src) REPO_SRC="$2"; shift 2 ;;
		--force) FORCE=1; shift ;;
		-h|--help) print_help; exit 0 ;;
		--)
			shift
			PIPELINE_ARGS="$*"
			break
			;;
		*)
			echo "Error: unknown option: $1" >&2
			print_help >&2
			exit 2
			;;
	esac
done

if [ -z "${ENVS_DIR}" ]; then
	echo "Error: --envs-dir is required" >&2
	exit 2
fi

if [ ! -d "${ENVS_DIR}" ]; then
	echo "Error: envs dir not found: ${ENVS_DIR}" >&2
	exit 1
fi

IS_REMOTE=0
if [ -n "${SSH_TARGET}" ]; then
	IS_REMOTE=1
fi

if [ -z "${BASE_DIR}" ]; then
	if [ "${IS_REMOTE}" -eq 1 ]; then
		BASE_DIR="/storage/ge96pug"
	else
		BASE_DIR="${DEFAULT_LOCAL_BASE_DIR}"
	fi
fi

if [ -z "${REPO_SRC}" ]; then
	if [ "${IS_REMOTE}" -eq 1 ]; then
		REPO_SRC="${BASE_DIR}/Projects_SHA3"
	else
		REPO_SRC="${REPO_ROOT}"
	fi
fi

quote_sh() {
	printf "'%s'" "$(printf "%s" "$1" | sed "s/'/'\\''/g")"
}

run_local() {
	sh -c "$1"
}

run_remote() {
	ssh "${SSH_TARGET}" "$1"
}

ensure_tmux_local() {
	if ! command -v tmux >/dev/null 2>&1; then
		echo "Error: tmux not available locally" >&2
		exit 1
	fi
}

ensure_tmux_remote() {
	run_remote "command -v tmux >/dev/null 2>&1" || {
		echo "Error: tmux not available on remote host" >&2
		exit 1
	}
}

list_envs() {
	find "${ENVS_DIR}" -maxdepth 1 -type f -name ".env*" | sort
}

env_to_name() {
	base_name="$(basename "$1")"
	name="${base_name#.env_}"
	if [ "${name}" = "${base_name}" ]; then
		name="${base_name#.env}"
	fi
	printf "%s" "${name}"
}

ensure_tmux_session() {
	label="$1"
	if [ "${IS_REMOTE}" -eq 1 ]; then
		if run_remote "tmux has-session -t $(quote_sh "${label}") 2>/dev/null"; then
			if [ "${FORCE}" -eq 1 ]; then
				run_remote "tmux kill-session -t $(quote_sh "${label}")"
			else
				echo "warn: tmux session exists, skipping: ${label}" >&2
				return 1
			fi
		fi
	else
		if tmux has-session -t "${label}" >/dev/null 2>&1; then
			if [ "${FORCE}" -eq 1 ]; then
				tmux kill-session -t "${label}"
			else
				echo "warn: tmux session exists, skipping: ${label}" >&2
				return 1
			fi
		fi
	fi
	return 0
}

sandbox_path() {
	label="$1"
	printf "%s/Projects_SHA3_sandbox_%s" "${BASE_DIR}" "${label}"
}

sandbox_exists() {
	label="$1"
	path="$(sandbox_path "${label}")"
	if [ "${IS_REMOTE}" -eq 1 ]; then
		run_remote "test -e $(quote_sh "${path}")"
	else
		[ -e "${path}" ]
	fi
}

setup_sandbox() {
	label="$1"
	setup_cmd="sh $(quote_sh "${SCRIPT_DIR}/setup_sandbox.sh") --label $(quote_sh "${label}") --base-dir $(quote_sh "${BASE_DIR}") --repo-src $(quote_sh "${REPO_SRC}") --with-traces"
	if [ "${FORCE}" -eq 1 ]; then
		setup_cmd="${setup_cmd} --force"
	fi
	if [ "${IS_REMOTE}" -eq 1 ]; then
		setup_cmd="sh $(quote_sh "${REPO_SRC}/project_SHA3-32bit/pipeline_runner/setup_sandbox.sh") --label $(quote_sh "${label}") --base-dir $(quote_sh "${BASE_DIR}") --repo-src $(quote_sh "${REPO_SRC}") --with-traces"
		if [ "${FORCE}" -eq 1 ]; then
			setup_cmd="${setup_cmd} --force"
		fi
		run_remote "${setup_cmd}"
	else
		run_local "${setup_cmd}"
	fi
}

deploy_env_file() {
	env_src="$1"
	label="$2"
	env_dest_dir="${BASE_DIR}/Projects_SHA3_sandbox_${label}/project_SHA3-32bit/pipeline_runner/envs"
	env_base="$(basename "${env_src}")"
	if [ "${IS_REMOTE}" -eq 1 ]; then
		scp "${env_src}" "${SSH_TARGET}:${env_dest_dir}/${env_base}"
	else
		cp "${env_src}" "${env_dest_dir}/${env_base}"
	fi
	# Some gen_envs.py scripts (e.g. smoke_v10_word_mix) embed a
	# ${WORKSPACE_DIR} placeholder in SIM_SCRIPT_OVERRIDE -- it's only safe
	# to resolve once the sandbox's real path is known, which is here. Left
	# unresolved, it crashes any stage whose helpers re-source .env in a
	# fresh shell (e.g. 0003_training/template_profiling_bytes/init.sh,
	# under set -eu -- "WORKSPACE_DIR: unbound variable").
	workspace_dir="${BASE_DIR}/Projects_SHA3_sandbox_${label}"
	sub_cmd="sed -i 's#\${WORKSPACE_DIR}#${workspace_dir}#g' $(quote_sh "${env_dest_dir}/${env_base}")"
	if [ "${IS_REMOTE}" -eq 1 ]; then
		run_remote "${sub_cmd}"
	else
		run_local "${sub_cmd}"
	fi
}

start_tmux_run() {
	tmux_label="$1"
	env_file_base="$2"
	dir_label="$3"
	sandbox_dir="${BASE_DIR}/Projects_SHA3_sandbox_${dir_label}"
	traces_dir="${BASE_DIR}/traces_${dir_label}"
	pipeline_dir="${sandbox_dir}/project_SHA3-32bit/pipeline_runner"
	log_path=""

	if [ -n "${LOGS_DIR}" ]; then
		log_path="${LOGS_DIR}/${tmux_label}.log"
	else
		log_path="${pipeline_dir}/${tmux_label}.log"
	fi

	inner_cmd="cd \"${pipeline_dir}\" && export TRACES_DIR=\"${traces_dir}\" && sh run_full_pipeline.sh --env-file \"envs/${env_file_base}\" ${PIPELINE_ARGS}"

	if [ "${IS_REMOTE}" -eq 1 ]; then
		run_remote "mkdir -p $(quote_sh "$(dirname "${log_path}")")"
		run_remote "mkdir -p $(quote_sh "${traces_dir}")"
		quoted_inner=$(quote_sh "${inner_cmd}")
		run_remote "tmux new-session -d -s $(quote_sh "${tmux_label}") sh -lc ${quoted_inner}"
		run_remote "i=0; while ! tmux has-session -t $(quote_sh "${tmux_label}") 2>/dev/null && [ \"\${i}\" -lt 10 ]; do i=\$((i+1)); sleep 0.1; done"
		run_remote "tmux pipe-pane -o -t $(quote_sh "${tmux_label}:0.0") \"cat >> $(quote_sh "${log_path}")\""
	else
		mkdir -p "$(dirname "${log_path}")"
		mkdir -p "${traces_dir}"
		tmux new-session -d -s "${tmux_label}" sh -lc "${inner_cmd}"
		i=0
		while ! tmux has-session -t "${tmux_label}" >/dev/null 2>&1 && [ "${i}" -lt 10 ]; do
			i=$((i + 1))
			sleep 0.1
		done
		tmux pipe-pane -o -t "${tmux_label}:0.0" "cat >> '${log_path}'"
	fi
}

if [ "${IS_REMOTE}" -eq 1 ]; then
	ensure_tmux_remote
else
	ensure_tmux_local
fi

ENV_FILES="$(list_envs)"
if [ -z "${ENV_FILES}" ]; then
	echo "Error: no env files found in ${ENVS_DIR}" >&2
	exit 1
fi

echo "Using envs dir: ${ENVS_DIR}"
echo "Base dir: ${BASE_DIR}"
echo "Repo src: ${REPO_SRC}"
if [ "${IS_REMOTE}" -eq 1 ]; then
	echo "Remote: ${SSH_TARGET}"
else
	echo "Mode: local"
fi
if [ -n "${LOGS_DIR}" ]; then
	echo "Logs dir: ${LOGS_DIR}"
fi

STARTED=0
SKIPPED=0

echo ""
echo "Launching sandboxes:"

for ENV_PATH in ${ENV_FILES}; do
	ENV_BASE="$(basename "${ENV_PATH}")"
	ENV_NAME="$(env_to_name "${ENV_PATH}")"
	if [ -z "${ENV_NAME}" ]; then
		echo "warn: could not derive env name from ${ENV_BASE}; skipping" >&2
		SKIPPED=$((SKIPPED + 1))
		continue
	fi

	DIR_LABEL="${ENV_NAME}"
	TMUX_LABEL="sandbox_${ENV_NAME}"
	SANDBOX_DIR="$(sandbox_path "${DIR_LABEL}")"

	if [ "${FORCE}" -eq 0 ] && sandbox_exists "${DIR_LABEL}"; then
		echo "warn: sandbox exists, skipping: ${SANDBOX_DIR}" >&2
		SKIPPED=$((SKIPPED + 1))
		continue
	fi

	if ! ensure_tmux_session "${TMUX_LABEL}"; then
		SKIPPED=$((SKIPPED + 1))
		continue
	fi

	echo "  ${TMUX_LABEL} (${ENV_BASE}) -> ${SANDBOX_DIR}"
	if ! setup_sandbox "${DIR_LABEL}"; then
		echo "Error: failed to set up sandbox for ${ENV_BASE}" >&2
		exit 1
	fi
	if ! deploy_env_file "${ENV_PATH}" "${DIR_LABEL}"; then
		echo "Error: failed to deploy env file ${ENV_BASE} to sandbox" >&2
		exit 1
	fi
	if ! start_tmux_run "${TMUX_LABEL}" "${ENV_BASE}" "${DIR_LABEL}"; then
		echo "Error: failed to start tmux run for ${ENV_BASE}" >&2
		exit 1
	fi
	STARTED=$((STARTED + 1))
done

echo ""
echo "Done. Started: ${STARTED}; Skipped: ${SKIPPED}."
