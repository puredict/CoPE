# Task-9 fresh identity static audit

Frozen: 2026-08-04 (Asia/Shanghai), before opening any LIBERO-10 task-9
initial state.

## Decision

Provisionally select LIBERO-10 task 9,
`KITCHEN_SCENE6_put_the_yellow_and_white_mug_in_the_microwave_and_close_it`,
for a one-cell development canary of cross-predicate commitment replacement.

This supersedes task 6 as the fresh physical candidate. Task 6 remains stopped
after its retained v1 failure and the independent task-4 `on` controller gate
failure.

## Static exposure evidence

At repository HEAD `09361a0fcd4ad2ea6c3e6c5f4c422d0d3bf92b3d`, exact fixed-string searches over
`research/`, `manifests/`, `configs/`, `cope_benchmark/`, `tests/`, `scripts/`,
and `experiments/` found zero files containing either:

- `microwave_1_heating_region`;
- the full task-9 BDDL task name.

The BDDL was read without opening an init state. Its SHA-256 is
`456d145f92be049f445fc77673dc583d9d17ea7afe92f6ffcb2fd1fa5565d420`.

Task 5 was rejected as a fresh alternative because its book/caddy back/front
geometry already appears in multiple retained state-0 target-geometry logs.
Task 3 requires an unqualified articulated-drawer close executor. Task 9 uses
the already validated `in` predicate for its physical prefix and exposes the
unary `close` commitment only at the semantic layer.

## Cross-predicate sequence

Initial commitments after the physical prefix:

- satisfied:
  `in(white_yellow_mug_1, microwave_1_heating_region)`;
- active pending: `close(microwave_1)`.

Dependent interruption sequence:

1. `Override` the unary close commitment with the binary commitment
   `in(porcelain_mug_1, microwave_1_heating_region)`;
2. `Expire` that newly active porcelain-mug commitment before execution.

The final directive is `HALT`. Event 2 must target the event-1 replacement ID,
not the retired close ID. The already completed yellow-mug placement must
remain satisfied and physically true.

This does not require a new operation opcode. It tests whether persistent
commitment identity and lineage remain valid when an override changes predicate
arity and argument types.

## Limitation

The scene has no third unused object/target that supports a clean second
replacement under the qualified `in` controller. Therefore task 9 contributes
only `replace_then_cancel`, not a matched `replace_then_replace` sibling. It
cannot replace the task-0 formal design; it is an external-validity canary.

