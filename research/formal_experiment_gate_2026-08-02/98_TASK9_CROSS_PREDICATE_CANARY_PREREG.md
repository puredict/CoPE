# Task-9 cross-predicate state-0 canary preregistration

Frozen: 2026-08-04 (Asia/Shanghai), before opening any LIBERO-10 task-9
initial state.

## Evidence class

Development-only oracle substrate and semantic protocol canary. No learned
provider, comparison arm, or confirmatory claim is authorized.

## State split

- authorized canary: task 9 state 0 only;
- development reserve: task 9 states 1--9;
- provisional formal reserve: task 9 states 10--29;
- untouched holdout: task 9 states 30--49.

This document authorizes only state 0. A pass does not automatically authorize
states 1--9. Existing task-1 and task-6 locks remain unchanged.

## Phase A semantic gate

Before simulator use, a generic commitment atom must support one or more
arguments and derive a stable ID from the exact predicate plus ordered
arguments.

Required sequence:

1. initialize a satisfied two-argument `in` commitment and active one-argument
   `close` commitment;
2. event 1 overrides `close(microwave_1)` with
   `in(porcelain_mug_1, microwave_1_heating_region)`;
3. event 2 expires the event-1 chain tip;
4. event 1 compiles exactly to
   `place_in(porcelain_mug_1, microwave_1_heating_region)`;
5. event 2 compiles exactly to `HALT`;
6. typed lineage, logical history, state versions, receipt hashes, and the
   completed yellow-mug progress row remain continuous;
7. wrong arity, unknown predicate/argument, wrong chain tip, stale version,
   old-event replay, duplicate stable ID, and absent physical done witness fail
   closed;
8. focused and full regression pass.

The task-6 relational module is not silently repurposed. Use a versioned generic
atom module so the arity change is explicit and testable.

## Phase B physical prefix canary

Run CPU-only with `CUDA_VISIBLE_DEVICES=""` on task 9 state 0:

1. reset from the assigned init state;
2. verify microwave is open and both mug-in-heating predicates are false;
3. use the unchanged qualified `in` controller to place
   `white_yellow_mug_1` in `microwave_1_heating_region`;
4. release/open the gripper and require five consecutive checks with:
   - yellow mug in heating region = true;
   - porcelain mug in heating region = false;
   - microwave close = false;
5. build and apply both oracle semantic events without any controller action;
6. require final directive `HALT`, controller action-count equality across both
   semantic transitions, completed predicate still true, and no post-event
   placement action;
7. record init, action, simulator, logical-state, receipt, BDDL, runtime, and
   controller hashes.

## Frozen decision rule

Pass only if every Phase-A unit gate and every Phase-B condition holds on the
first assigned run. If the physical prefix fails, stop task 9 and do not tune
on states 1--9. If a task-independent manifest/code defect occurs, retain the
failure and require an explicit versioned amendment before a state-0 retry.

Even a pass supports only feasibility of cross-arity commitment history on one
oracle-executed state. It does not support learned semantic competence,
baseline superiority, multi-task replication, or publication readiness.

