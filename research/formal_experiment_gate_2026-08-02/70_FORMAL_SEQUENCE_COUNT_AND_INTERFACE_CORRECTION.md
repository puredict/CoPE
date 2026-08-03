# Formal sequence-count and interface correction

Date: 2026-08-04

## Correct call accounting

A genuine two-event sequence requires two provider calls per arm: event 1 is
committed first, then event 2 is constructed from and prompted with the
published revision-2 state.  Consequently, the earlier arithmetic of 80
sequences per arm and 320 total calls was incorrect; that design would require
640 calls.

The frozen 320-call design is therefore:

- one physically feasible LIBERO-10 task (task 0);
- formal states 10--29 (20 states total);
- one prefix orientation per state:
  - states 10--19: A=alphabet soup, B=tomato sauce;
  - states 20--29: A=tomato sauce, B=alphabet soup;
- two separately reset sequence types per state;
- 20 states x 2 sequence types = 40 sequence units per arm;
- 40 sequences x 2 event calls = 80 calls per arm;
- 80 calls x 4 arms = **320 fixed provider calls**.

Both prefix orientations passed 10/10 on development states 0--9.  Task-0
states 30--49 remain permanent reserve.  Task 7 is excluded from embodied
confirmation because it has only three relevant objects and cannot instantiate
the preregistered four-distinct-object double replacement.

## Corrected sequential interface gate

Before the formal manifest is frozen, rerun the 16-cell zero-provider gate on
the two task-0 orientations crossed with the two sequence types and four arms.
All earlier pass conditions remain unchanged, including logical and typed hash
continuity and cross-arm final-state equality.

## Interpretation limitation

The confirmatory study estimates performance over state variation, prefix
orientation, and dependent sequence type within one scene/task identity.  It
does not establish cross-task generalization.  A future external replication
must use another scene containing at least four manipulable objects and must
receive its own prefix qualification.
