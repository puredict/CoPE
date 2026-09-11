# v2.1 gap summary

The retained v2 preflight expanded **794 derived rows** from **127 root-cause units**. This rebuild operates on the root causes and never treats cascade rows as separate manual tasks.

The v2.1 source-backed catalog has **zero mandatory schema/evidence completeness gaps**. All **127 prior root-cause units** are accounted for in `GAP_MATRIX.csv`, including their **794 derived symptoms** and closure status. There are **12 measured task-level scientific eligibility failures** after catalog closure; these are grouped by task, category, required evidence, and blocking gate in `GAP_MATRIX_V2_1.csv`.

## Remaining root causes by category

- `calibration`: 3
- `schedule_coverage`: 6
- `structural_and_milestones`: 3

## Cascade handling

State-digest, trigger-field, feasibility, calibration-identity, and collection-marker cascades were regenerated from one upstream artifact per category. A missing or failed upstream certificate remains one root cause even when it affects several derived task/event/state cells. No task-catalog entry was invented to erase a failed measurement.

## Root causes grouped by task

### Task 0

| Category | Root cause | Automatic fixability | Required evidence | Blocking gate |
| --- | --- | --- | --- | --- |
| structural_and_milestones | `safe_changeable_grounding` | REQUIRES_NEW_MEASURED_EVIDENCE | additional source-grounded and observed structural witness | `task_eligibility` |
| schedule_coverage | `UNSUPPORTED_REGISTERED_EIGHT_EVENT_TEMPLATE` | REQUIRES_NEW_MEASURED_EVIDENCE | task-local support for both temporary lifecycles, preference, reissue, one grounding event, and one retirement event | `task_eligibility;manifest_schedule` |
### Task 1

| Category | Root cause | Automatic fixability | Required evidence | Blocking gate |
| --- | --- | --- | --- | --- |
| None | None | None | All mandatory source-backed evidence is present. | None |
### Task 2

| Category | Root cause | Automatic fixability | Required evidence | Blocking gate |
| --- | --- | --- | --- | --- |
| schedule_coverage | `UNSUPPORTED_REGISTERED_EIGHT_EVENT_TEMPLATE` | REQUIRES_NEW_MEASURED_EVIDENCE | task-local support for both temporary lifecycles, preference, reissue, one grounding event, and one retirement event | `task_eligibility;manifest_schedule` |
### Task 3

| Category | Root cause | Automatic fixability | Required evidence | Blocking gate |
| --- | --- | --- | --- | --- |
| calibration | `CLEAN_SUCCESS_RATE_OUTSIDE_FROZEN_INTERVAL` | REQUIRES_NEW_MEASURED_EVIDENCE | measured clean success within the unchanged inclusive [0.40,0.95] interval | `task_eligibility` |
| schedule_coverage | `UNSUPPORTED_REGISTERED_EIGHT_EVENT_TEMPLATE` | REQUIRES_NEW_MEASURED_EVIDENCE | task-local support for both temporary lifecycles, preference, reissue, one grounding event, and one retirement event | `task_eligibility;manifest_schedule` |
### Task 4

| Category | Root cause | Automatic fixability | Required evidence | Blocking gate |
| --- | --- | --- | --- | --- |
| None | None | None | All mandatory source-backed evidence is present. | None |
### Task 5

| Category | Root cause | Automatic fixability | Required evidence | Blocking gate |
| --- | --- | --- | --- | --- |
| structural_and_milestones | `two_independently_verifiable_milestones` | REQUIRES_NEW_MEASURED_EVIDENCE | additional source-grounded and observed structural witness | `task_eligibility` |
| structural_and_milestones | `completed_milestone_preservable` | REQUIRES_NEW_MEASURED_EVIDENCE | additional source-grounded and observed structural witness | `task_eligibility` |
| schedule_coverage | `UNSUPPORTED_REGISTERED_EIGHT_EVENT_TEMPLATE` | REQUIRES_NEW_MEASURED_EVIDENCE | task-local support for both temporary lifecycles, preference, reissue, one grounding event, and one retirement event | `task_eligibility;manifest_schedule` |
### Task 6

| Category | Root cause | Automatic fixability | Required evidence | Blocking gate |
| --- | --- | --- | --- | --- |
| None | None | None | All mandatory source-backed evidence is present. | None |
### Task 7

| Category | Root cause | Automatic fixability | Required evidence | Blocking gate |
| --- | --- | --- | --- | --- |
| None | None | None | All mandatory source-backed evidence is present. | None |
### Task 8

| Category | Root cause | Automatic fixability | Required evidence | Blocking gate |
| --- | --- | --- | --- | --- |
| calibration | `HORIZON_UNESTIMABLE` | REQUIRES_NEW_MEASURED_EVIDENCE | additional preregistered unique calibration states with successful trajectories | `clean_horizon_and_task_eligibility` |
| schedule_coverage | `UNSUPPORTED_REGISTERED_EIGHT_EVENT_TEMPLATE` | REQUIRES_NEW_MEASURED_EVIDENCE | task-local support for both temporary lifecycles, preference, reissue, one grounding event, and one retirement event | `task_eligibility;manifest_schedule` |
### Task 9

| Category | Root cause | Automatic fixability | Required evidence | Blocking gate |
| --- | --- | --- | --- | --- |
| calibration | `CLEAN_SUCCESS_RATE_OUTSIDE_FROZEN_INTERVAL` | REQUIRES_NEW_MEASURED_EVIDENCE | measured clean success within the unchanged inclusive [0.40,0.95] interval | `task_eligibility` |
| schedule_coverage | `UNSUPPORTED_REGISTERED_EIGHT_EVENT_TEMPLATE` | REQUIRES_NEW_MEASURED_EVIDENCE | task-local support for both temporary lifecycles, preference, reissue, one grounding event, and one retirement event | `task_eligibility;manifest_schedule` |

## Eligibility

- Eligible task IDs: [1, 4, 6, 7]
- Eligible task count: 4
- Selection status: `BLOCKED_INSUFFICIENT_ELIGIBLE_TASKS`
- Formal launch minimum: 8 tasks
