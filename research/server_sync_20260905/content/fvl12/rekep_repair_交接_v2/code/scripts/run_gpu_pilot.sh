#!/usr/bin/env bash
# v2 20-episode single-GPU pilot -- REMOTE GPU SERVER ONLY (except DRY_RUN=1).
#
# 2 methods x 2 severities x 5 paired seeds = 20 episodes, ONE GPU.
# Debug episodes run first; the pilot refuses to continue unless they show
# genuine candidate verification and a nontrivial restore check.
set -euo pipefail
cd "$(dirname "$0")/.."

DRY="${DRY_RUN:-0}"
OUT_ROOT="${OUT_ROOT:-runs/pilot_v2_$(date +%Y%m%d_%H%M%S)}"
REKEP_ROOT="${REKEP_ROOT:-../ReKep}"
SEEDS="${SEEDS:-0 1 2 3 4}"
SEVERITIES="${SEVERITIES:-0.075 0.150}"
METHODS="${METHODS:-nominal_with_disturbance online_repair}"
FLAG=""; [[ "$DRY" == "1" ]] && FLAG="--dry-run"
[[ "$DRY" != "1" && "$(uname)" == "Darwin" ]] && {
  echo "REFUSING: REMOTE GPU SERVER ONLY. Use DRY_RUN=1." >&2; exit 2; }

mkdir -p "$OUT_ROOT"
echo "=== v2 pilot -> $OUT_ROOT (dry_run=$DRY) ==="

run_one () {  # method seed severity subdir
  local m="$1" s="$2" sev="$3" d="$4"
  mkdir -p "$d"
  python scripts/run_gpu_pilot_episode.py --method "$m" --seed "$s" \
      --severity "$sev" --rekep-root "$REKEP_ROOT" --out "$d" $FLAG \
      > "$d/stdout.log" 2> "$d/stderr.log" \
    && echo "  PASS $m seed=$s sev=$sev" \
    || { echo "  FAIL $m seed=$s sev=$sev (see $d/stderr.log)"; \
         printf '%s\t%s\t%s\tFAIL\n' "$m" "$s" "$sev" >> "$OUT_ROOT/FAILURES.tsv"; }
}

# ---- debug episodes first -------------------------------------------------
echo "--- debug episodes (one per method) ---"
run_one nominal_with_disturbance 0 0.150 "$OUT_ROOT/debug/nominal"
run_one online_repair            0 0.150 "$OUT_ROOT/debug/repair"

DBG="$OUT_ROOT/debug/repair/events.jsonl"
if [[ -f "$DBG" ]]; then
  n_roll=$(grep -c '"event": "ROLLOUT_RESULT"' "$DBG" || true)
  n_rej=$(grep -c '"event": "CANDIDATE_REJECTED"' "$DBG" || true)
  n_rest=$(grep -c '"event": "RESTORE_CHECK"' "$DBG" || true)
  n_succ=$(grep -c '"event": "TASK_SUCCESS_EVALUATION"' "$DBG" || true)
  echo "  gate: rollouts=$n_roll rejected=$n_rej restore_checks=$n_rest success_evals=$n_succ"
  if (( n_roll < 2 )) || (( n_rest < 1 )) || (( n_succ < 1 )); then
    echo "REFUSING to run the pilot: the debug episode did not show genuine" >&2
    echo "candidate verification / restore check / success evaluation." >&2
    exit 3
  fi
else
  echo "REFUSING: no debug event log produced." >&2; exit 3
fi

# ---- the 20-episode grid ---------------------------------------------------
echo "--- pilot grid (20 episodes) ---"
for sev in $SEVERITIES; do
  for s in $SEEDS; do
    for m in $METHODS; do
      run_one "$m" "$s" "$sev" "$OUT_ROOT/sev_${sev}/seed_${s}/${m}"
    done
  done
done

echo "=== done. failures: ==="
cat "$OUT_ROOT/FAILURES.tsv" 2>/dev/null || echo "  (none)"
echo "aggregate with: python scripts/aggregate_pilot.py --root $OUT_ROOT"
