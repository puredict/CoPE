# Data and Method Contracts

## 1. Record boundaries

Never merge the following records:

- `PublicEventPayload`: what an agent may observe.
- `HiddenCanonicalEffect`: scoring-only truth.
- `MethodProposal`: raw model or rule output.
- `AcceptedMethodState`: post-validation state.
- `CompiledPlanningProblem`: pure translation of accepted state.
- `ExecutionTrace`: common backend behavior.
- `SealedEvaluation`: independent outcome.

This separation is the main anti-leakage mechanism.

## 2. Commitment occurrence

Required fields:

```text
family_key
occurrence_id
role
predicate
arguments
lifecycle
priority
hardness
source
authority
grounding_validity
restore_guard
dependency_ids
provenance
evidence_ids
created_event_id
retired_event_id
```

The same predicate may have multiple occurrence IDs.

## 3. Progress certificate

```text
milestone_id
predicate
arguments
verified_at_step
verifier_record_id
evidence_ids
affected_by_event_ids
currently_preserved
```

A completed milestone is scored for regression only when no later event legitimately invalidated it.

## 4. Continuation

```text
active_stage
active_skill
program_counter
held_object_hypothesis
resumable_suffix
controller_state_ref
captured_at_step
```

## 5. Planning problem

```text
problem_id
source_method
source_revision
initial_facts
active_goal_occurrence_ids
remaining_goals
hard_constraints
soft_preferences
forbidden_regressions
grounding_bindings
restore_eligibility
progress_certificates
continuation_assumptions
```

It must be hashable after canonical normalization.

## 6. CoPE proposal

The editor emits:
- affected scope;
- protected projection hash;
- evidence references;
- validation checks;
- typed mutations;
- confidence.

The kernel, not the model, assigns final occurrence IDs.

## 7. Generic persistent proposal

The generic arm receives the same normalized facts but uses:
- assertions;
- creates;
- path writes;
- relation updates;
- evidence links.

Its output must not contain CoPE operator names.

## 8. Regeneration proposal

The full-state arm regenerates all semantically relevant occurrences and state fields, not raw immutable audit-log bytes.

## 9. Replanning proposal

The full-history/RAG/summary/skill arms emit the same normalized planning-directive schema so that the common executor can consume them.

## 10. Pure compiler rule

The compiler may:
- normalize names;
- map accepted commitments to planner-specific fields;
- serialize a VLA instruction;
- topologically order already-present dependencies.

The compiler may not:
- add a missing goal;
- select the correct occurrence using task ID;
- infer an omitted preference;
- retrieve hidden simulator facts;
- repair a stale or invalid restore;
- replace a baseline state with canonical truth.

## 11. Failure accumulation

If an arm corrupts its state at event 2, event 3 uses that corrupted accepted state. The only exception is a formally rejected transaction, which leaves the previous accepted state unchanged. No oracle reset is allowed.

## 12. Controlled vs learned execution

`controlled_mechanism` results may support representation-to-plan reasoning only.

`end_to_end` results require a learned, non-privileged VLA adapter. The two must never be pooled under one success rate.
