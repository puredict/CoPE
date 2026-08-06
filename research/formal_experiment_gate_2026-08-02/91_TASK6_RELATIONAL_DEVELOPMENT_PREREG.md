# Task-6 relational commitment development preregistration

Frozen: 2026-08-04 (Asia/Shanghai), before opening any LIBERO-10 task-6
initial state.

## Purpose and evidence class

This is a development-only substrate qualification. It tests whether a new
LIBERO-10 identity can physically support a completed `on` prefix and the
terminal action compiled from a same-object target override.

It is not a learned-provider experiment, confirmatory comparison, or paper
success result. Development outcomes may determine whether a later formal
experiment is worth preregistering, but they may not be pooled into that later
experiment.

## Frozen state split

- development: task 6, states 0--9;
- provisional formal reserve: task 6, states 10--29;
- untouched holdout: task 6, states 30--49.

Only states 0--9 are authorized by this document. Open states sequentially and
stop as soon as a gate is impossible or a protocol defect is found. Retain a
ledger row for every attempted or opened state. Do not inspect reserve states
to choose controller parameters.

Existing locks remain unchanged:

- never retry LIBERO-10 task 1 state 33;
- never index LIBERO-10 task 1 states 34--49;
- do not spend any existing formal reserve merely to debug task 6.

## Frozen semantic atoms and sequence

Use lowercase predicate symbols at the evaluator boundary:

- done atom `on(porcelain_mug_1, plate_1)`;
- original pending atom
  `on(chocolate_pudding_1, living_room_table_plate_right_region)`;
- event-1 replacement atom
  `on(red_coffee_mug_1, living_room_table_plate_right_region)`;
- event-2 retarget atom
  `on(red_coffee_mug_1, living_room_table_plate_left_region)`.

Stable commitment IDs include predicate, object, and target. Event 2 must
target the event-1 replacement ID, not the original pudding ID. The final
compiled directive is exactly:

`place_on(red_coffee_mug_1, living_room_table_plate_left_region)`

The sibling branch replaces event 2 with cancellation and must compile to
`HALT`. The completed porcelain-mug commitment and its progress ledger entry
must remain unchanged in both branches.

## Phase A: protocol unit gate

Before simulator use:

1. existing `in` callers remain byte-for-byte behavior compatible;
2. a fake evaluator observes `on` for an explicit `on` request;
3. relational stable IDs distinguish same-object/different-target atoms;
4. two overrides preserve both historical chain links;
5. stale base version, wrong chain tip, old event replay, unknown object/target,
   and predicate mismatch fail closed;
6. cancellation compiles to `HALT`, retarget compiles to the exact directive
   above;
7. full regression passes.

Any failure blocks Phase B.

## Phase B: state-0 one-cell canary

Run CPU-only with `CUDA_VISIBLE_DEVICES=""`. On state 0:

1. place `porcelain_mug_1` on `plate_1` with the explicit `on` predicate;
2. require five consecutive post-action checks with done=true and original
   pending=false;
3. reset the same assigned state from the frozen init;
4. recreate the prefix, apply the two oracle semantic events without provider
   calls, compile the final directive, and execute only the compiled final
   action;
5. require five consecutive checks with done=true,
   `on(red_coffee_mug_1, left_region)=true`, and all retired right-region goal
   atoms excluded from the current goal;
6. record controller phases, failure reason, step count, predicate snapshots,
   state hashes, receipt hashes, and exact reset provenance.

The cancellation sibling is semantic-only in this canary and must produce no
post-event controller action.

## Phase C: bounded development expansion

Only if state 0 passes exactly, expand to states 1--9 with identical code and
configuration. No result-dependent retuning is allowed inside the assigned
run.

Primary development gates:

- prefix feasibility: 10/10;
- retarget terminal action: 10/10;
- cancellation no-action: 10/10;
- receipt/history/version validation: 20/20 two-event sequences;
- reset/provenance completeness: 10/10;
- zero silent retries and zero provider calls.

If state 0 fails because of task-independent code or manifest defects, retain
the failed run, fix under a versioned amendment, rerun state 0 only, and do not
expand until the corrected canary passes. If physical geometry fails, the task
is not qualified; do not tune on states 1--9 to rescue it.

## Promotion rule

Even a 10/10 development pass does not authorize states 10--29. Promotion
requires a new formal preregistration with matched arms, provider prompt
contracts, call counts, seed/order schedule, exact statistical decision rule,
credential smoke, journal recovery, and a clean commit hash. If those gates do
not mature, the reserve remains unopened.

