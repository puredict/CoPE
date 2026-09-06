# GPU runbook — CoPE vs FSR-PC basket-sorting benchmark

**Nothing in this document has been executed.** The development machine is
CPU-only; no GPU software was installed, imported or run. Every command below is
for the remote colleague. Do not treat any of it as tested.

Commands that must run on the GPU host are marked **REMOTE GPU SERVER ONLY**.

---

## 0. What is already validated (CPU) and what is not

| | status |
|---|---|
| CoPE semantics, patch operators, invariants | validated, 19 tests |
| Fairness controls incl. byte-identical inputs | validated, 53 tests |
| Metrics, statistics, pilot protocol, ablation | validated end to end on CPU |
| Reliability gate machinery | validated, and proven non-vacuous |
| **Physical reliability of the real task** | **not validated — Stage A must be re-run here** |
| **Any robotics claim** | **not made** |

---

## 1. Environment check — REMOTE GPU SERVER ONLY

```bash
python3 scripts/check_gpu_environment.py --report env_report.json
```

Reused unchanged from the previous handoff. It validates the environment and
does not depend on any CoPE code.

---

## 2. Wire the real executor

The only integration point is the executor. Both policies already emit an
`ExecutorRequest`:

```python
{"active_goals": [{"id", "grounding", "priority", "source",
                   "object", "target", "order", ...}],
 "safety_constraints": [...],
 "horizon_steps": 900,
 "budget": {...}}
```

Implement one class with the same two methods as
`cope/benchmark/mock_executor.py::MockPickPlaceExecutor`:

```python
class RealPickPlaceExecutor:
    def run_one(self, request) -> dict:   # execute ONE pending goal
        ...
    def run(self, request) -> dict:       # execute the request to completion
        ...
```

Return records with the same keys: `placed` (list of
`{goal_id, object, target}`), `failed`, `invalid_actions`, `steps`,
`collision`, `done`.

Two properties the CPU mock has that the real executor **must** keep, or the
paired design breaks:

1. **A physically impossible placement is an `invalid_action`, not a success.**
   Placing into a basket that is not on the table must fail. This is what makes
   a stale goal cost something.
2. **Common random numbers.** A given `(condition, seed)` must produce the same
   physical initial layout for every arm. Set `verify_paired_layout: true` in
   `configs_cope_gpu/machine.yaml` and check it before trusting a paired
   statistic.

No policy code changes. `cope/` never imports the executor; the harness
constructs it.

---

## 3. Stage A — reliability gate — REMOTE GPU SERVER ONLY

```bash
python3 scripts/run_cope_pilot.py --gate-seeds 10 --out results/gpu_stage_a
```

Gate: nominal success **≥ 8/10** (preferred ≥ 9/10), measured with the
`no_adaptation` arm on the uninterrupted task.

**If it fails: change or simplify the task. Do not tune the methods, do not
adjust thresholds, do not proceed to Stage B.** Options in order of preference:
reduce to two objects; enlarge the place tolerance; use a fixed pre-grasp pose;
replace the least reliable object.

Report the number either way.

---

## 4. Stage B — paired comparison — REMOTE GPU SERVER ONLY

Only after Stage A passes.

```bash
python3 scripts/run_cope_pilot.py --seeds 5 --out results/gpu_stage_b
```

60 episodes: 5 seeds × 4 conditions × 3 arms. Expect this to be cheap enough to
run on one GPU. Inspect before scaling:

- Do CoPE and FSR-PC receive identical `adaptation_input_fingerprints`? If not,
  stop — the fairness control is broken on this host.
- Is `invalid_action_count` zero for both primary arms?
- Does `no_adaptation` actually lose I1 and I3?

---

## 5. Stage C — ablation — REMOTE GPU SERVER ONLY

Runs automatically with Stage B; writes `stage_c_ablations.json`. The
`FSR-PC(preserve_ids)` arm separates identity re-minting from regeneration.

---

## 6. Full sweep — REMOTE GPU SERVER ONLY

**Do not start this until Stages A–C look sane.**

```bash
# 8 workers, one seed range each
bash scripts/launch_gpu_workers.sh --script scripts/run_cope_pilot.py \
     --seeds 30 --out results/gpu_sweep
```

450 episodes (30 seeds × 5 conditions × 3 arms).

---

## 7. What to send back

- `results/gpu_stage_a/stage_a_reliability.json`
- `results/gpu_stage_b/stage_b_paired.json`, `stage_c_ablations.json`
- `env_report.json`
- per-episode logs and traces
- video for every failure, plus one nominal success per condition
- the git revision and SHA-256 of the code actually run

## 8. Interpretation rules carried forward

- Do not classify simulator non-determinism as a method failure unless the
  evidence supports it.
- Do not rely only on JSON success flags when video contradicts them.
- Report null results as null; a tie between CoPE and FSR-PC on final success is
  a legitimate outcome and is what the CPU pilot already shows.
- `normalized_edit_distance = 1.0` for FSR-PC is true by definition of full
  regeneration — describe it as a property of the design, not as a finding.

---

# r2 (post-audit revision) — 2026-08-07

## The design flaw this revision fixes

The first LIBERO/MuJoCo pilot coupled the I2/I4 **restore** event to `g_milk`
*completing*. When the milk grasp failed (seeds 1 and 3), the restore event was
never delivered and those episodes silently stopped testing restoration while
still counting as valid I2/I4 episodes — 8 of 30 method episodes.

Interruption delivery is now a **pre-registered elapsed-step schedule**:

    t_u1 = fixed absolute simulator step per (condition, seed)
    t_u2 = t_u1_actual + delta_steps
    t_u3 = t_u1_actual + delta_steps      (I5 only)

Delivery never consults goal completion, grasp success, slot identity, or the
method. Only the episode ending can prevent it, and that is recorded as
`event_not_delivered_due_to_episode_termination`.

Per event the scheduler records `event_id`, `scheduled_step`,
`actual_delivery_step`, `event_delivered`, `delivery_delay`,
`delivery_failure_reason`, `world_state_hash_before`, `world_state_hash_after`.

## Staged protocol

```bash
# Stage A — regression tests (must all pass first)
python3 -m pytest tests/ -q                       # 321 tests

# Stage A' — CPU dry run of every r2 mechanism
python3 scripts/cope_r2_dry_run.py --out results/cope_r2_dryrun

# Stage B — controller reliability gate, PER LEG   REMOTE GPU SERVER ONLY
python3 scripts/run_cope_pilot.py --stage controller_gate \
  --backend libero_mujoco --backend-config configs_gpu/task_assets.yaml \
  --gate-seeds 10 --out "$OUT"
#   Reports per-object grasp success. If one object is systematically weak,
#   fix the asset pose / grasp waypoint / controller BEFORE comparing methods.
#   Do not use method results to compensate for a poor nominal controller.

# Stage C — fixed-scheduler regression pilot       REMOTE GPU SERVER ONLY
python3 scripts/run_cope_pilot.py --stage regression_pilot \
  --backend libero_mujoco --backend-config configs_gpu/task_assets.yaml \
  --conditions I1,I2,I3,I4 --methods CoPE,FSR-PC,no_adaptation \
  --seeds 5 --out "$OUT"

# Stage D — diagnostic pilot                       REMOTE GPU SERVER ONLY
python3 scripts/run_cope_pilot.py --stage diagnostic_pilot \
  --backend libero_mujoco --backend-config configs_gpu/task_assets.yaml \
  --conditions I3,I4,I5 \
  --methods CoPE,FSR-PC,FSR-PC_stable_ids,FSR-PC_provenance \
  --seeds 5 --out "$OUT"

# Stage D' — verifier mechanism                    REMOTE GPU SERVER ONLY
python3 scripts/run_cope_pilot.py --stage diagnostic_pilot \
  --backend libero_mujoco --backend-config configs_gpu/task_assets.yaml \
  --methods CoPE_full,CoPE_no_rollout_verification \
  --seeds 5 --out "$OUT"
```

**Do not expand to 20 seeds until the five-seed schemas and videos are audited.**

## Stage C acceptance criteria

- every non-terminated I2/I4/I5 episode receives its restore event;
- controller failures are separated from adaptation failures;
- every required pipeline stage is logged;
- task-success labels agree with final geometry;
- no silent episode exclusions.

## Per-episode artifacts (nine)

`result.json`, `events.jsonl`, **`interruptions.jsonl`**, `adaptation_trace.jsonl`,
`repair_trace.jsonl`, **`candidate_rollouts.jsonl`**, `state_snapshots.json`,
`simulator.log`, `video.mp4`.

## Separate denominators

`attempted_episodes`, `valid_episodes`, `all_events_delivered_episodes`,
`adaptation_valid_episodes`, `controller_valid_episodes`,
`final_task_successes`.

## What r2 does NOT establish

r2 changes the experimental design only. The first execution found **no
behavioural difference** between CoPE and FSR-PC (16/20 vs 16/20, p = 1.0), and
r2 has not been executed on the simulator. Do not claim a CoPE behavioural
advantage unless the r2 physical experiments support it.
