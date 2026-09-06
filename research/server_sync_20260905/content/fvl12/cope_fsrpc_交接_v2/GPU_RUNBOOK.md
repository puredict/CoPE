# Real simulator runbook — CoPE versus FSR-PC

This runbook is for the audited server and `libero_mujoco` backend. The
simulator and OSMesa renderer run on CPU; the host has GPUs, but this mechanism
experiment loads no learned checkpoint and performs no CUDA inference.

## 1. Exact environment

```bash
ssh -p 26575 lijingsu@10.176.53.120
cd /home/lijingsu/cope_fsrpc_交接_v2

# Required before any possible GPU use; never select a busy GPU.
nvidia-smi

RUN_ENV=/home/lijingsu/vla/scripts/run_project_env.sh
PY=/home/lijingsu/vla/.venv/bin/python
```

The wrapper unsets the server's broken CUDA library path, adds the installed
LIBERO/OpenVLA source roots, and selects OSMesa offscreen rendering. Do not use
sudo, Docker, or create another account/environment.

## 2. Package and CPU gate

```bash
shasum -a 256 -c SHA256SUMS.txt
$RUN_ENV bash -lc "cd /home/lijingsu/cope_fsrpc_交接_v2 && \
  python -m pytest tests/ -q"
$RUN_ENV bash -lc "cd /home/lijingsu/cope_fsrpc_交接_v2 && \
  python scripts/cope_pipeline_trace.py --all --seed 0"
```

Expected in the updated package: `138 passed`; I1–I4 must emit the complete
ten-marker path.

## 3. Stage A — real simulator preflight

Use a new output directory; scripts refuse to overwrite one.

```bash
$RUN_ENV $PY scripts/run_backend_preflight.py \
  --backend libero_mujoco \
  --backend-config configs_gpu/task_assets.yaml \
  --out /home/lijingsu/cope_outputs/preflight_YYYYMMDD_vN
```

Do not continue unless `preflight.json` says `preflight_passed: true`. Inspect:

- native checkpoint change/restore hashes;
- candidate 0 collision rejection and `candidate_0.mp4`;
- candidate 1 invalid-handoff rejection and `candidate_1.mp4`;
- candidate 2 acceptance and `candidate_2.mp4`;
- real pick/place predicate and `video.mp4`.

## 4. Stage B — 10-seed nominal gate

Run detached with a server-local log so an SSH disconnect cannot enter the
experiment control path:

```bash
OUT=/home/lijingsu/cope_outputs/nominal_gate_YYYYMMDD_vN
nohup $RUN_ENV $PY scripts/run_cope_pilot.py \
  --backend libero_mujoco \
  --backend-config configs_gpu/task_assets.yaml \
  --stage gate --gate-seeds 10 --out "$OUT" \
  > "${OUT}.log" 2>&1 < /dev/null &
```

Gate requirements:

- exactly 10 attempted and 10 valid episodes;
- at least 8/10 revised-task successes;
- every result contains per-object stability and `task_time` metrics;
- every episode has `result.json`, `events.jsonl`,
  `adaptation_trace.jsonl`, `repair_trace.jsonl`,
  `state_snapshots.json`, `simulator.log`, and `video.mp4`.

If the gate fails, stop. Do not tune CoPE/FSR-PC and do not start the pilot.

## 5. Stage C — manual nominal and online-repair debug

The single-episode runner is useful for a fresh review case:

```bash
$RUN_ENV $PY scripts/run_single_backend_episode.py \
  --backend libero_mujoco \
  --backend-config configs_gpu/task_assets.yaml \
  --out /home/lijingsu/cope_outputs/debug_I1_cope_seed0_vN \
  --method CoPE --condition I1 --seed 0
```

Before the pilot, manually inspect the nominal and I1 videos plus every JSONL
trace. The online repair must show candidate rollouts from identical
checkpoint hashes, at least one accepted candidate, graph splice, nontrivial
restore validation, and stage resume. A `SAFE_FALLBACK` debug does not pass.

Then run and inspect the full same-seed debug matrix before the pilot:

```text
CoPE   x I1 I2 I3 I4 x seed 0
FSR-PC x I1 I2 I3 I4 x seed 0
```

For every condition, the pair must have the same initial simulator-state hash,
event ordinal/step and physical world edit. CoPE must record local typed patch
operations; FSR-PC must record full regeneration; both must enter the same
candidate verifier, restore gate, and resume stack. Final JSON predicates must
agree with the video.

## 6. Stage D — fixed 60-episode pilot

Only after the gate and manual debug pass:

```bash
GATE=/home/lijingsu/cope_outputs/nominal_gate_YYYYMMDD_vN/stage_a_nominal_gate.json
OUT=/home/lijingsu/cope_outputs/paired_pilot_YYYYMMDD_vN
nohup $RUN_ENV $PY scripts/run_cope_pilot.py \
  --backend libero_mujoco \
  --backend-config configs_gpu/task_assets.yaml \
  --stage pilot --gate-report "$GATE" \
  --seeds 5 --out "$OUT" \
  > "${OUT}.log" 2>&1 < /dev/null &
```

This is exactly 5 seeds × 4 conditions × 3 methods = 60 episodes. Do not add
ablations, extra seeds, or a full sweep in this handoff.

The real output root is stage-specific and every leaf follows:

```text
<method>/<condition>/seed_<seed>/
```

## 7. Interpretation

- Report attempted and valid denominators separately.
- Task success comes from revised object–region predicates, cancellation and
  stale-goal checks, not program termination.
- FSR-PC is an internally defined strong baseline, not published prior art.
- Oracle geometry and OSMesa make these mechanism results; do not label them
  learned-policy, GPU-inference, physical-robot, or calibrated-safety results.
- Preserve all failed/invalid runs and old ReKep evidence. Never overwrite an
  experiment directory.
