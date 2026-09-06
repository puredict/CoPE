# Code map — practical navigation

All paths are relative to `code/`. Nothing here uses absolute paths.

## "Where do I find…?"

| Question | Answer |
|---|---|
| **Where does repair synthesis happen?** | `rekep_repair/repair/planner.py` → `RepairPlanner.plan()`; operator model in `repair/abstract_state.py` (`SYMBOLIC_OPS`) |
| **Where is rollout verification?** | `rekep_repair/repair/rollout_verifier.py` → `RolloutVerifier.verify()` |
| **Where is the continuation captured?** | `rekep_repair/policies/online_repair.py` → `_plan_and_splice()`; the object is `program/continuation.py` |
| **Where does graph rewriting happen?** | `rekep_repair/program/task_program.py` → `interrupt_active_stage()` then `splice_repair_before_successor()` |
| **Where do the policies differ?** | `rekep_repair/policies/` — all inherit `OnlineRepairPolicy` and override `_make_generator()` (synthesis vs. templates vs. precompiled library) |
| **Where are benchmark scenes generated?** | `rekep_repair/benchmark/scenes.py` → `sample_scene(EpisodeSpec)` |
| **Where are statistics computed?** | `rekep_repair/benchmark/statistics.py` (Wilson, paired bootstrap, exact McNemar, Holm) |
| **Where does the ReKep adapter begin?** | `rekep_repair/adapter.py` (frozen interface) → `rekep_repair/rekep_adapter.py` (GPU implementation) |
| **Where is model mismatch injected?** | `rekep_repair/benchmark/mismatch.py` → `MismatchedEnv` |
| **Where are the ablations?** | `rekep_repair/policies/ablations.py` |

## Package responsibilities

### `program/` — the task-program IR

| File | Responsibility |
|---|---|
| `stage.py` | `StageSpec` (subgoal/path constraints, guards, mode, metadata) and `StageState` enum |
| `task_program.py` | The executable program + **runtime state machine**. Enforces: interrupted stage becomes `SUSPENDED` not `COMPLETED`; successor unreachable until restore validates; `advance()` is **atomic** (all checks before any mutation); repair node IDs namespaced by `stage::event::instance` |
| `continuation.py` | κ — snapshot of the interrupted computation (state, attachment, handoff pose, resume contract) |
| `graph.py` | `TaskGraph`, `splice_after()`, acyclicity (Kahn) |
| `contracts.py` | Entry/handoff contracts with continuous margins |

**Implements:** the splice operator `sᵢ^suspended → u₁…uₘ → sᵢ^resumed(κ) → sᵢ₊₁`.

### `events/` — detection

`event.py` (types), `predicates.py` (deterministic predicates), `detector.py`
(`EventDetector` + `NoiseModel` for delay / false positives / false negatives).

### `repair/` — the synthesis + verification engine

| File | Responsibility |
|---|---|
| `abstract_state.py` | `AbstractState`, `RepairGoal`, `WorldPredicates`, `SYMBOLIC_OPS` (precondition/effect/cost). **`goal_from_predicates()` builds the union goal for compound events.** |
| `planner.py` | Bounded best-first search returning k goal-reaching operator sequences + exploration trace |
| `synthesis_generator.py` | Instantiates searched plans into candidates (**this is synthesis**) |
| `candidate_generator.py` | Instantiates prewritten templates (**this is the template baseline**) |
| `legality_filter.py` | Acyclicity, `HasRestore`, attachment consistency |
| `feasibility_filter.py` | Cheap terminal handoff-reachability screen (a heuristic, not verification) |
| `rollout_verifier.py` | **Sequential** operator-by-operator rollout; hard-rejects collision, guard timeout, horizon overrun, attachment violation, unmet requirement residual |
| `verifier_variants.py` | `NoVerifier` / `Nominal` / `Conservative` / `Receding` (the latter two were measured and **fail** — kept for the record) |
| `scorer.py` | State-dependent scoring from rollout quantities |
| `repair_manager.py` | The pipeline: generate → legality → feasibility → **rollout** → score → select, or safe fallback |
| `operator.py` | Concrete operator → `StageSpec` instantiation (controller + guard keys) |

### `execution/` — the shared harness

`context.py` (`ExecutionContext`, incl. the **current** `task_goal`),
`action.py` (**single source of truth** for action clipping — used by both env
and verifier), `controller.py` (behavior-keyed controllers; operator semantics
are **non-overlapping** — only `Retreat` opens clearance), `guard_monitor.py`,
`executor.py` (the one harness every method runs through), `fallback.py`,
`provenance_logger.py`.

### `policies/` — the methods

`fixed_program`, `path_only`, `safe_stop`, `template_repair`,
`offline_recovery` (branch-selection), `offline_parameterized`
(**the strong baseline** — same runtime capability as online, only cannot search),
`online_repair` (**ours**), `verified_repair` (verifier variants),
`ablations.py`.

### `synthetic/` — the CPU world

`dynamics.py` (`SceneConfig`, `Obstacle`, `Rollout` + the three success
metrics), `env.py` (`Synthetic2DEnv`, `predicates()`), `conflict_bound.py`
(Theorem 1).

### `benchmark/` — randomized evaluation

`scenes.py` (three task families; **process-stable** blake2b seeding),
`runner.py` (paired grid), `statistics.py`, `mismatch.py`, `probe.py`
(internal-activation instrumentation used for the mechanism study).

### `tests/` — 71 tests

Program semantics, repair filters, execution properties, synthesis semantics,
events, scientific validity, action limits, mechanism activation, baseline
validity + adapter contract.

## End-to-end call graph

```
Executor.run(policy)
└─ loop t = 0 … horizon
   ├─ policy.act(ctx)                         [policies/online_repair.py]
   │  ├─ _maybe_advance(ctx)                  advance stages whose guards hold
   │  │  ├─ stage_exit(...)                   [execution/guard_monitor.py]
   │  │  ├─ _validate_restore(ctx)            → TaskProgram.mark_restore_validated
   │  │  └─ TaskProgram.advance()             ATOMIC; raises RestorationBlocked
   │  ├─ detector.detect(ctx)                 [events/detector.py]
   │  └─ _plan_and_splice(event, ctx)         ── only if a repair is required
   │     ├─ Continuation(...)                 capture κ  [program/continuation.py]
   │     ├─ env.predicates(d_react)           the SAME channel every policy gets
   │     ├─ state_from_predicates / goal_from_predicates   [repair/abstract_state.py]
   │     ├─ RepairManager.plan(...)           [repair/repair_manager.py]
   │     │  ├─ SynthesisGenerator.generate()  → RepairPlanner.plan()   SEARCH
   │     │  ├─ LegalityFilter.check()         acyclic + restore + attachment
   │     │  ├─ FeasibilityFilter.check()      cheap reachability screen
   │     │  ├─ RolloutVerifier.verify()       SEQUENTIAL rollout; hard reject
   │     │  └─ Scorer.select()                state-dependent scoring
   │     ├─ TaskProgram.interrupt_active_stage(κ)        → SUSPENDED
   │     └─ TaskProgram.splice_repair_before_successor() → graph rewrite
   ├─ control(behavior, ctx, stage, κ, params, ctx.task_goal)  [execution/controller.py]
   ├─ ProvenanceLog.add(record)
   └─ env.step(action) → clip_action(...)     [execution/action.py]  SHARED
```

The repair stages then execute, `Resume`'s guard is the restore contract, and on
validation the program enters `sᵢ^resumed(κ)` and finishes the interrupted stage.

## The three paradigms (do not conflate them)

| | precompiled full branch | runtime template instantiation | runtime operator synthesis |
|---|---|---|---|
| class | `Offline*Policy` | `TemplateRepairPolicy` | `OnlineRepairPolicy` |
| stored | complete branch per combination | complete sequence per event class | **atomic operators only** |
| runtime decision | which branch | which template | **which sequence to construct** |
| handles novel composition | no | no | **yes** |
