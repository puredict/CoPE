# Generic on-controller task-4 failure and task-6 stop

Date: 2026-08-04 (Asia/Shanghai)

## Decision

The non-task6 development gate frozen in
`95_TASK6_STATE0_V1_FAILURE_AND_AMENDMENT.md` failed. Therefore:

- do not run task-6 state0 canary v2;
- disqualify LIBERO-10 task 6 as a physical identity for the current paper;
- do not open task-6 states 1--49;
- retain the task-6 full-atom semantics as protocol/unit evidence only;
- do not count either failed physical run as formal or confirmatory evidence.

## Retained task-4 result

Assigned cell: already exposed LIBERO-10 task 4, state 0,
`porcelain_mug_1 -> plate_1` with exact predicate `on`.

Result:

- placement: fail, `on_contact_not_established`;
- five stable post-checks: 0/5 true;
- action count: 212;
- task-6 states indexed: 0;
- provider/GPU use: none;
- first assigned run retained at
  `research/on_controller_development_2026-08-04/task4_state0_v1`.

The run used the frozen bounded contact descent:

- 0.005 m nominal descent increment;
- 0.10 m maximum descent;
- 0.02 m minimum EEF height above target origin;
- 0.15 translation action limit;
- configuration hash
  `1cb870a686ea52179eb4c72fe75e234fb1f860f1050b510ea25ca3261861438d`.

## New failure localization

The start and final geometry reveal that descent depth was not the primary
remaining issue.

- target plate center XY: `(-0.0044841, -0.3231965)`;
- final mug center XY: `(-0.0715125, -0.3573952)`;
- XY center error: approximately 0.075 m;
- LIBERO object-target `On` threshold: below 0.03 m plus contact.

The controller moves the end effector to target XY. It does not measure and
compensate the held object's actual transform relative to the end effector.
The state-0 grasp had a large lateral offset, so contact-directed vertical
motion could not satisfy the XY predicate. The object also ceased to be
grasped before success even though the controller issued no open-gripper
phase. Increasing the descent bound would not repair either defect.

## Scientific consequence

The task-6 relational idea remains semantically valid: a second `Override`
can change the target while preserving the object and full history. Its unit
gate passed and exposed an important identity assumption. But the physical
substrate is unqualified, so it cannot be used to support embodied or
cross-task claims now.

Any future generic `on` controller must:

1. estimate the held object-to-EEF translation after lift;
2. command target object-center XY, not target EEF XY;
3. monitor grasp retention during descent;
4. stop and recover safely if the object is lost;
5. qualify on a new, independently frozen development identity before any
   return to reserved task identities.

That work is separate infrastructure research and does not authorize another
task-6 retry under the present design.

## Locks preserved

- task-6 state0: one failed v1 run only;
- task-6 states 1--49: unopened;
- task-1 state33: not retried;
- task-1 states34--49: not indexed;
- learned provider calls: 0.

