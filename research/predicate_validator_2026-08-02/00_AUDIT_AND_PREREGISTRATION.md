# Task-1 simulator-predicate packet and validator preregistration

Date frozen: 2026-08-02 (Asia/Shanghai)

Parent commit: `e8fa0c59ee0fed36f23a382128f1d0c30439e91e`

## Interface audit before implementation

The current main backend sends only PNG bytes and image metadata in
`RecoveryInput.observation`. The production engine passes that observation to
the revalidation validator, so no existing non-fake adapter can evaluate the
task-1 `in(object, basket_region)` predicate. The current main engine also
initializes one instruction-valued `goal` slot instead of atomic predicate
slots. Config `cope_main_comparison_v1.yaml` points to the LIBERO-Spatial suite
and checkpoint, not the qualified LIBERO-10 task-1 tuple.

Reusable code does exist: `cope_benchmark.task_progress.LiberoStateView` calls
LIBERO's `_eval_predicate`, and its frozen task-1 definition names the cream
cheese and butter containment commitments. This is simulator-grounded scoring
code, not an always-true fixture.

## Frozen implementation boundary

Implement a disabled-by-default packet producer and a fail-closed validator.
The producer must evaluate the registered task commitment predicates from the
live LIBERO environment at the event step and bind them to event ID, RGB hash,
simulator-state hash, task ID, policy step, producer version/commit, and a
canonical packet hash. The validator may read only this observation packet and
the atomic slot; provider-supplied evidence is non-authoritative.

Production mode must reject test packets, missing or malformed hashes, wrong
events/tasks, duplicate predicates, non-atomic slots, unsupported predicates,
and packet-hash corruption. Test mode must advertise `metadata.is_fake=true`;
only production mode may advertise `is_fake=false`.

Backend integration is opt-in and must refuse to emit a snapshot unless
`predicate_snapshot` is in the frozen observation information budget. The
default spatial config must remain unchanged.

## Frozen replay cases

`01_REPLAY_CASES.csv` contains ten rows from already consumed task-1 development
states 0--4. Each source CSV is hash-pinned. At the post-lift event it records
cream cheese in the basket as true and the held alphabet soup in the basket as
false. The replay constructs an explicitly `test_only=true` summary packet;
it tests parsing/binding/decision logic, not live predicate production or
sensor authenticity.

## Decision rule

The CPU adapter preflight passes only if:

1. all 10 replay decisions match their recorded booleans after source-hash
   verification;
2. a fake environment proves the live producer calls `_eval_predicate` for the
   registered task-1 commitments;
3. corruption tests reject packet hash, event, observation hash, simulator
   hash, duplicate predicate, unsupported slot, and test packet in production;
4. test-mode validator metadata is fake and production-mode metadata is
   non-fake with a real 40-hex source commit;
5. backend integration is opt-in and information-budget guarded;
6. the full repository regression remains clean.

Passing closes only an adapter CPU contract. X03 remains PARTIAL until a clean
committed live backend emits and consumes production packets. X08 remains
PARTIAL until a separate semantic task-1 config pins the LIBERO-10 checkpoint,
BDDL, init-state file, event schema, and reserved-state manifest and is accepted
by a semantic runner. No state 25--49 may be inspected in this phase.

## No-retuning rule

Case sources, hashes, expected booleans, corruption classes, and claim boundary
may not be changed after results are observed. Defects require retained,
versioned superseding outputs.
