#!/usr/bin/env bash
set -euo pipefail

cd /home/lijingsu/vla

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export PYTHONPATH="$HOME/vla/src/openvla:$HOME/vla/src/LIBERO:${PYTHONPATH:-}"
export HF_HOME="${HF_HOME:-$HOME/vla/cache/huggingface}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export TOKENIZERS_PARALLELISM=false
export MUJOCO_GL="${MUJOCO_GL:-egl}"
export PYOPENGL_PLATFORM="${PYOPENGL_PLATFORM:-egl}"

PORT="${PORT:-7860}"

exec python /home/lijingsu/vla/libero_dashboard.py \
  --host 127.0.0.1 \
  --port "$PORT" \
  --default-checkpoint /home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial \
  --default-task-suite libero_spatial \
  --default-out-dir /home/lijingsu/vla/dashboard_outputs
