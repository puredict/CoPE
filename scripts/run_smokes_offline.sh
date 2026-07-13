#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_ENV="${PROJECT_ROOT}/scripts/run_project_env.sh"
LOCAL_MODEL="/home/lijingsu/vla/models/openvla-7b"

STAMP="$(date +%Y%m%d_%H%M%S)"
AUDIT_DIR="${AUDIT_DIR:-${PROJECT_ROOT}/audit_outputs/${STAMP}_offline_smokes}"
ISOLATED_SMOKE_OUTPUTS="${AUDIT_DIR}/isolated_smoke_outputs"
COMMANDS_TSV="${AUDIT_DIR}/commands.tsv"

mkdir -p "${AUDIT_DIR}" "${ISOLATED_SMOKE_OUTPUTS}"

if ! command -v bwrap >/dev/null 2>&1; then
  echo "bwrap is required so smoke_outputs can be isolated without overwriting existing results." >&2
  exit 2
fi

if [[ ! -x "${RUN_ENV}" ]]; then
  echo "missing executable: ${RUN_ENV}" >&2
  exit 2
fi

if [[ ! -d "${LOCAL_MODEL}" ]]; then
  echo "missing local OpenVLA model directory: ${LOCAL_MODEL}" >&2
  exit 2
fi

printf 'index\texit\tcommand\tlog_path\n' > "${COMMANDS_TSV}"

BWRAP_PREFIX=(
  bwrap
  --bind / /
  --dev-bind /dev /dev
  --proc /proc
  --bind "${ISOLATED_SMOKE_OUTPUTS}" "${PROJECT_ROOT}/smoke_outputs"
)

run_logged() {
  local index="$1"
  shift
  local name="$1"
  shift
  local log="${AUDIT_DIR}/${index}_${name}.log"
  local stdout_file="${AUDIT_DIR}/${index}_${name}.stdout"
  local stderr_file="${AUDIT_DIR}/${index}_${name}.stderr"
  local command_text
  printf -v command_text '%q ' "$@"

  {
    printf 'COMMAND: %s\n' "${command_text% }"
    printf 'START: %s\n' "$(date -Is)"
  } > "${log}"

  set +e
  "$@" > "${stdout_file}" 2> "${stderr_file}"
  local exit_code=$?
  set -e

  {
    printf 'END: %s\n' "$(date -Is)"
    printf 'EXIT: %s\n' "${exit_code}"
    printf '\nSTDOUT:\n'
    cat "${stdout_file}"
    printf '\nSTDERR:\n'
    cat "${stderr_file}"
  } >> "${log}"

  printf '%s\t%s\t%s\t%s\n' "${index}_${name}" "${exit_code}" "${command_text% }" "${log}" >> "${COMMANDS_TSV}"
  return "${exit_code}"
}

overall=0

run_logged 00 gpu_before nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv || overall=1

run_logged 01 check_vla_env \
  "${BWRAP_PREFIX[@]}" "${RUN_ENV}" python check_vla_env.py || overall=1

run_logged 02 openvla_smoke \
  "${BWRAP_PREFIX[@]}" "${RUN_ENV}" python openvla_smoke.py \
    --model "${LOCAL_MODEL}" \
    --device cuda:0 \
    --unnorm-key bridge_orig || overall=1

run_logged 03 libero_base_closed_loop_smoke \
  "${BWRAP_PREFIX[@]}" "${RUN_ENV}" python libero_base_closed_loop_smoke.py || overall=1

run_logged 04 libero_disturbance_smoke \
  "${BWRAP_PREFIX[@]}" "${RUN_ENV}" python libero_disturbance_smoke.py || overall=1

run_logged 98 generated_files \
  find "${AUDIT_DIR}" -type f '(' -name '*.json' -o -name '*.png' -o -name '*.mp4' ')' -printf '%TY-%Tm-%Td %TH:%TM:%TS %s %p\n' || overall=1

run_logged 99 gpu_after nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv || overall=1

{
  printf 'audit_dir=%s\n' "${AUDIT_DIR}"
  printf 'isolated_smoke_outputs=%s\n' "${ISOLATED_SMOKE_OUTPUTS}"
  printf 'overall_exit=%s\n' "${overall}"
} | tee "${AUDIT_DIR}/summary.env"

exit "${overall}"
