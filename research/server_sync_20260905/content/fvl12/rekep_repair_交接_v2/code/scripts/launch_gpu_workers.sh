#!/usr/bin/env bash
# =============================================================================
# 8-GPU experiment launcher -- REMOTE GPU SERVER ONLY
#
# STATUS: locally syntax-checked (bash -n) ONLY. NOT EXECUTED.
#         Requires remote GPU verification.
#
# One OmniGibson simulator worker per GPU. Each worker gets fully ISOLATED
# config / seeds / traces / videos / episode JSON / error logs, so a crash in
# one worker cannot corrupt another's output.
#
# DO NOT run large sweeps until BOTH of these are reproducible on ONE GPU:
#   * one nominal ReKep episode
#   * one online-repaired ReKep episode
# The launcher refuses to start a sweep unless the gate file exists (see below).
# =============================================================================
set -euo pipefail

NUM_GPUS="${NUM_GPUS:-8}"
TASK="${TASK:-upright_transport}"
MODE="${MODE:-repair}"
SEEDS_PER_GPU="${SEEDS_PER_GPU:-25}"
STEPS="${STEPS:-400}"
RUN_ROOT="${RUN_ROOT:-runs/sweep_$(date +%Y%m%d_%H%M%S)}"
REKEP_ROOT="${REKEP_ROOT:-../ReKep}"
GATE_FILE="${GATE_FILE:-runs/milestone1/GATE_PASSED}"
DRY_RUN="${DRY_RUN:-0}"

echo "=== ReKep-R sweep launcher ==="
echo "  gpus=${NUM_GPUS} task=${TASK} mode=${MODE} seeds/gpu=${SEEDS_PER_GPU}"
echo "  run_root=${RUN_ROOT}"

# --- gate: milestone 1 must have passed -------------------------------------
if [[ ! -f "${GATE_FILE}" ]]; then
  echo "REFUSING: milestone-1 gate file '${GATE_FILE}' not found." >&2
  echo "Run scripts/run_rekep_baseline.py in --mode nominal AND --mode repair," >&2
  echo "verify both are reproducible on a single GPU, then create the gate file." >&2
  exit 3
fi

# --- preflight ---------------------------------------------------------------
if [[ "${DRY_RUN}" != "1" ]]; then
  command -v nvidia-smi >/dev/null || { echo "nvidia-smi missing" >&2; exit 4; }
  VISIBLE=$(nvidia-smi --query-gpu=index --format=csv,noheader | wc -l)
  if (( VISIBLE < NUM_GPUS )); then
    echo "REFUSING: only ${VISIBLE} GPUs visible, need ${NUM_GPUS}" >&2
    exit 5
  fi
  python scripts/check_gpu_environment.py || {
    echo "REFUSING: environment check failed" >&2; exit 6; }
fi

mkdir -p "${RUN_ROOT}"
cp -f requirements_gpu.txt "${RUN_ROOT}/" 2>/dev/null || true

PIDS=()
for (( GPU=0; GPU<NUM_GPUS; GPU++ )); do
  WORKER_DIR="${RUN_ROOT}/gpu${GPU}"
  mkdir -p "${WORKER_DIR}"/{traces,videos,logs,configs}

  SEED_START=$(( GPU * SEEDS_PER_GPU ))
  SEED_END=$(( SEED_START + SEEDS_PER_GPU - 1 ))

  # isolated, self-describing worker config
  cat > "${WORKER_DIR}/configs/worker.json" <<EOF
{
  "gpu": ${GPU},
  "task": "${TASK}",
  "mode": "${MODE}",
  "seed_start": ${SEED_START},
  "seed_end": ${SEED_END},
  "steps": ${STEPS},
  "rekep_root": "${REKEP_ROOT}",
  "run_root": "${RUN_ROOT}"
}
EOF

  echo "  -> gpu${GPU}: seeds ${SEED_START}..${SEED_END}"
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "     [DRY_RUN] would launch worker on CUDA_VISIBLE_DEVICES=${GPU}"
    continue
  fi

  (
    export CUDA_VISIBLE_DEVICES="${GPU}"
    # one simulator per process; keep Omniverse caches per-worker to avoid
    # cross-worker lock contention
    export OMNI_KIT_CACHE_DIR="${WORKER_DIR}/.omni_cache"
    export MPLBACKEND=Agg
    for (( SEED=SEED_START; SEED<=SEED_END; SEED++ )); do
      python scripts/run_rekep_baseline.py \
        --mode "${MODE}" \
        --task "${TASK}" \
        --seed "${SEED}" \
        --steps "${STEPS}" \
        --rekep-root "${REKEP_ROOT}" \
        --out "${WORKER_DIR}/traces/seed_${SEED}" \
        >  "${WORKER_DIR}/logs/seed_${SEED}.out" \
        2> "${WORKER_DIR}/logs/seed_${SEED}.err" \
        || echo "seed ${SEED} FAILED (see logs/seed_${SEED}.err)" \
             >> "${WORKER_DIR}/logs/FAILURES"
    done
  ) &
  PIDS+=($!)
done

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "DRY_RUN complete: configs written, nothing launched."
  exit 0
fi

echo "launched ${#PIDS[@]} workers; waiting..."
FAIL=0
for pid in "${PIDS[@]}"; do wait "${pid}" || FAIL=1; done

echo "=== done. failures across workers: ==="
cat "${RUN_ROOT}"/gpu*/logs/FAILURES 2>/dev/null || echo "  (none)"
exit "${FAIL}"
