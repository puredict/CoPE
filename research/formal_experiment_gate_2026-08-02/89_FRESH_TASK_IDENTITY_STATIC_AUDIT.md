# Fresh task-identity static audit

Frozen: 2026-08-04 (Asia/Shanghai), before opening any LIBERO-10 task-6
initial state.

## Decision

Provisionally select LIBERO-10 task 6,
`LIVING_ROOM_SCENE6_put_the_white_mug_on_the_plate_and_put_the_chocolate_pudding_to_the_right_of_the_plate`,
for a development-only relational commitment sequence.

This is not yet a qualified physical task and is not confirmatory evidence.
Qualification is allowed only on development states 0--9 under the separate
preregistration in `91_TASK6_RELATIONAL_DEVELOPMENT_PREREG.md`.

## Static non-exposure audit

At repository HEAD `2a501bbf8d04f581bc055d1f28f53570eac090ee`, exact fixed-string searches over
`research/`, `manifests/`, `configs/`, `cope_benchmark/`, `tests/`, and
`scripts/` returned zero files containing any of:

- `chocolate_pudding_1`;
- `living_room_table_plate_right_region`;
- the full task-6 BDDL task name.

An exact search for serialized `task_id=6` found only
`configs/libero_spatial_target_joints.yaml`. That row belongs to the different
LIBERO-Spatial suite and describes a black-bowl task. It is neither evidence
for nor exposure of LIBERO-10 task 6. Suite identity is therefore mandatory in
all subsequent manifests.

The task-6 BDDL was read without loading an initial state. Its SHA-256 is
`dbc9464b424cdc9b771b92d0b8a8c185b1b539f6a4133b323dc858bcf8f6a9c2`.
It contains:

- original satisfied-prefix candidate: `On(porcelain_mug_1, plate_1)`;
- original pending commitment: `On(chocolate_pudding_1,
  living_room_table_plate_right_region)`;
- spare object: `red_coffee_mug_1`;
- unused task region: `living_room_table_plate_left_region`.

No task-6 init-state file was opened, hashed, counted, or indexed during this
audit.

## Proposed dependent sequence

Let a commitment identity bind the full atom `(predicate, object, target)`, not
only the object.

1. Preserve the physically witnessed commitment
   `On(porcelain_mug_1, plate_1)`.
2. Event 1 overrides `On(chocolate_pudding_1, right_region)` with
   `On(red_coffee_mug_1, right_region)`.
3. Event 2 either:
   - cancels the active red-mug/right commitment; or
   - overrides it with `On(red_coffee_mug_1, left_region)`.

The second branch changes the target while keeping the object fixed. It is a
strictly stronger interface test than the existing basket sequences, whose
replacements changed only the object while retaining one receptacle.

No new operation opcode is introduced. Both object replacement and target
change are `Override` operations whose replacement commitment has a new stable
full-atom ID. This keeps the method claim about editing persistent
commitments, not proliferating task-specific verbs.

## Known blockers before physical use

The frozen oracle controller currently evaluates only
`in(object, target_region)` inside `pick_and_place` and `place_held`. Task 6
uses BDDL `On`. Reusing the current controller without a predicate parameter
would be a protocol error even if the geometry happened to look correct.

Therefore physical qualification is blocked until all of the following hold:

1. the controller accepts an explicit predicate and preserves `in` as the
   backwards-compatible default;
2. focused tests prove the requested predicate, rather than hard-coded `in`,
   is sent to the LIBERO evaluator;
3. semantic state and physical witness use full predicate atoms;
4. a development state passes both the completed-prefix stability check and
   the final compiled action check under `on`;
5. every failure and opened development state is retained.

## Claim boundary

Passing the development gate would establish only that task 6 is a feasible
new substrate for relational target-edit experiments. It would not establish
learned recovery, task-identity replication, superiority over baselines, or a
confirmatory result. States 10--29 remain unopened until a separately frozen
formal design and all provider gates pass; states 30--49 remain untouched.

