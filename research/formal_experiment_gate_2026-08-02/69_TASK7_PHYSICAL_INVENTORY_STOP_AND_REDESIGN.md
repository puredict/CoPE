# Task-7 physical inventory stop and formal-design correction

Date: 2026-08-04

## Stop finding

The sequential symbolic gate passed, but a read-only inventory of development
state 0 found that the proposed task-7 sequence referenced an object absent
from the MuJoCo scene:

- task 0 joints: `alphabet_soup_1`, `tomato_sauce_1`, `cream_cheese_1`,
  `butter_1`;
- task 7 joints: `alphabet_soup_1`, `cream_cheese_1`, `tomato_sauce_1`;
- therefore task-7 `replacement_d=butter_1` is physically impossible.

Only development state 0 was opened for this inventory.  No task-0/task-7
state 10--49 was accessed, no provider was called, task-1 state 33 was not
retried, and task-1 states 34--49 were not indexed.

The task-7 symbolic cells are valid interface tests but are disqualified as a
physical formal design.  They must not appear in the confirmatory manifest.

## Corrected design

Use task 0, whose scene contains all four objects, with two independently
reset prefix orientations:

1. A=`alphabet_soup_1`, B=`tomato_sauce_1`, C=`cream_cheese_1`,
   D=`butter_1`;
2. A=`tomato_sauce_1`, B=`alphabet_soup_1`, C=`cream_cheese_1`,
   D=`butter_1`.

Cross 20 formal states (10--29), two prefix orientations, and two dependent
event sequences (`replace_then_cancel`, `replace_then_replace`).  This retains
80 sequence units per arm and 320 fixed provider calls without inventing an
absent object.  It reduces task-identity diversity from two to one, which must
be reported as an external-validity limitation.

Before freezing this correction, the reverse prefix (tomato sauce completed,
alphabet soup still pending) must pass 10/10 on task-0 development states
0--9 with the already validated bounded-regrasp controller.  The existing
forward prefix already passed 10/10.

## Reverse-prefix preregistration

- authorized task/state cells: task 0, states 0--9 only;
- done object: `tomato_sauce_1`;
- pending object: `alphabet_soup_1`;
- controller configuration hash:
  `56171aef20a9f60e335259ff10abe7c211f6594a98b52b09864effcc7b1d988a`;
- success: controller placement succeeds, then five consecutive checks are
  exactly done=true and pending=false;
- gate: 10/10, with every failure retained and classified;
- provider calls: 0;
- stop: any failure blocks the corrected formal manifest.
