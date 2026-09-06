#!/usr/bin/env bash
# Reproduce every CPU result in this package. No GPU software involved.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pytest tests/ -q
# the pipeline gate: exits non-zero unless every interruption drives
# the complete frozen repair pipeline
python3 scripts/cope_pipeline_trace.py --all --seed 0 \
  --out results_cpu_rerun/pipeline_trace_all.txt
python3 scripts/run_cope_pilot.py --seeds 5 --out results_cpu_rerun
for c in nominal I1 I2 I3 I4; do
  python3 scripts/cope_dry_run.py --condition $c --seed 0 \
    --out results_cpu_rerun/dry_run_$c.txt > /dev/null
done
echo "OK -- compare results_cpu_rerun/ against results_cpu/"
