# Task-0/task-7 shared-prefix development audit preregistration

Status: frozen before loading any task-0/task-7 initial state.

## Authorized development pool

- LIBERO-10 task 0, states 0--9, done object `alphabet_soup_1`, pending object
  `tomato_sauce_1`, target `basket_1_contain_region`;
- LIBERO-10 task 7, states 0--9, done object `alphabet_soup_1`, pending object
  `cream_cheese_1`, same target;
- execution order: task 0 then task 7; within task ascending state ID;
- exactly one episode per task/state; no retry or state skip.

The controller is the independently validated bounded-regrasp configuration:
`OracleSkillConfig(max_move_steps=60)` with attempts centered, `+/-12 mm` X,
then `+/-12 mm` Y.  Warmup is 10 actions.  Success requires the done object in
the basket and the pending object outside it for five consecutive one-action
holds.

CPU only, zero provider credentials/calls, no interruption method and no
post-event execution.  Task-0/task-7 states 10--49 and task-1 states 25--49 are
not indexed.

## Gate

Both tasks must achieve 10/10 stable prefixes.  Any failure blocks creation of
the new formal manifest and is diagnosed only with these development states.
Passage authorizes manifest freezing and cold preflight, not provider calls.

