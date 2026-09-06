#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 ABSOLUTE_OUTPUT_DIRECTORY" >&2
  exit 64
fi

RUN_OUTPUT="$1"
if [[ "$RUN_OUTPUT" != /* ]]; then
  echo "output directory must be absolute" >&2
  exit 64
fi
if [[ -e "$RUN_OUTPUT" || -e "${RUN_OUTPUT}_gate" ]]; then
  echo "refusing to overwrite an existing output path" >&2
  exit 73
fi

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
export MUJOCO_GL=osmesa
export PYTHONPATH="$PROJECT_DIR/code${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/preflight_r3.py --server --live-call --check-libero
python3 scripts/run_r3_lineage.py \
  --stage gate \
  --backend libero_mujoco \
  --out "${RUN_OUTPUT}_gate"
python3 scripts/run_r3_lineage.py \
  --stage main \
  --client openai \
  --backend libero_mujoco \
  --out "$RUN_OUTPUT"
python3 scripts/validate_r3_results.py "$RUN_OUTPUT" --expected 120

echo "completed fixed-model r3 experiment: $RUN_OUTPUT"

