# Changelog — `cope_fsrpc_交接_v1` → `cope_fsrpc_交接_v2`

## Why v2 exists

The v1 audit found that the frozen online-repair core was neither delivered nor
exercised. Every finding was verified against the v1 code and was correct. v2
integrates the engine for real. **v1 is left untouched** as a separate folder.

## The gap, precisely

| | v1 | v2 |
|---|---|---|
| frozen core in the package | `__init__.py` + `statistics.py` (3 files) | the complete `rekep_repair/` (63 modules) |
| `cope/` imports the core | never | `repair_bridge/` imports 8 of its modules |
| `repair_engine` attribute | stored, never invoked | drives every interruption |
| `slot_to_repair_intent` / `patch_to_repair_goal` | no call sites | called from `enter_repair_pipeline` |
| what an interruption did | recompiled the active-slot list | full capture→synthesis→verify→splice→restore→resume |
| executor | symbolic mock | frozen controllers inside `Synthetic2DEnv` |
| rollout verification | none | 165 candidates verified in the pilot |

## Added

- **`cope/repair_bridge/`** — the bridge, and the only genuinely new logic:
  - `goal_compiler.py` — `ConstraintStateToRepairGoalCompiler`: lifecycle
    transitions → `RepairGoal`, with per-requirement attribution
  - `continuation_capture.py` — κ_t, captured before physical adaptation
  - `engine.py` — `SharedRepairEngine`, the single stack both arms enter
  - `stages.py` — the ten pipeline markers + `assert_complete()`
- **`cope/benchmark/basket_world.py`** — the basket task mapped onto the frozen
  `Synthetic2DEnv` (a "leg" is one object → one basket)
- **`cope/benchmark/physical_executor.py`** — legs driven by the frozen
  controllers and guards
- **`cope/benchmark/physical_episode.py`** — the harness; interruptions are
  delivered *mid-leg* so there is an active stage to interrupt
- **`scripts/cope_pipeline_trace.py`** — the gate: prints the marker sequence and
  exits non-zero if any interruption fails to complete the pipeline
- **`tests/test_repair_integration.py`** — 63 tests, one per audit requirement
- **`docs/REPAIR_INTEGRATION.md`**

## Changed

- `cope/recovery_manager.py` — `enter_repair_pipeline()` added as the single
  shared entry point; `execute()`'s docstring now states plainly that it is the
  *nominal* path and not the repair path.
- `cope/policies/{cope_patch_policy,fsrpc_policy,no_adaptation_policy}.py` — each
  calls `enter_repair_pipeline()` with the identical signature after producing
  its state update. This is the only change to the policies.
- `cope/benchmark/metrics.py` — nine pipeline metrics added.
- `scripts/run_cope_pilot.py` — `--executor {physical,mock}`, default `physical`.
- `cope/benchmark/basket_task.py` — I2/I4's restore now triggers after `g_milk`
  rather than `g_yogurt`. With the physical runner the task stalls once every
  goal is suspended or done, so an update keyed on the last leg could never be
  delivered.

## Corrected modelling (found by the verifier rejecting candidates)

1. **A suspended goal no longer requires clearing an obstruction.** v2's first
   draft compiled `not obstacle_present` for a suspension; the planner emitted
   `WaitUntilClear`, and the rollout verifier hard-rejected every candidate
   because the obstruction never leaves. Setting a goal aside obliges the robot
   to end *resumable*, nothing more.
2. **An unavailable basket is an absent target, not an obstacle.** Same
   symptom, same fix: absence is carried by `blocked_targets`.
3. **`drive_repair` stops at `STAGE_RESUMED`.** It previously drove on and
   finished the whole leg — which once completed a goal the user had just
   cancelled. The resumed stage is nominal work and belongs to the harness.

## Unchanged

- **`rekep_repair/` is byte-identical to the pre-pivot commit** (`git diff
  --stat 60d94e1 -- rekep_repair/` is empty). All 94 of its tests still pass.
- The CoPE semantic layer, its invariants and its audit queries.
- The fairness protocol F1–F5 (F6 added: both arms share one engine instance).
- `cope_fsrpc_交接_v1/` and all four earlier evidence folders.

## Test count

| | v1 | v2 |
|---|---|---|
| pre-existing repair core | 94 | 94 |
| CoPE semantics | 19 | 19 |
| CoPE fairness / benchmark | 53 | 53 |
| repair integration | — | **63** |
| **total** | **166** | **229** |
