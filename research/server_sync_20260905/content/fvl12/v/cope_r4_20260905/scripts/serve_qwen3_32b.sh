#!/usr/bin/env bash
set -euo pipefail

MODEL_PATH="${COPE_MODEL_PATH:-Qwen/Qwen3-32B}"
PORT="${COPE_LLM_PORT:-8000}"
TP_SIZE="${COPE_TENSOR_PARALLEL_SIZE:-8}"

exec vllm serve "$MODEL_PATH" \
  --served-model-name Qwen/Qwen3-32B \
  --host 127.0.0.1 \
  --port "$PORT" \
  --tensor-parallel-size "$TP_SIZE" \
  --dtype auto \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.88 \
  --enable-prefix-caching

