# Task-6 relational protocol gate result

Date: 2026-08-04 (Asia/Shanghai)

## Decision

Phase A of `91_TASK6_RELATIONAL_DEVELOPMENT_PREREG.md` passes. The task-6
state-0 CPU canary is authorized after this result and its implementation are
committed. No task-6 initial state was opened during Phase A.

## Implemented protocol change

The new relational sequence module binds stable commitment identity to the
full atom `(predicate, object, target)`:

- `goal:on:red_coffee_mug_1:living_room_table_plate_right_region`;
- `goal:on:red_coffee_mug_1:living_room_table_plate_left_region`.

The target-only change remains a standard `Override`; no task-specific
`Retarget` operation was added. The second event must target the active
event-1 commitment ID. Historical commitment rows and typed-slot lineage are
retained through both overrides.

The oracle controller now exposes an explicit relational predicate at
`pick_and_place` and `place_held`, normalized to lowercase and forwarded to
the LIBERO evaluator. The default remains `in`, preserving all historical
callers. An empty predicate fails closed before evaluator use.

## Frozen implementation hashes

| File | SHA-256 |
|---|---|
| `cope/relational_sequential_semantics.py` | `c8a5b3755a4b15b237cf8d82c30a948cd946132cccb05722abec4611695a3614` |
| `cope_benchmark/oracle_skill_controller.py` | `6dba076b264d2e04a8bd56b6f5c5babfa50e3e4d2cd0b041395f97c242e2e65b` |
| `tests/test_relational_sequential_semantics.py` | `5f77112cbd32daf217434904348da9d5456453a3e9fff097db0ba44fb4d4b11a` |
| `tests/test_oracle_skill_controller.py` | `cfe74a4a6b3f768db3b112f4545c8adf8e774a2b6ebd64658e1daa85d72d01ab` |

## Test evidence

- focused relational semantics plus controller: **23/23 passed** in 0.19s;
- full repository regression: **553/553 passed** in 49.14s;
- `git diff --check`: pass.

The focused suite demonstrates:

- same object/different target produces distinct stable IDs;
- two overrides preserve both logical history and typed lineage;
- event 1 compiles red-mug/right and event 2 compiles exactly
  `place_on(red_coffee_mug_1, living_room_table_plate_left_region)`;
- the cancellation sibling compiles to `HALT` and preserves completed
  progress;
- wrong chain tip, stale version, wrong replacement ID, old-event replay,
  unknown/unlicensed atom, predicate mismatch, and absent physical witness all
  fail closed;
- explicit `On` is normalized and forwarded as `on`;
- the historical no-keyword controller path still evaluates `in`.

## Evidence boundary

This is deterministic unit/protocol evidence only. It does not show that the
task-6 geometry is executable, that LIBERO's `on` relation becomes true after
the controller release, or that a learned provider can generate the sequence.
Those questions begin with the one-cell canary. States 10--49 remain unopened.

