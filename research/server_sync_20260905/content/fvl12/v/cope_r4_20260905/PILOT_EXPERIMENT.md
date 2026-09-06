# Pilot experiment — protocol and CPU results

## 1. Design

| | |
|---|---|
| task | multi-object basket sorting (3 objects, 3 baskets) |
| arms | **CoPE**, **FSR-PC** (internally defined baseline), `no_adaptation` (control) |
| conditions | nominal, I1 cancel+redirect, I2 temporary unavailability, I3 repeated interruption, I4 changed-world restoration |
| pairing | by `(task, condition, seed)` — the method is excluded from the key |
| CPU pilot size | 10 gate episodes + 60 Stage-B episodes + 60 Stage-C episodes |
| planned GPU pilot | same, then 450-episode sweep only if the earlier stages hold |

Run:

```bash
python3 scripts/run_cope_pilot.py --seeds 5 --out results/cope_pilot
```

## 2. Stage A — reliability gate

**10/10 nominal success → PASS** (required ≥ 8/10, preferred ≥ 9/10).

Measured with the `no_adaptation` arm on the uninterrupted task, so it describes
the task and the executor rather than any adaptation method.

Non-vacuity check: with a degraded executor (`p_success=0.5`) the gate returns
FAIL. The gate can therefore fail, and passing it means something.

**This is a CPU number from a scripted mock.** It validates that the gate
machinery works. It says nothing about the physical reliability of the real
task, which must be re-measured on the GPU host before any robotics claim.

## 3. Stage B — paired comparison (5 seeds × 4 conditions)

Binary outcomes, exact McNemar:

| metric | CoPE | FSR-PC | discordant | p |
|---|---|---|---|---|
| revised task success | 20/20 | 20/20 | 0/0 | 1.000 |
| completed progress preserved | 20/20 | 20/20 | 0/0 | 1.000 |
| remaining goal correct | 20/20 | 20/20 | 0/0 | 1.000 |
| **identity preserved** | **20/20** | **0/20** | 20/0 | **<0.001** |
| lifecycle transitions legal | 20/20 | 20/20 | 0/0 | 1.000 |
| lineage correct | 20/20 | 20/20 | 0/0 | 1.000 |
| history monotonic | 20/20 | 20/20 | 0/0 | 1.000 |

Continuous outcomes, paired bootstrap 95% CI on `CoPE − FSR-PC`:

| metric | CoPE | FSR-PC | 95% CI | excludes 0 |
|---|---|---|---|---|
| normalized edit distance | 0.507 | 1.000 | [−0.541, −0.442] | ✓ |
| slots touched per event | 3.00 | 5.13 | [−2.500, −1.725] | ✓ |
| **audit coverage** | **1.000** | **0.458** | [+0.483, +0.600] | ✓ |
| completion steps | 165.0 | 165.0 | [0, 0] | ✗ |
| invalid actions | 0.000 | 0.000 | [0, 0] | ✗ |

Per-condition final success:

| condition | CoPE | FSR-PC | no_adaptation |
|---|---|---|---|
| I1 | 5/5 | 5/5 | **0/5** |
| I2 | 5/5 | 5/5 | 5/5 (with 1 invalid action, +60 steps per episode) |
| I3 | 5/5 | 5/5 | **0/5** |
| I4 | 5/5 | 5/5 | 5/5 (with 1 invalid action, +60 steps per episode) |

## 4. Stage C — ablation

| arm | success | identity preserved | mean NED | mean audit coverage |
|---|---|---|---|---|
| CoPE | 20/20 | 20/20 | 0.507 | 1.000 |
| FSR-PC | 20/20 | 0/20 | 1.000 | 0.458 |
| FSR-PC(preserve_ids) | 20/20 | **20/20** | 1.000 | 0.458 |

**Mechanism identified.** Re-using identifiers recovers the identity metric and
changes nothing else. The locality and audit differences come from *local typed
editing*, not from identifier hygiene. This is exactly the ablation a reviewer
would demand, and it is run rather than argued.

## 5. Honest interpretation

What the CPU pilot supports:

- The two arms are **tied on every behavioural outcome**. CoPE does not beat
  FSR-PC on final task success, and this report does not claim it does.
- The measurable differences are structural: identity survival, edit locality,
  and which audit questions the record can answer.
- The audit gap is the substantive one. FSR-PC answers Q1 (what was cancelled)
  and Q2 (what completed work was preserved) — both recoverable from a state
  snapshot — and cannot answer Q3 (why suspended), Q4 (what allowed
  restoration) or Q5 (what replaced the old target), because a snapshot carries
  no reasons, conditions or replacement links. The scoring gives every query a
  regeneration-evidence path precisely so this is not circular.

What it does **not** support:

- `normalized_edit_distance = 1.000` for FSR-PC is true by *definition* of full
  regeneration. It describes the two designs; it is not an experimental finding
  and must not be presented as one.
- No physical, robotics, or wall-clock-cost claim. The executor is a CPU mock.
- No language-model claim. Both arms use deterministic planners; `token_usage`
  is `None` by design.
- With 20 paired episodes per arm, only large effects are detectable. The
  behavioural ties are "no evidence of a difference", not "evidence of no
  difference".

## 6. What would change the conclusion

The CPU harness cannot distinguish the arms on final success because the mock
executor never punishes a slightly-wrong-but-recoverable state. On the GPU host,
watch for:

- longer horizons where regenerated state drifts across many interruptions;
- conditions with more than two interruptions, where re-minted identity makes it
  harder to tell what has already been attempted;
- cases where the executor cannot cheaply retry, so a stale or duplicated goal
  becomes an unrecoverable failure.

If none of those separate the arms either, the honest paper claim is about
**representation, auditability and edit locality**, not about task success —
and the results section should say so.

## 7. Artifacts

```
results/cope_pilot/stage_a_reliability.json
results/cope_pilot/stage_b_paired.json      # 60 episodes, full per-episode records
results/cope_pilot/stage_c_ablations.json
results/cope_pilot/dry_run_{nominal,I1,I2,I3,I4}.txt
```

Each episode record carries its `pairing_key`, both fingerprint lists, the
expected outcome, and all metrics — enough to re-derive every number above
without re-running anything.

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
