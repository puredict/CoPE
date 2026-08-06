# Task-6 state-0 v1 failure and controller-defect amendment

Frozen: 2026-08-04 (Asia/Shanghai), after retaining v1 and before any retry.

## V1 result

The preregistered state-0 canary failed and stopped before the sequence branch:

- grasp acquired: true;
- object lift: 0.211170135 m;
- `on(porcelain_mug_1, plate_1)` after release/settle: false on 5/5
  consecutive checks;
- failure: `prefix_only:target_predicate_false`;
- controller actions: 222;
- provider calls: 0;
- task-6 development states opened: state 0 only;
- task-6 states 1--49 opened: none;
- task-1 state 33 retried: no;
- task-1 states 34--49 indexed: no.

The create-only failure directory is
`research/task6_relational_development_2026-08-04/state0_canary_v1`.
Its result and journal remain primary evidence and must not be overwritten or
excluded from the development narrative.

## Root-cause classification

This is classified as a task-independent controller implementation defect,
not evidence that task 6 is geometrically impossible.

The Phase-A change correctly forwarded the explicit `on` predicate, but motion
remained the historical insertion controller:

1. it descended to the target geometry origin plus the fixed
   `release_offset_m=0.10`;
2. it opened without establishing contact;
3. it reused an early-return rule intended for narrow `in` regions, which can
   report success while the object is still grasped.

LIBERO source inspection shows two different `On` contracts:

- object target such as `plate_1`: target contact, target below the moving
  object, and XY center distance below 0.03 m;
- site target such as left/right table region: the moving-object center must be
  above and within the region, with support/contact supplied by the parent
  object when present.

Predicate forwarding alone therefore did not qualify an `on` controller.

## Frozen v2 correction

Add a separate, bounded `OnPlacementConfig`; do not change the historical
`OracleSkillConfig` fields or hash. For explicit `predicate="on"` only:

1. retain the existing grasp, lift, and transfer-to-target XY protocol;
2. keep the gripper closed and descend in bounded increments;
3. stop descent at the first true requested `on` predicate;
4. cap total descent and enforce a minimum end-effector height above the target
   geometry origin;
5. fail closed if contact predicate is not established inside the bound;
6. after first establishment, open, retreat, settle, and require the same `on`
   predicate to remain true;
7. never use the historical still-grasped early-success path for `on`;
8. retain the old code path byte-behavior-compatible for default `in` calls.

The new parameters and their stable hash must be recorded before physical
development. Unit tests must cover on-contact establishment, failure at the
descent bound, release-before-success, and unchanged `in` behavior.

## Non-task6 development gate

Do not tune on task 6. Develop and freeze the generic `on` controller on the
already exposed LIBERO-10 task 4, state 0 only:

- object: `porcelain_mug_1`;
- target: `plate_1`;
- success: placement result true plus five consecutive
  `on(porcelain_mug_1, plate_1)=true` checks;
- provider/GPU use: none;
- no parameter search inside the assigned run;
- retain the first assigned result.

If this task-4 gate fails, task 6 is disqualified and v2 is not run. A new
parameter search would require a new amendment and a distinct development
identity.

## Single authorized task6 retry

Only after focused tests, full regression, and the task-4 state-0 gate pass,
run the unchanged task-6 canary once more on state 0 in a new create-only
`state0_canary_v2` directory. This is the only retry authorized by this
amendment.

- If v2 passes, states 1--9 still require a separate promotion decision; no
  automatic expansion is authorized.
- If v2 fails at either prefix or terminal placement, task 6 is disqualified
  for the current paper and states 1--49 remain unopened.

The v1 failure remains part of the evidence regardless of v2 outcome.

