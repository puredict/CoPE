#!/usr/bin/env bash
# Regenerate every frozen CPU result artifact. CPU-only; takes ~25-40 min.
# Usage: bash scripts/reproduce_cpu_results.sh [--quick]
set -euo pipefail
cd "$(dirname "$0")/../code"
OUT="../results_cpu"
QUICK="${1:-}"
mkdir -p "$OUT"
if [[ "$QUICK" == "--quick" ]]; then
  BENCH="--quick"; ABL="--seeds 6"; MM="--seeds 6"; ATTR="--seeds 4"
else
  BENCH="";        ABL="--seeds 20"; MM="--seeds 20"; ATTR="--seeds 10"
fi
echo "[1/6] theorem sanity";     python scripts/validate_theorem1.py          > "$OUT/theorem1.txt"
echo "[2/6] main benchmark";     python scripts/run_benchmark.py $BENCH       > "$OUT/benchmark_main.txt"
echo "[3/6] ablations";          python scripts/run_ablations.py $ABL         > "$OUT/ablations.txt"
echo "[4/6] coverage/storage";   python scripts/offline_regimes.py            > "$OUT/coverage_storage.txt"
echo "[5/6] mismatch aggregate"; python scripts/run_mismatch.py $MM           > "$OUT/mismatch_aggregate.txt"
echo "[6/6] mismatch attribution"; python scripts/run_mismatch_attribution.py $ATTR \
      --json "$OUT/mismatch_attribution.json"                                 > "$OUT/mismatch_attribution.txt"
echo "done -> $OUT"
