# Validation report — `cope_fsrpc_交接_v2`, revision r2

All checks run on this CPU-only machine on 2026-08-07. Commands and their
actual output are recorded, not paraphrased.

---

## 1. Test suite

```
python3 -m pytest -q            (repository)
321 passed in 1.89s

python3 -m pytest tests/ -q     (this package, standalone)
227 passed in 1.52s
```

| group | count | status |
|---|---|---|
| frozen repair core (repo only) | 94 | pass, unchanged |
| `test_cope_semantics.py` | 19 | pass |
| `test_cope_fairness.py` | 73 | pass |
| `test_repair_integration.py` | 63 | pass |
| **`test_postaudit_fixes.py` (new in r2)** | **72** | **pass** |
| **total (repo)** | **321** | **pass** |

## 2. The core method was not redesigned

`git diff --stat 60d94e1 -- rekep_repair/` → empty. ConstraintState,
ConstraintSlot, the typed patch operators, CoPEPatchPolicy, FSRPCPolicy,
continuation capture, RepairManager, candidate synthesis, the legality and
feasibility filters, RolloutVerifier, the TaskProgram splice and the
restore/resume semantics are unchanged.

Three deliberate, documented exceptions, none of which alters an operator:

1. `suspended → overridden` added to the lifecycle table (I5 requires a
   suspended goal to accept a temporary stand-in). `EXPIRED` stays terminal.
2. `Override` on a suspended slot now preserves the suspension's priority
   snapshot and restore predicate.
3. `SharedRepairEngine.disable_rollout_verification`, used only by the ablation.

## 3. Interruption delivery (the v2 defect)

```
python3 scripts/cope_r2_dry_run.py --out results/cope_r2_dryrun

  episodes            : 75
  events scheduled    : 150
  events delivered    : 150
  short-delivery cases: 0
```

Regression test, with **every placement forced to fail** (`p_disturbance=1.0`),
so no goal ever completes:

```
  I2: placements=0 events delivered=2/2  layer=task
  I4: placements=0 events delivered=2/2  layer=task
  I5: placements=0 events delivered=3/3  layer=task
```

Under the v2 rule none of those restore events could have been delivered.

Undelivered events are recorded, never omitted
(`test_undelivered_events_are_recorded_never_omitted`), with reason
`event_not_delivered_due_to_episode_termination`.

## 4. Failure-layer separation

`test_a_correct_state_update_with_a_failed_grasp_is_a_controller_failure`
asserts the v2 mislabelling cannot recur: a valid state update plus
`grasp_not_acquired` classifies as **controller**, with
`adaptation_failure=False` and `state_update_valid=True`.

Hierarchy verified deterministic: infrastructure outranks adaptation, which
outranks controller (`test_the_layer_hierarchy_is_deterministic`).

## 5. Audit decomposition — a finding that weakens a previous claim

| condition | CoPE | FSR-PC | +stable_ids | +provenance |
|---|---|---|---|---|
| I1 | 1.000 | 0.667 | 0.667 | 1.000 |
| I2 | 1.000 | 0.333 | 0.333 | 1.000 |
| I3 | 1.000 | 0.500 | 0.500 | 1.000 |
| I4 | 1.000 | 0.333 | 0.333 | 1.000 |
| I5 | 1.000 | 0.200 | 0.200 | 0.800 |

**Stable IDs do not close the audit gap; explicit provenance almost entirely
does.** CoPE's audit advantage is attributable to *recording provenance*, not
to persistent local editing — except under I5, where a residual gap remains.

## 6. I5 is diagnostic, not rigged

All four adaptation arms succeed on I5
(`test_i5_is_not_rigged_for_cope`). Two fairness gaps were found while building
it and were fixed **in the baseline's favour**: FSR-PC had not been told the
withdrawal semantics, and it did not record the pre-detour grounding.

CoPE's lifecycle trace:

```
patch-I5-u1-1: ['Suspend(g_butter)']
patch-I5-u2-2: ['Override(g_butter)']
patch-I5-u3-3: ['Inherit(g_milk)', 'Expire(g_butter@basket_C)',
                'Revalidate(g_butter)', 'Restore(g_butter)']
```

Per-episode validity checks (all arms): exactly one active butter goal, no stale
target execution, no duplicate execution, correct lineage, the withdrawn detour
never executed, progress preserved.

## 7. Verifier discrimination

```
CoPE_full                    : 4 candidates, 4 rejected (collision), safe fallback
CoPE_no_rollout_verification : 4 candidates, 0 rejected, candidate accepted
verifier changed the decision: True
```

**Honest limitation:** on the CPU synthetic world the synthesised candidates
share an operator multiset, so the verifier rejects them uniformly rather than
2-of-3. The reject/reject/accept split must be established on LIBERO; the v2
preflight already recorded exactly it.

## 8. Fairness

- `test_paired_arms_get_the_identical_schedule` — all five arms produce the same
  `schedule_fingerprint` and the same scheduled steps, for every condition.
- `test_paired_arms_receive_identical_adaptation_inputs` — identical at every
  event, all five conditions.
- `test_paired_arms_compile_identical_repair_goals` — identical compiled repair
  goals. This test **found a real defect**: CoPE and FSR-PC compiled different
  goals for the same I5 semantic change; the compiler now compares the canonical
  live target instead.
- `assert_no_patch_application` — no FSR-PC variant applies a CoPE patch.

## 9. Server-path wiring

`backend_episode.run_backend_episode` can only be executed end to end on the
LIBERO host. Its wiring is verified here by seven static tests: the scheduler is
used, the v2 trigger is gone, delivery is attempted on the pick-failure branch,
undelivered events are drained and recorded, both new artifacts are written,
separate denominators are reported, and the ablation also suppresses the backend
verifier.

**This is a wiring check, not an execution check.** The r2 LIBERO run is
outstanding.

## 10. Immutable evidence untouched

```
cope_fsrpc_v2_execution : 837/837 checksums OK, nothing written
cope_fsrpc_v2_analysis  : unmodified
```

The server-side backend code (`cope/backends/`, `cope/benchmark/backend_episode.py`,
five scripts) was **copied out** of the execution folder read-only and is now
maintained in the working handoff.

## 11. Known limitations

1. No new physical result. r2 fixes experimental design only.
2. The CPU world cannot reproduce the 2-of-3 verifier split.
3. The first execution found **no behavioural difference** between CoPE and
   FSR-PC. Nothing in r2 changes that, and no such advantage is claimed.
4. The CPU schedule profile is a different step scale from LIBERO's; both are
   pre-registered, but only the LIBERO profile matters for the published run.
5. 5 seeds per condition remains under-powered; do not expand to 20 until the
   five-seed schemas and videos are audited.
