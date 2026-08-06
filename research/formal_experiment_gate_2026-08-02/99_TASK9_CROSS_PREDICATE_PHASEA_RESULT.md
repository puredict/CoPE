# Task-9 cross-predicate Phase-A result

Date: 2026-08-04 (Asia/Shanghai)

## Decision

The semantic protocol gate in
`98_TASK9_CROSS_PREDICATE_CANARY_PREREG.md` passes. Task-9 state0 may be opened
only after this implementation and result are committed.

## Result

- focused variable-arity plus relational sequence tests: **23/23 passed** in
  0.18s;
- full repository regression: **565/565 passed** in 49.29s;
- `git diff --check`: pass;
- provider/GPU/simulator use: none;
- task-9 initial states opened: none.

Implementation hashes:

- `cope/arity_commitment_sequence.py`:
  `c6072d4322bef80ebc0bf7902be49eadbbc3cc92431fe28d81016c52152df3dd`;
- `tests/test_arity_commitment_sequence.py`:
  `949a08f0098ca35038da0ac7961dd77580a5afc829497e01480f40a2c2579e2c`.

## Demonstrated semantics

- unary ID: `goal:close:microwave_1`;
- binary replacement ID:
  `goal:in:porcelain_mug_1:microwave_1_heating_region`;
- event-1 directive:
  `place_in(porcelain_mug_1, microwave_1_heating_region)`;
- event-2 target: the event-1 replacement stable ID;
- event-2 directive: `HALT`;
- typed revision chain: 1 -> 2 -> 3;
- completed yellow-mug commitment and progress ledger preserved exactly.

Negative gates cover wrong predicate, argument, arity, target, version,
replacement ID, historical ID reuse, event replay, source-atom tampering, and
missing physical completion witness.

## Boundary

This is deterministic protocol evidence, not a learned or embodied result.
The one-cell physical canary must still establish that task9 state0 admits the
yellow-mug-in-microwave prefix under the unchanged `in` controller and that
both semantic transitions issue zero controller actions.

