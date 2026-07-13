#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

echo "[run_project_env] Using project-isolated LIBERO/OpenVLA environment for this subprocess only." >&2
echo "[run_project_env] LD_LIBRARY_PATH is unset here to avoid the broken system CUDA nvJitLink path." >&2

unset LD_LIBRARY_PATH

if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
  export VIRTUAL_ENV="${PROJECT_ROOT}/.venv"
  export PATH="${VIRTUAL_ENV}/bin:${PATH}"
fi

export PYTHONPATH="${PROJECT_ROOT}/src/openvla:${PROJECT_ROOT}/src/LIBERO:${PYTHONPATH:-}"
export MUJOCO_GL="${MUJOCO_GL:-osmesa}"
export PYOPENGL_PLATFORM="${PYOPENGL_PLATFORM:-osmesa}"
export HF_HOME="${HF_HOME:-${PROJECT_ROOT}/cache/huggingface}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-${PROJECT_ROOT}/cache/transformers}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}"

if [[ "$#" -eq 0 ]]; then
  echo "usage: scripts/run_project_env.sh <command> [args...]" >&2
  exit 2
fi

exec "$@"
