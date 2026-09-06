#!/usr/bin/env bash
# One-GPU Milestone-1 runner -- REMOTE GPU SERVER ONLY.
# Runs nominal -> wrapped -> repair and reports the parity check.
# Use DRY_RUN=1 to validate wiring locally with NO GPU imports.
set -euo pipefail
cd "$(dirname "$0")/../code"
REKEP_ROOT="${REKEP_ROOT:-../ReKep}"
TASK="${TASK:-upright_transport}"
STEPS="${STEPS:-400}"
DRY="${DRY_RUN:-0}"
FLAG=""; [[ "$DRY" == "1" ]] && FLAG="--dry-run"
[[ "$DRY" != "1" && "$(uname)" == "Darwin" ]] && { echo "REFUSING: REMOTE GPU SERVER ONLY. Use DRY_RUN=1." >&2; exit 2; }

for MODE in nominal wrapped repair; do
  echo "=== ${MODE} ==="
  python scripts/run_rekep_baseline.py --mode "$MODE" --task "$TASK" \
    --steps "$STEPS" --rekep-root "$REKEP_ROOT" $FLAG \
    --out "runs/milestone1/${MODE}"
done
echo
echo "PARITY CHECK: compare stage sequences in"
echo "  runs/milestone1/nominal/trace.json"
echo "  runs/milestone1/wrapped/trace.json"
echo "They must be IDENTICAL. If not, stop (risk R7)."
echo "On full approval:  touch runs/milestone1/GATE_PASSED"
