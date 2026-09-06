# Codex Master Prompt
## CoPE Experiment 1 — Repeated-Interruption Planning under History Pressure v2

You are working inside the repository `puredict/CoPE`.

Act as the lead research engineer for a confirmatory experiment. Do not merely write a design document. Audit the current code, implement the complete experiment, add tests, run zero-provider preflight, run simulator smoke tests when dependencies exist, and leave the repository ready for a formal multi-GPU run. Do not ask the user questions. Resolve non-critical ambiguity with the most conservative, auditable, scientifically fair design. If a required external checkpoint, endpoint, simulator dependency, or plugin is unavailable, implement and test everything that does not require it, then fail closed with an explicit `BLOCKED_*` status. Never fabricate formal results.

The source repository was inspected at commit:

`84e1e742579899adb67efee92cef16efca063b31`

Start by recording the actual current HEAD. Do not assume it still equals this SHA. Create a new branch and do not modify or overwrite frozen v1 manifests, prompts, results, or claim-decision files.

---

# 1. Scientific objective

Implement Experiment 1 for the paper:

**Plan Around Changes, Learn from Violations: Persistent Constraints for Long-Horizon VLA Agents**

This experiment tests only the runtime claim:

> Under repeated interruptions and growing task history, local persistent constraint editing preserves the correct planning problem better than reconstructing a full task state or plan, and this preservation improves downstream execution.

The causal chain to test is:

```text
repeated interruptions / growing history
→ different task-state maintenance
→ different compiled planning problem
→ different planning behavior
→ different final task success
```

The primary outcome is downstream task execution, not JSON accuracy.

The experiment must distinguish:

1. `PersistentConstraintLedger C_t = (S_t, G_t, H_t)`
   - `S_t`: commitment occurrences;
   - `G_t`: typed relations;
   - `H_t`: append-only transition/audit history.

2. `ExecutionContext E_t = (B_t, M_t, kappa_t)`
   - `B_t`: current world belief and grounding evidence;
   - `M_t`: verified progress certificates;
   - `kappa_t`: current physical/program continuation.

3. Three separate statuses:
   - applicability/lifecycle;
   - grounding validity;
   - satisfaction/progress.

Do not collapse them into one `status` field.

---

# 2. What this experiment may and may not claim

## Allowed claim if the registered gates pass

Persistent local editing preserves the planning problem and downstream execution more reliably than non-persistent full rewriting as interruptions accumulate.

## Required nuance

An information-equivalent generic persistent transaction is a fair control. If it matches CoPE in semantic or execution accuracy, conclude that the main reliability benefit comes from persistent responsibility structure. CoPE's additional contribution is a compact, typed, directly validatable, atomic carrier.

## Forbidden claims

Do not claim any of the following from this experiment:

- typed syntax is inherently more intelligent than every generic persistent representation;
- CoPE alone solves perception, VLA control, safety, or open-world specification induction;
- controlled oracle execution is learned-VLA evidence;
- a custom continuation-repair backend is original published ReKep;
- semantic state correctness automatically equals physical task success;
- an invalid or rejected patch is a successful recovery;
- missing formal dependencies are successful cells;
- any current v1 result may be overwritten or silently pooled with v2.

---

# 3. Existing code to read before editing

Read at minimum:

```text
README.md
configs/repeated_interruptions_v1.yaml
experiments/repeated_interruptions.py
cope/schema.py
cope/operations.py
cope/validator.py
cope/replay.py
cope/formal_recovery.py
cope_benchmark/adapters.py
cope_benchmark/interruption_scheduler.py
cope_benchmark/interruptions.py
cope_benchmark/task_progress.py
cope_benchmark/metrics.py
cope_benchmark/repeated_manifest.py
cope_benchmark/oracle_skill_controller.py
research/167_OCCURRENCE_CONFIRMATORY_V3_RESULT_AND_CLAIM_DECISION.md
research/168_NEXT_CRITICAL_EXPERIMENT_NONINFERIORITY_PREREG_DRAFT.md
docs/EXPERIMENTS_INDEX_BEGINNER_CN.md
```

If the workspace contains the continuation-carrying repair package, inspect and adapt rather than copying blindly:

```text
SharedRepairEngine.py
ConstraintStateToRepairGoalCompiler.py
REPAIR_INTEGRATION.md
R2_Final_Audit.md
ReKep_Same_Scene_Feasibility.md
```

The existing oracle skill controller explicitly uses privileged simulator state. It may be used only for controlled pipeline qualification, never as the learned-policy substrate for the end-to-end VLA protocol.

---

# 4. New code layout

Add v2 as an isolated experiment family:

```text
configs/
  repeated_interruptions_v2_pilot.yaml
  repeated_interruptions_v2_formal.yaml

schemas/
  repeated_v2/
    event_evidence.schema.json
    cope_patch.schema.json
    generic_transaction.schema.json
    full_state.schema.json
    planning_directive.schema.json
    event_result.schema.json
    episode_result.schema.json

cope_benchmark/
  repeated_v2/
    __init__.py
    enums.py
    schema.py
    canonical.py
    task_catalog.py
    task_calibration.py
    events.py
    scheduler.py
    evidence.py
    execution_context.py
    occurrence.py
    patch_contract.py
    generic_contract.py
    state_engine.py
    generic_engine.py
    history.py
    prompts.py
    parsers.py
    provider.py
    compiler.py
    planner_backend.py
    vla_adapter.py
    dynamic_evaluator.py
    metrics.py
    journal.py
    integrity.py
    runner.py
    statistics.py
    claim_decision.py
    adapters/
      __init__.py
      base.py
      cope_typed_edit.py
      generic_persistent_edit.py
      full_state_regeneration.py
      full_history_replan.py
      rag_replan.py
      summary_memory_replan.py
      skill_local_replan.py
      classical_execution_monitor.py
      oracle_persistent_update.py

experiments/
  repeated_interruptions_v2.py

tools/
  calibrate_repeated_v2_tasks.py
  build_repeated_v2_task_catalog.py
  build_repeated_interruptions_v2_manifest.py
  validate_repeated_interruptions_v2.py
  freeze_repeated_interruptions_v2.py
  analyze_repeated_interruptions_v2.py

scripts/
  run_repeated_interruptions_v2.sh
  run_repeated_interruptions_v2_slurm.sh.example

docs/
  REPEATED_INTERRUPTIONS_V2_PROTOCOL.md
  REPEATED_INTERRUPTIONS_V2_METHOD_CONTRACTS.md
  REPEATED_INTERRUPTIONS_V2_RUNBOOK.md

tests/
  repeated_v2/
    test_schema.py
    test_occurrence.py
    test_task_catalog.py
    test_events.py
    test_scheduler.py
    test_evidence.py
    test_state_engine.py
    test_generic_engine.py
    test_method_parsers.py
    test_information_parity.py
    test_prompt_leakage.py
    test_compiler_purity.py
    test_dynamic_evaluator.py
    test_metrics.py
    test_journal.py
    test_runner_resume.py
    test_statistics.py
    test_claim_decision.py
    test_mocked_end_to_end.py
```

Do not place v2-specific semantics into frozen v1 modules unless the change is strictly backward-compatible and fully regression-tested. Prefer the isolated namespace.

---

# 5. Frozen experimental design

Implement two protocols. They are parts of one experiment family and must be reported separately.

## Protocol A — Controlled state-to-plan stress test

Purpose: isolate state maintenance and planning-problem preservation.

All non-oracle methods receive the same accurate, structured, agent-visible event evidence. They do not receive the correct patch, correct lifecycle transition, or hidden failure-cause label.

Execution substrate:
- deterministic abstract planner or existing privileged oracle skill controller;
- clearly labeled `controlled_mechanism`;
- never described as learned VLA evidence.

Continuous trajectory:
- eight sequential events in one episode;
- metrics at checkpoints after events `0, 1, 2, 4, 8`;
- no reset to oracle state after a method error.

## Protocol B — End-to-end learned-VLA execution

Purpose: test whether state-maintenance differences propagate to actual VLA behavior.

All methods start from the same raw observations, user messages, initial simulator state, seeds, detector/verifier implementation, action budget, VLA checkpoint, compiler family, and execution backend.

Requirements:
- no hidden event cause in any non-oracle input;
- no privileged geometry in the learned VLA adapter;
- four sequential events in one episode;
- metrics at checkpoints after events `0, 1, 2, 4`;
- actual VLA/action-policy inference;
- an oracle controller is forbidden as the formal policy substrate.

If no production VLA adapter is configured, stop Protocol B with `BLOCKED_VLA_ADAPTER_UNAVAILABLE`. Do not substitute oracle control and call it Protocol B.

## Formal task/session scale

Use all semantically eligible LIBERO-10 tasks; require at least eight. Eligibility is frozen before formal testing and may depend only on task structure and clean-policy calibration, never on the relative performance of experimental methods.

Default formal session grid:

```text
initial_state_ids = [0, 1, 2, 3, 4]
policy_seeds      = [11, 29, 47]
```

Thus each selected task has 15 paired master sessions.

Each method runs one continuous trajectory per master session. Do not rerun independent episodes for K=1,2,4,8; use checkpoints from the same growing-history trajectory.

---

# 6. Task calibration and catalog

Implement a separate calibration phase.

A task is eligible only if:

1. it has at least two independently verifiable milestones or goal predicates;
2. at least one completed milestone can remain valid through later interruptions;
3. it contains an object/receptacle grounding that can be changed safely;
4. it supports at least one cross-skill requirement or persistent preference;
5. the clean learned policy success rate is in `[0.40, 0.95]` on the preregistered calibration seeds;
6. all required event injections pass feasibility checks.

Task selection rules:
- enumerate all LIBERO-10 tasks;
- include every task satisfying the rules, up to all ten;
- require at least eight or stop with `BLOCKED_INSUFFICIENT_ELIGIBLE_TASKS`;
- do not select tasks based on CoPE-vs-baseline differences;
- calibration seeds and formal seeds must be disjoint;
- freeze the resulting `task_catalog_v2.json` and its SHA256 before formal calls.

Each task catalog record must include:

```text
task_id
task_name
original_instruction
object aliases and simulator names
receptacle/region aliases
initial achievement goals
maintenance invariants
hard safety constraints
soft preference templates
milestone predicates
alternative valid goals
replaceable goal families
safe event-injection poses/regions
supported event families
semantic trigger definitions
dynamic evaluator predicates
planner compiler metadata
```

Do not silently infer unsupported task semantics during a formal run. Catalog gaps are preflight failures.

---

# 7. Event and schedule design

Support at least these event families:

```text
TARGET_OBJECT_DISPLACED
GOAL_RECEPTACLE_OR_GROUNDING_CHANGED
TEMPORARY_NO_GO_APPEARS
TEMPORARY_NO_GO_CLEARS
USER_ADDS_PERSISTENT_PREFERENCE
TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE
TOOL_OR_TARGET_AVAILABLE_AGAIN
USER_REPLACES_ACTIVE_GOAL
USER_CANCELS_ACTIVE_GOAL
USER_REISSUES_RETIRED_GOAL
```

Each event must have two separate representations:

1. `PublicEventPayload`
   - user utterance or observation-derived evidence;
   - visible to all non-oracle methods.

2. `HiddenCanonicalEffect`
   - true affected commitment families;
   - canonical state transition;
   - simulator intervention metadata;
   - scoring only.

Never expose `HiddenCanonicalEffect`, expected operator names, expected target occurrence, or fault labels to non-oracle prompts.

## Master schedules

Build an eight-event master schedule per master episode using a constrained topological shuffle. Pair dependencies must hold:

```text
NO_GO_CLEARS after NO_GO_APPEARS
AVAILABLE_AGAIN after TEMPORARILY_UNAVAILABLE
REISSUES_RETIRED_GOAL after replacement or cancellation retired an occurrence
RESTORE cannot precede fresh revalidation evidence
```

Every eight-event schedule must contain:
- at least one grounding shift;
- at least one suspend/revalidate/restore lifecycle sequence;
- at least one persistent preference;
- at least one goal replacement or cancellation;
- at least one fresh occurrence of a previously used semantic goal.

Balance event-family positions across master episodes. Use deterministic seeded schedule generation and verify prefix legality.

## Semantic triggers

Do not rely only on fixed policy steps. Each event uses:

```text
trigger predicate or semantic milestone
earliest policy step
latest policy step
minimum steps since previous event
physical feasibility guard
```

Examples:
- after a verified milestone;
- during transport but before placement;
- after a temporary constraint was active for N steps;
- before the final active goal is completed.

If a method fails before reaching the trigger, keep the master episode in the denominator and record `EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE`. Do not oracle-reset it.

Physical interventions must not teleport a grasped object unless the event explicitly models an external forced displacement. Use task-catalog safe poses and feasibility guards.

---

# 8. Agent-visible evidence and hidden truth

Define:

```text
EventEvidence q_t = (
  hypothesis,
  confidence,
  evidence_ids,
  evidence_timestamp,
  observation_refs,
  user_message,
  affected_entity_hypotheses
)
```

and separately:

```text
HiddenEventCause xi_t_star
```

Only `q_t` is available to non-oracle methods.

Protocol A may generate exact `q_t` from the canonical event, but must not include the correct patch or responsibility label.

Protocol B generates `q_t` from the shared detector/verifier pipeline using the same raw observations for every method. The detector may say that an object pose changed; it may not say that the correct operation is `Expire`, that the cause is external, or that CoPE should win.

All evidence records require IDs, timestamps/versions, provenance, and confidence.

---

# 9. State model

## Persistent ledger

Define:

```text
C_t = (S_t, G_t, H_t)
```

Each commitment occurrence contains:

```text
stable family key
unique occurrence ID
role
predicate / planner-facing grounding specification
arguments
lifecycle
priority / hardness
source
authority
grounding-validity state
restore guard
dependencies
provenance
evidence references
created-at event
retired-at event
```

Use separate enums:

```text
Lifecycle:
  ACTIVE
  SUSPENDED
  OVERRIDDEN
  EXPIRED

GroundingValidity:
  VALID
  DEGRADED
  UNKNOWN
  INVALID

Satisfaction:
  UNRESOLVED
  SATISFIED
  VIOLATED
  UNKNOWN
```

Do not use one field for all three.

## Execution context

Define:

```text
E_t = (B_t, M_t, kappa_t)
```

Ownership is exclusive:

- `B_t`: current uncertain physical facts, poses, visibility, availability, held-object probability;
- `M_t`: verifier-backed progress certificates;
- `kappa_t`: active stage/skill, program counter, resumable suffix, controller state.

Example:

```text
B_t: holding(robot, mug)=0.96
M_t: grasp(mug) milestone verified by record V104
kappa_t: active_stage=transport, next_stage=place
```

Do not let the patch reasoner arbitrarily rewrite `B_t`, `M_t`, or `kappa_t`. Their owners are perception, task monitor, and executor respectively.

## Occurrence semantics

Keep semantic family identity separate from occurrence identity.

```text
family_key: goal:inside:red_mug:cabinet
occurrence_id: goal:inside:red_mug:cabinet@2
```

Rules:
- reissue creates a fresh occurrence;
- model output requests a new occurrence but the trusted allocator assigns the final ID;
- replacement/cancellation never silently mutates the old occurrence;
- old occurrences remain auditable;
- an exclusive goal family may have at most one active occurrence;
- restore never creates a fresh occurrence;
- a repeated semantic request after retirement is not a restore.

---

# 10. CoPE v2 patch contract

Do not require the model to reprint every inherited slot.

A CoPE proposal contains:

```json
{
  "schema_version": "cope-repeated-v2/patch-1",
  "episode_id": "...",
  "event_index": 1,
  "base_revision": 4,
  "affected_scope": ["..."],
  "protected_ids": ["..."],
  "protected_projection_sha256": "...",
  "evidence_ids": ["..."],
  "checks": [],
  "operations": [],
  "confidence": 0.0
}
```

Use a fixed operator vocabulary:

```text
INSERT
SUSPEND
OVERRIDE
SET_PRIORITY
EXPIRE
RESTORE
```

`REVALIDATE` is represented in `checks`, not as an ordinary mutation. It creates a validation record and may authorize a later `RESTORE`, `SET_PRIORITY`, or `EXPIRE`.

Unmentioned slots are preserved by default. `protected_projection_sha256` proves that protected task, user, safety, and verified-progress references have not been silently changed.

Do not reuse the legacy `DEMOTED` lifecycle mode in the v2 contract. Priority changes are not lifecycle changes.

Kernel invariants:
- base revision must match;
- IDs and occurrences must exist unless inserted;
- new IDs come from the trusted allocator;
- lifecycle preconditions must hold;
- expired occurrences cannot be restored;
- restore requires fresh successful evidence satisfying the guard;
- authority restrictions hold;
- edge-type-specific graph invariants hold;
- the protected projection hash matches;
- the entire transaction applies atomically;
- `H_{t+1}` strictly extends `H_t`.

---

# 11. Method arms

Implement exactly these primary non-oracle arms:

```text
cope_typed_edit
generic_persistent_edit
full_state_regeneration
full_history_replan
rag_replan
summary_memory_replan
skill_local_replan
classical_execution_monitor
```

Also implement:

```text
oracle_persistent_update
```

as an upper bound, excluded from non-oracle claims.

## 11.1 CoPE typed edit

Input:
- persistent ledger;
- execution context;
- public evidence;
- relevant trace.

Output:
- CoPE v2 patch contract.

Materialization:
- deterministic CoPE kernel.

## 11.2 Information-equivalent generic persistent edit

It receives exactly the same normalized semantic facts as CoPE:
- IDs;
- occurrence;
- lifecycle;
- relations;
- provenance;
- evidence;
- progress references;
- grounding.

It outputs a method-neutral transaction:

```json
{
  "schema_version": "generic-persistent-v2/tx-1",
  "base_revision": 4,
  "assertions": [],
  "creates": [],
  "writes": [],
  "relation_additions": [],
  "relation_removals": [],
  "evidence_links": [],
  "protected_projection_sha256": "..."
}
```

Do not use CoPE operator names in its prompt or output. Implement a normalized semantic-fact parity test showing that CoPE and generic arms have access to the same facts.

## 11.3 Full-state regeneration

At every event, regenerate the complete current semantic materialization:
- every current and retired occurrence;
- lifecycle;
- grounding-validity state;
- relations;
- active goals;
- hard constraints;
- preferences;
- progress certificates;
- restore guards;
- continuation assumptions.

It need not reproduce immutable raw log bytes, but it must reproduce all semantic history needed for future decisions. A trusted logger may append a “full state regenerated” record; it may not restore omitted semantics.

## 11.4 Full-history replan

Read the full public task/event/action history and regenerate the current planning directive without a persistent commitment ledger.

Output:
- current target occurrence hypothesis;
- initial facts;
- remaining goals;
- hard constraints;
- soft preferences;
- protected progress;
- continuation assumptions;
- ordered macro plan or subgoal.

## 11.5 RAG replan

Index only public history chunks. Retrieve with a frozen retriever under a fixed token budget. Do not index hidden canonical state or scoring labels. Return the same planning-directive schema as full-history replan.

## 11.6 Summary-memory replan

Maintain a free-text or lightly structured summary without occurrence/lifecycle enforcement. At each event, one high-level call jointly returns:
- updated summary;
- planning directive.

This keeps the high-level event-call count equal to other generative arms.

## 11.7 Skill-local replan

Receive:
- active skill;
- local preconditions/postconditions;
- recent observation/action window;
- current subgoal;
- public event evidence.

It does not receive the full persistent ledger. Return a local recovery/next-skill directive.

## 11.8 Classical execution monitor

Implement a strong deterministic PDDL/BT-style state monitor:
- current facts;
- completed milestones;
- skill preconditions/effects;
- local execution-monitoring rules.

It may maintain structured facts, but not CoPE occurrence/lifecycle/provenance or learning-credit identity. It uses the same downstream planner/executor.

## 11.9 Oracle persistent update

Uses hidden canonical state and event effects. It is a diagnostic upper bound only. Mark every output as privileged.

---

# 12. Reasoner fairness

All generative arms use:
- the same foundation-model checkpoint;
- the same provider;
- the same decoding configuration;
- temperature 0;
- the same seed policy;
- zero semantic retries;
- the same public evidence;
- one high-level adaptation call per event;
- the same common downstream executor.

Use two clearly separated settings:

1. `evidence_matched`
   - same underlying public facts;
   - natural interface length;
   - common sufficiently large context cap.

2. `token_matched`
   - same input token ceiling;
   - frozen truncation/retrieval policy;
   - secondary robustness analysis.

Record input/output tokens and exact prompts/responses.

Do not expose method names, condition labels, expected operations, hidden event cause, canonical state, or file paths in prompts. Implement recursive leakage scans.

Use method-specific output schemas, because output interface is the treatment. Keep the common task/evidence preamble semantically identical.

---

# 13. Common planning and execution pipeline

Every arm must ultimately produce a normalized `PlanningProblem`:

```text
initial facts
active target occurrence IDs
remaining achievement goals
hard constraints
soft preferences and weights
forbidden regressions
current groundings
restore eligibility
progress certificates
continuation assumptions
```

A pure compiler translates only the method's accepted state/directive. It must not:
- read hidden canonical state;
- add omitted commitments;
- correct wrong occurrences;
- infer a goal from task ID;
- restore missing progress;
- use simulator truth except through public execution context.

Implement a compiler-purity test with poisoned hidden fields.

All methods then use the same planner/VLA/backend.

## Controlled backend

May use the existing privileged oracle skill controller or deterministic abstract executor, but label outputs as `controlled_mechanism`. The controller must execute the planning problem it is given and must not correct its semantics.

## Learned-VLA backend

Define a production plugin interface:

```python
class VLAAdapter(Protocol):
    provider_id: str
    learned_policy: bool
    uses_privileged_state: bool

    def reset(self, *, task, seed, initial_observation) -> None: ...
    def begin_subgoal(self, compiled_instruction) -> None: ...
    def act(self, observation) -> ActionChunk: ...
    def close(self) -> None: ...
```

Formal Protocol B requires:
- `learned_policy is True`;
- `uses_privileged_state is False`;
- finite, shape-valid actions;
- checkpoint/model identity recorded;
- no fake/mock/scripted/oracle provider markers.

Use a configurable plugin factory rather than hard-coding an endpoint schema:

```text
module.path:factory_name
```

Search the workspace for an existing OpenVLA/OpenVLA-OFT client and wrap it if available. If none exists, implement the protocol and fail closed until a production factory is configured.

## Continuation-carrying repair backend

If the uploaded repair package is available, wrap it behind:

```python
class PlannerBackend(Protocol):
    def solve(self, problem: PlanningProblem, context: ExecutionContext) -> ExecutionPlan: ...
```

Use:
- state-to-RepairGoal compilation;
- continuation capture;
- candidate recovery;
- verification;
- splice/resume.

It must remain representation-neutral and must not use hidden truth to repair a baseline's semantic omissions. Call it a continuation-carrying executable repair backend, not original ReKep.

---

# 14. Runtime loop

For each `(master_episode, method)`:

1. Reset an independent environment copy to the same initial state and seeds.
2. Initialize the method's own accepted state.
3. Execute using the common backend.
4. At each semantic trigger:
   - checkpoint simulator, RNG, method state, execution context, and action trace;
   - inject the public/physical event;
   - update hidden canonical state separately;
   - obtain a fresh post-event observation;
   - build agent-visible `EventEvidence`;
   - call the method once;
   - parse and validate the proposal;
   - if accepted, commit method state;
   - if rejected, retain the previous accepted state and invoke the frozen fallback;
   - compile the method state/directive with the pure compiler;
   - solve and execute with the common backend;
   - continuously update belief, progress, continuation, and verifier records;
   - store an atomic event result.
5. Continue to the next scheduled event from the method's own state.
6. Never replace an arm's state with canonical/oracle state after an error.
7. Finalize with the sealed dynamic evaluator.

If a method fails before a later event, record the remaining events as `EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE`; do not drop the trajectory.

---

# 15. Dynamic task evaluator

Do not rely only on static LIBERO `_check_success()` because user goal changes alter the active task.

Implement a sealed evaluator with access to simulator truth and hidden canonical task state. It must be independent of the agent's trainable/runtime verifier.

Final success requires:
- every currently active achievement goal is satisfied;
- no expired, cancelled, or superseded goal was intentionally executed after retirement;
- all monitored hard constraints remained satisfied;
- all unaffected verified milestones were preserved;
- no timeout;
- no manual intervention;
- required events were reached unless prior method failure prevented them.

Track macro actions and target occurrence IDs so that wrong-occurrence execution can be scored even when two occurrences share the same physical predicate.

---

# 16. Metrics

## Primary

`final_active_task_success_after_last_event`

Protocol B checkpoint 4 is the primary confirmatory outcome.

## Key secondary outcomes

### Planning-problem fidelity
Compare the method's normalized problem to the hidden canonical problem:
- exact active occurrence set;
- remaining goals;
- hard constraints;
- soft preferences;
- protected progress;
- current grounding;
- restore eligibility;
- continuation assumptions.

Report exact match and field-level macro F1.

### History corruption
Any unauthorized or unrelated change to:
- commitment identity;
- lifecycle;
- relation;
- persistent preference;
- retired occurrence;
- evidence lineage;
- protected history projection.

### Completed-step regression
An unaffected verified milestone is forgotten, undone, or unnecessarily re-executed.

### Wrong-occurrence execution
A plan/action is bound to an expired, cancelled, superseded, or completed occurrence instead of the current one.

### Restoration correctness
- restore without fresh successful revalidation;
- stale-evidence restore;
- failure to restore when guards and evidence permit it;
- restore of an expired occurrence.

### Behavioral efficiency
- redundant macro actions;
- additional VLA steps;
- recovery-plan length;
- wrong-target actions;
- time to resume;
- timeout.

### Computational efficiency
- high-level calls;
- input/output tokens;
- reasoner wall time;
- validation/apply time;
- compilation time;
- planning time;
- VLA inference time;
- amortized event overhead.

Do not pool controlled-mechanism metrics with learned-VLA metrics.

---

# 17. Statistical plan

The experimental unit is a complete master session:

```text
task + initial state + policy seed + master event schedule
```

All method comparisons are paired by master session.

## Primary comparison

At Protocol B event checkpoint 4:

```text
CoPE typed edit
vs.
primary non-persistent comparator
```

Select the comparator on a disjoint development split from:

```text
full_state_regeneration
full_history_replan
rag_replan
summary_memory_replan
skill_local_replan
classical_execution_monitor
```

Selection rule:
1. highest dev final success at checkpoint 4;
2. tie-break lower dev history corruption;
3. tie-break lexicographic method name.

Freeze the selected comparator before formal testing.

Report:
- paired risk difference;
- 95% master-session cluster-bootstrap CI;
- discordant counts;
- exact McNemar test;
- Wilson intervals for per-method rates.

## Scaling claim

Estimate degradation over checkpoints `0,1,2,4` or `0,1,2,4,8`.

Preferred:
- mixed-effects logistic model with method × `log2(K+1)`;
- random intercepts for master session and task.

If convergence fails:
- paired cluster-bootstrap slope difference;
- record the fallback; do not switch based on desired significance.

## CoPE vs generic persistent control

Preregister non-inferiority margin:

`-0.05` absolute success probability.

Use a one-sided 95% paired bootstrap CI.

If non-inferior, compare token cost, invalid transaction rate, and latency. Do not claim semantic superiority if the confidence interval does not support it.

## Multiple testing

Use Holm correction for prespecified secondary pairwise tests. Keep primary test unadjusted because it is singular and preregistered.

Do not treat multiple events inside one trajectory as independent samples.

---

# 18. Claim-decision gates

Runtime claim is `GO` only if all hold:

1. Protocol B checkpoint-4 CoPE success exceeds the frozen primary non-persistent comparator by at least 0.10 absolute.
2. The lower bound of the paired 95% CI is above 0.
3. CoPE's degradation slope is flatter in the preregistered analysis.
4. CoPE history corruption and completed-step regression are each at most half those of the frozen comparator.
5. Planning-problem fidelity is higher before the corresponding execution improvement.
6. CoPE is non-inferior to generic persistent edit within the -0.05 margin.
7. CoPE does not receive more hidden information or more event-level reasoner calls.

Possible decisions:
- `GO`
- `PARTIAL_SUPPORT`
- `NO_GO`
- `INVALID_RUN`
- `BLOCKED_*`

If CoPE only saves tokens but does not improve execution, the runtime claim is `NO_GO` or `PARTIAL_SUPPORT`, not `GO`.

---

# 19. Durable execution and run integrity

Implement intent → response → result journaling generalized to:
- protocols A/B;
- events 1–8;
- all methods;
- all master sessions.

Every high-level call has a unique idempotency key:

```text
protocol/master_episode_id/method/event_index
```

Formal policy:
- zero semantic retries;
- ambiguous interrupted provider calls are not automatically repeated;
- credentials never written to disk;
- completed event cells never duplicated;
- simulator/event-boundary snapshots are atomic;
- resume only from a verified event-boundary snapshot;
- missing, duplicate, or unexpected cells invalidate analysis;
- no result deletion.

Before the first formal call, freeze and record:
- git SHA;
- config hash;
- task catalog hash;
- manifest hash;
- prompt hashes;
- schema hashes;
- provider/model ID;
- VLA checkpoint hash;
- detector/verifier version;
- compiler/backend version.

After the first formal call, any hash drift must stop the run with `INVALID_PROTOCOL_DRIFT`.

---

# 20. Output artifacts

For each formal protocol directory write:

```text
00_RUN_METADATA.json
01_CONFIG_FROZEN.yaml
02_TASK_CATALOG_FROZEN.json
03_MANIFEST_FROZEN.jsonl
04_CALL_INTENTS.jsonl
05_PROVIDER_RESPONSES.jsonl
06_EVENT_RESULTS.jsonl
07_EPISODE_RESULTS.jsonl
08_STATE_SNAPSHOTS.jsonl
09_PLANNING_PROBLEMS.jsonl
10_ACTION_TRACES/
11_CONDITION_KEY.csv
12_STATUS.json
13_INFRASTRUCTURE_STOP.json        # only if blocked/stopped
```

Analysis output:

```text
analysis/integrity_report.json
analysis/summary_by_method.csv
analysis/summary_by_checkpoint.csv
analysis/summary_by_task.csv
analysis/planning_fidelity.csv
analysis/history_corruption.csv
analysis/paired_tests.csv
analysis/noninferiority.csv
analysis/degradation_slopes.csv
analysis/failure_taxonomy.csv
analysis/latency_breakdown.csv
analysis/paper_table.tex
analysis/degradation_curve.pdf
analysis/REPORT.md
analysis/CLAIM_DECISION.md
```

Use stable canonical JSON and SHA256.

---

# 21. Preflight

The preflight must make zero provider calls and zero formal VLA calls.

It must verify:

- task catalog has at least eight eligible tasks;
- calibration/formal seeds are disjoint;
- exact expected master sessions, method trajectories, and event cells;
- every schedule has legal event ordering and required family coverage;
- prefix checkpoints are valid;
- occurrence IDs are unique and deterministic;
- reissue creates a fresh occurrence;
- generic and CoPE inputs have normalized semantic information parity;
- no hidden cause/operator/method/condition leakage in prompts;
- every output schema parses oracle fixtures;
- the pure compiler cannot access hidden state;
- event injection changes world/canonical state but not arm state;
- fresh observation follows injection;
- no policy step is consumed silently;
- the dynamic evaluator handles goal replacement/cancellation/reissue;
- wrong occurrence and stale restore negative fixtures fail;
- rejected patches preserve the prior committed state;
- journal resume does not duplicate calls/results;
- statistics and GO/NO-GO fixtures behave correctly;
- formal provider and VLA gates reject fake/mock/scripted/oracle adapters.

Optional `--with-env-smoke` may reset each selected LIBERO task and test event feasibility without any model call.

---

# 22. Required tests

At minimum implement tests for:

```text
schema round-trip and canonical hashes
lifecycle / validity / satisfaction separation
occurrence allocation and reissue
event dependency ordering
semantic trigger windows
physical feasibility guards
task catalog completeness
event evidence vs hidden-cause separation
prompt leakage
CoPE parser and kernel
generic transaction parser and engine
full-state materialization
full-history planning directive
RAG public-history-only index
summary memory update
skill-local scope
classical monitor
information parity
protected projection preservation
wrong occurrence
stale restore
authority violation
edge-type-specific cycles
atomic rejection
history monotonicity
compiler purity
dynamic evaluator
completed-step regression
history corruption
action-trace occurrence binding
journal at-most-once behavior
event-boundary resume
missing/duplicate cell rejection
paired statistics
non-inferiority
degradation slope
claim-decision fixtures
mocked common planner
mocked VLA integration
formal gate rejection of oracle/fake policy
```

Run:

```bash
python -m pytest -q
python -m pytest -q tests/repeated_v2
```

Do not weaken unrelated existing tests.

---

# 23. Commands to implement

```bash
# Audit and calibration
python tools/calibrate_repeated_v2_tasks.py \
  --config configs/repeated_interruptions_v2_formal.yaml \
  --output-dir outputs/repeated_v2_calibration

python tools/build_repeated_v2_task_catalog.py \
  --config configs/repeated_interruptions_v2_formal.yaml \
  --calibration-dir outputs/repeated_v2_calibration \
  --output task_catalogs/repeated_v2.json

# Manifest
python tools/build_repeated_interruptions_v2_manifest.py \
  --config configs/repeated_interruptions_v2_formal.yaml \
  --task-catalog task_catalogs/repeated_v2.json \
  --output manifests/repeated_interruptions_v2.jsonl

# Zero-call validation
python tools/validate_repeated_interruptions_v2.py \
  --config configs/repeated_interruptions_v2_formal.yaml \
  --task-catalog task_catalogs/repeated_v2.json \
  --manifest manifests/repeated_interruptions_v2.jsonl \
  --output-dir outputs/repeated_v2_preflight

# Pilot
python experiments/repeated_interruptions_v2.py \
  --phase pilot \
  --protocol controlled \
  --config configs/repeated_interruptions_v2_pilot.yaml \
  --output-dir outputs/repeated_v2_pilot_controlled

python experiments/repeated_interruptions_v2.py \
  --phase pilot \
  --protocol end_to_end \
  --config configs/repeated_interruptions_v2_pilot.yaml \
  --output-dir outputs/repeated_v2_pilot_vla

# Freeze
python tools/freeze_repeated_interruptions_v2.py \
  --config configs/repeated_interruptions_v2_formal.yaml \
  --task-catalog task_catalogs/repeated_v2.json \
  --manifest manifests/repeated_interruptions_v2.jsonl \
  --output-dir frozen/repeated_interruptions_v2

# Formal sharded runs
bash scripts/run_repeated_interruptions_v2.sh controlled 8
bash scripts/run_repeated_interruptions_v2.sh end_to_end 8

# Analysis
python tools/analyze_repeated_interruptions_v2.py \
  --controlled-run outputs/repeated_v2_formal_controlled \
  --end-to-end-run outputs/repeated_v2_formal_vla \
  --output-dir outputs/repeated_v2_analysis
```

Scripts must support `CUDA_VISIBLE_DEVICES`, deterministic manifest sharding, resume, and no duplicate ownership.

---

# 24. Implementation order

Perform these phases in order.

## Phase 1 — Audit and contracts
- read existing v1 and repair-backend code;
- write protocol docs;
- implement schemas, task catalog, events, scheduler, canonical state, manifest, and preflight;
- no provider calls.

## Phase 2 — Method implementations
- implement all adapters, prompts, parsers, state engines, parity/leakage tests;
- implement pure compiler and controlled backend;
- run all unit tests.

## Phase 3 — VLA and runner
- implement plugin VLA interface;
- bind an existing production VLA client if present;
- integrate continuation backend behind a neutral interface;
- implement dynamic evaluator, event-boundary snapshots, durable runner;
- run simulator smoke and pilot.

## Phase 4 — Freeze and formal readiness
- freeze hashes;
- generate exact call/trajectory counts;
- create clean commit;
- only then run formal protocols if dependencies exist.

## Phase 5 — Analysis
- integrity checks first;
- statistics;
- plots/tables;
- claim decision;
- no post-hoc case deletion.

---

# 25. Final response required from Codex

Report:

```text
branch and commit SHA
files added/modified
v1 regression-test status
new test status
task calibration status
eligible/frozen task IDs
task-catalog SHA
manifest SHA
prompt/schema/config hashes
preflight expected counts
provider/VLA/backend identities
pilot status
formal controlled status
formal VLA status
missing/duplicate/unexpected cells
primary result table, if formal run completed
CoPE vs frozen primary comparator
CoPE vs generic non-inferiority
degradation slopes
history corruption and completed-step regression
token and latency breakdown
GO/PARTIAL/NO-GO/INVALID/BLOCKED decision
paper-safe claims
forbidden claims
all artifact paths
```

If formal dependencies are unavailable, state exactly what remains blocked and why. Do not generate synthetic “formal” result rows.

Start now.
