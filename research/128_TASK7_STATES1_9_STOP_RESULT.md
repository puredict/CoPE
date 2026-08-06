# Task-7 occurrence states 1--9 development stop result

Date: 2026-08-04  
Runtime commit: `c946f1b830f5f2a32945ce04b9c99c84ce6cea0e`

## Decision

**FAIL and STOP at task-7 state 2 restore.** Do not retry state 2, do not tune
the controller on task 7, and do not index task-7 states 3--49. Task 7 is not a
formal physical identity under the frozen controller.

## Executed cells

| State | Mode | Prefix | Semantic no-action / simulator | Terminal | Result |
|---:|---|---|---|---|---|
| 1 | cancel | PASS | PASS / PASS | PASS | PASS |
| 1 | restore | PASS | PASS / PASS | cream cheese placed | PASS |
| 2 | cancel | PASS | PASS / PASS | PASS | PASS |
| 2 | restore | PASS | PASS / PASS | `target_predicate_false` | **FAIL** |

State 1 cancel/restore shared prefix action hash
`e3a97145cf31e5085d9335b1cfcdef6d890df772036f26e140478c826e86a827`.
State 2 cancel/restore shared prefix action hash
`fc4b66ead0a68022384781d84045fb0e8517ce4739aeb5a00ebbd92b287d2e69`.
Thus the failing arm did not begin from a different semantic-treatment prefix.

The state-2 restore cell preserved the completed soup predicate, emitted no
semantic action, preserved the simulator hash during the semantic phase, and
maintained correct occurrence history. Its final cream-cheese placement ended
after 366 steps with `target_predicate_false`; cream cheese remained outside
the basket. This is a method-independent terminal controller/substrate failure.

## Integrity

- Provider calls: **0**; retries: **0**.
- The first failure stopped the loop immediately.
- Task-7 states 3--49 were not indexed.
- Task-1 state 33 was not retried and task-1 states 34--49 were not indexed.
- Every completed cell was written to an `fsync` journal before advancing.

## Claim boundary

The symbolic occurrence-addressed result remains valid: all five high-level
representations can express recurring commitments. The physical data show only
that the existing privileged position controller has insufficient reliability
for task-7 formal use (restore succeeded on states 0 and 1, then failed on
state 2). They are neither a CoPE failure nor cross-task method evidence.
