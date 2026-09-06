# Repair-engine integration — response to the v1 audit

## 1. What the audit found, and what was actually true

Every finding was correct. Verified against the v1 code before any change:

| finding | verification |
|---|---|
| `code/rekep_repair/` held only `__init__.py` + statistics | `find` on the shipped package: 3 files |
| no `TaskProgram`, `Continuation`, verifier, splice delivered | same |
| `RecoveryManager.repair_engine` stored, never invoked | `grep -rn repair_engine cope/` → 4 hits, all assignments |
| `slot_to_repair_intent` / `patch_to_repair_goal` unused | `grep` → definitions only, zero call sites |
| `execute()` calls `executor.run(request)` directly | confirmed |
| `cope/` never imported the repair core at all | `grep -rn rekep_repair cope/` → one docstring mention |

So v1 tested `event → patch/regeneration → active-slot compilation → mock
executor`. The "two-layer design" in the v1 docs described an interface that
existed and was never called. The docs asserted an integration that the code did
not perform, and no test caught it — that is the part worth fixing structurally,
not just repairing once.

## 2. What the pipeline does now

```
C_t      = (S_t, G_t, H_t)                       persistent constraint state
P_t      = epsilon(e_t, C_t, x_t)                CoPE patch | FSR-PC regeneration
C_t+     = Apply(C_t, P_t)                       validated, invariant-checked
kappa_t  = Capture(TaskProgram, active_stage, x_t)   BEFORE physical adaptation
Omega_t  = Generate(C_t+, x_t, kappa_t)          runtime operator synthesis
Delta_t* = argmin J(Delta)  s.t. Legal, RolloutFeasible, RestoreValid
TP+      = Splice(TaskProgram, Delta_t*, kappa_t)
           Execute -> Revalidate -> Restore -> Resume
```

Everything from `Capture` onwards is the **frozen** engine, imported and called:

| step | frozen module actually invoked |
|---|---|
| kappa_t | `rekep_repair.program.continuation.Continuation` (+ `policies.common.resume_contract`) |
| Omega_t | `rekep_repair.repair.synthesis_generator.SynthesisGenerator` → `repair.planner.RepairPlanner` |
| Legal | `rekep_repair.repair.legality_filter.LegalityFilter` |
| Feasible | `rekep_repair.repair.feasibility_filter.FeasibilityFilter` |
| RolloutFeasible | `rekep_repair.repair.rollout_verifier.RolloutVerifier` |
| argmin J | `rekep_repair.repair.scorer.Scorer` |
| orchestration | `rekep_repair.repair.repair_manager.RepairManager.plan()` |
| Splice | `rekep_repair.program.task_program.TaskProgram.splice_repair_before_successor` |
| Restore gate | `TaskProgram.mark_restore_validated` |
| Resume | `TaskProgram.advance()` → `StageState.RESUMED` |
| execution | `rekep_repair.execution.controller.control`, `execution.guard_monitor.stage_exit` |
| world | `rekep_repair.synthetic.env.Synthetic2DEnv` |

New code is confined to `cope/repair_bridge/` (the mapping) and
`cope/benchmark/basket_world.py` + `physical_executor.py` + `physical_episode.py`
(the substrate and harness). **`rekep_repair/` is byte-identical to the
pre-pivot commit** — `git diff --stat 60d94e1 -- rekep_repair/` is empty.

## 3. Requirement-by-requirement

| # | requirement | where | test |
|---|---|---|---|
| 1 | ship the frozen core | `code/rekep_repair/` — full package, 64 modules | `test_the_frozen_repair_core_is_actually_imported` |
| 2 | real `ConstraintStateToRepairGoalCompiler` | `cope/repair_bridge/goal_compiler.py`, called from `RecoveryManager.enter_repair_pipeline` | `test_compiler_turns_lifecycle_transitions_into_repair_requirements` |
| 3 | patch semantics → repair requirements | lifecycle-transition → `RepairGoal` table below | `test_cancellation_requires_a_resumable_end_state_not_a_retarget` |
| 4 | continuation before physical adaptation | `continuation_capture.capture_continuation`, called first | `test_continuation_is_captured_before_the_repair_runs` |
| 5 | multiple runtime candidates | best-first planner returns k plans → k concrete programs | `test_multiple_candidate_programs_are_synthesised_at_runtime` |
| 6 | real sequential rollout verifier | `RolloutVerifier.verify` per candidate | `test_every_candidate_is_rollout_verified` |
| 7 | hard rejection | `RepairManager` rejects; no score penalty | `test_an_unsatisfiable_goal_is_hard_rejected_not_scored_down` |
| 8 | splice into `TaskProgram` | `splice_repair_before_successor` | `test_the_selected_candidate_is_spliced_into_the_task_program` |
| 9 | non-tautological restore + resume | contract captured pre-adaptation | `test_the_restore_contract_can_actually_fail` |
| 10 | FSR-PC uses the same stack | one shared `enter_repair_pipeline` | `test_both_arms_compile_identical_repair_requirements` |
| 11 | integration tests | `tests/test_repair_integration.py`, 63 tests | — |
| 12 | new folder | `cope_fsrpc_交接_v2/`; v1 untouched | — |

## 4. The mapping the compiler performs

| lifecycle transition | physical meaning | compiled requirement |
|---|---|---|
| `ACTIVE → OVERRIDDEN` (re-grounded) | the target moved | `aligned_to_current_target`, `restore_valid` |
| `ACTIVE → SUSPENDED` | set the goal aside | `restore_valid` |
| `ACTIVE → EXPIRED` (cancelled) | stop pursuing it | `restore_valid` |
| `SUSPENDED → ACTIVE` (restored) | resume the old goal | `restore_valid` (+ the slot's own restore predicate) |
| insert of a HARD safety slot | new safety envelope | `safe_clearance`, `restore_valid`, `not obstacle_present` |
| world: object not grasped | slip | `object_grasped`, `object_stable` |

Every requirement carries the slot and transition that induced it, so the trace
answers *why* the robot had to do something, not only *what* it did.

Two modelling corrections were needed and are worth recording:

- **A suspended goal does not require clearing an obstruction.** The first
  version compiled `not obstacle_present` for a suspension, so the planner
  emitted `WaitUntilClear` and the rollout verifier correctly rejected every
  candidate — the obstruction never leaves. Setting a goal aside obliges the
  robot to end *resumable*, nothing more.
- **An unavailable basket is an absent target, not an obstacle.** Modelling it
  as a permanent obstruction produced the same unsatisfiable goal. Absence is
  carried by `blocked_targets` and shows up in `placement_valid()`.

Both were caught by the verifier hard-rejecting candidates, which is the engine
working as intended on an incorrectly stated problem.

## 5. Why both arms provably share the stack

`RecoveryManager.enter_repair_pipeline(before, after, adaptation,
adaptation_kind, world, event_id, step)` is the single entry point. Both
policies call it with the identical signature immediately after producing their
state update.

- The **compiler is policy-blind**: its signature contains no policy, method or
  arm parameter (asserted by test).
- `adaptation_kind` may only select the `PATCH` vs `REGENERATION` trace marker;
  a test asserts the identifier does not appear anywhere in the method body
  after continuation capture.
- The diff is taken on **canonical** slot ids, so FSR-PC's re-minted ids
  (`g_butter#r2`) compare correctly against CoPE's stable ones. Without this the
  baseline would look like it replaced every slot and would have been handed
  different requirements — unfairness created by bookkeeping.

Measured over the pilot: identical adaptation-input fingerprints, identical
compiled repair-goal fingerprints, and identical downstream work (repairs,
candidates, rollouts, splices, restores, resumes all equal), while the arms
differ exactly where they should — 0 vs 10 slots regenerated, identity preserved
20/20 vs 0/20.

## 6. The gate

```bash
python3 scripts/cope_pipeline_trace.py --all --seed 0
```

Prints the full marker sequence per interruption per arm and exits non-zero if
any is incomplete. Current status: **PASS** on I1–I4 for both arms.

Sample (condition I1, CoPE — FSR-PC is identical except for the slot-1 marker):

```
EVENT
PATCH
CONTINUATION_CAPTURED    captured before physical adaptation
REPAIR_GOAL_COMPILED     required_true=['aligned_to_current_target','restore_valid']
CANDIDATES_GENERATED     n=3 planner_nodes=13
                         ['Suspend+UpdateTargetContract+Stabilize+Realign+Resume',
                          'Suspend+Stabilize+UpdateTargetContract+Realign+Resume',
                          'Suspend+Stabilize+Realign+UpdateTargetContract+Resume']
ROLLOUT_RESULTS          3 verified
CANDIDATE_SELECTED       Suspend+UpdateTargetContract+Stabilize+Realign+Resume
                         score=2.350 rejected=0
GRAPH_SPLICED            ['suspend#0','updatetargetcontract#1','stabilize#2',
                          'realign#3','resume#4']  stages 1 -> 6
RESTORE_VALIDATED        validated=True handoff_error=0.0
STAGE_RESUMED
```

## 7. Honest limitations of this integration

1. The world is the frozen **2D synthetic env**, not a manipulation simulator.
   That is what the rollout verifier was written against, so verification is now
   meaningful — but it is still not a robotics result.
2. The basket task is mapped onto that env as a sequence of transport **legs**.
   A leg is the frozen env's nominal task with the basket as `p_goal`. This is a
   modelling choice, not something the memo prescribes.
3. `handoff_error = 0.0` after a successful repair is expected, not suspicious:
   `Realign` drives back to the captured handoff pose. The gate is shown to be
   non-tautological by a test that displaces the state and asserts refusal.
4. The engine's own safe-fallback path is exercised in a test but does not occur
   in the pilot (0 fallbacks in 105 repairs). Fallback behaviour under a harder
   world is therefore untested empirically.
5. Interruptions are delivered at a fixed point after a leg starts
   (`MIN_STEPS_BEFORE_INTERRUPT = 3`). Timing is method-independent, but it is
   not randomised, so this pilot says nothing about sensitivity to *when* an
   interruption lands.

---

# r2 additions

The unified method is unchanged:

    event -> CoPE patch or FSR-PC regeneration -> updated constraint state
    -> continuation capture -> repair-goal compilation -> candidate synthesis
    -> rollout verification -> graph splice -> guarded restoration
    -> resumed execution

Three integration-level changes, none of which touches the method:

1. **`SharedRepairEngine.disable_rollout_verification`** — used only by
   `CoPE_no_rollout_verification`. It withholds `cfg` from `RepairManager` (and
   the backend `verifier_factory`), so sequential rollout verification is
   skipped while the **legality and feasibility filters stay on**. Asserted by
   `test_the_ablation_keeps_legality_and_feasibility_on`.
2. **Representation-neutral goal compilation** — see
   `FAIR_COMPARISON_PROTOCOL.md` F8.
3. **`suspended -> overridden`** added to the lifecycle table so a suspended
   goal may be covered by a temporary stand-in (I5). `Override`'s side effects
   are unchanged, the suspension's priority snapshot and restore predicate are
   preserved, and `EXPIRED` remains terminal.

## Verifier status

The first execution rollout-verified 162 candidates and rejected **zero**, so it
did not demonstrate that the verifier changes decisions. The r2 probe does, on
CPU:

    CoPE_full                     : 4 candidates, 4 rejected (collision), safe fallback
    CoPE_no_rollout_verification  : 4 candidates, 0 rejected, candidate accepted

Honest limitation: on the CPU synthetic world the synthesised candidates share
an operator multiset, so the verifier rejects them uniformly rather than
2-of-3. The reject/reject/accept split must be established on LIBERO, where the
v2 preflight already recorded exactly it (candidate 0 unsafe contact, candidate
1 handoff 0.142 m, candidate 2 accepted).
