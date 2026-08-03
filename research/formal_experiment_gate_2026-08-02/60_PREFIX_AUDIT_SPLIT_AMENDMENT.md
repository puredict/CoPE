# Shared-prefix audit split amendment

Status: frozen before any state 5--24 audit execution.

This amendment supersedes the single-stage state 5--24 execution proposed in
`59_PREFIX_FEASIBILITY_AUDIT_PREREG.md`.  The purpose is to prevent controller
repair from being evaluated on states whose prefix outcomes were already
inspected during diagnosis.

## Sequential authorization

1. **Diagnostic stage:** run the current committed controller on task-1 states
   5--14, exactly once per state, in ascending order.
2. Inspect only states 5--14 and develop any controller repair using states
   0--14.  Freeze the candidate controller and its configuration before the
   validation stage.
3. **Locked validation stage:** task-1 states 15--24 remain unindexed until the
   candidate is frozen.  Then compare the frozen baseline and candidate from
   identical resets on every state, with controller order fixed in advance.

This commit authorizes only stage 1.  Stage 3 requires a separate committed
runner and validation preregistration.  States 25--49 remain unindexed by this
audit.  In particular, formal state 33 is never retried and states 34--49 are
not opened.

## Frozen diagnostic-stage protocol

- LIBERO-10 task 1; state IDs exactly `5,6,7,8,9,10,11,12,13,14`;
- seed equals state ID; ascending execution order; no retry and no state skip;
- controller configuration is `OracleSkillConfig(max_move_steps=60)`;
- ten-step open-gripper warmup, cream-cheese-to-basket placement, then five
  one-step open-gripper predicate-stability holds;
- CPU only and no provider credential, request, parsing, semantic patch, or
  post-interruption execution;
- output directory must not exist; worktree must be clean and committed;
- retain every attempt, including prefix failures, with initial-state hash,
  exact action-prefix hash, simulator-state hash, action count, phase errors,
  object/eef geometry, grasp/lift/predicate result, and stability trace;
- a crash does not authorize rerunning an attempted state; the append-only
  journal determines which states were attempted.

## Diagnostic decision rule

- Any failure means the shared event constructor is not reliable on the
  diagnostic split and requires repair before formal experiments.
- All ten successes are evidence only for states 5--14; they do not authorize
  reopening formal states or inspecting states 15--24 early.
- Prefix feasibility is a substrate result shared by every recovery method;
  it is not counted as a CoPE method success or failure.

