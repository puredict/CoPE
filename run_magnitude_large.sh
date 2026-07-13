#!/usr/bin/env bash
set -euo pipefail
cd /home/lijingsu/vla
source .venv/bin/activate
export PYTHONPATH=$HOME/vla/src/openvla:$HOME/vla/src/LIBERO:${PYTHONPATH:-}
export MUJOCO_GL=osmesa
export PYOPENGL_PLATFORM=osmesa
export HF_HOME=$HOME/vla/cache/huggingface
export CUDA_VISIBLE_DEVICES=5
export TOKENIZERS_PARALLELISM=false
python /home/lijingsu/vla/libero_disturbance_eval.py \
  --checkpoint /home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial \
  --task-suite libero_spatial \
  --task-id -1 \
  --trials 1 \
  --max-steps 220 \
  --disturbance-step 70 \
  --target-joint auto \
  --dx 0.15 \
  --dy 0.10 \
  --out-dir /home/lijingsu/vla/disturbance_outputs/magnitude_large
