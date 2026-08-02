# X09 two-state Oracle semantic execution pilot preregistration

Date frozen: 2026-08-02 (Asia/Shanghai)

Pre-run parent: `579186e776a5630b5f1591956ef07ed523b14d35`

## Question

After a real LIBERO checkpoint has one original commitment physically
satisfied, can a correct persistent commitment edit be executed without
discarding that progress?

This isolates the execution substrate.  It is not a learned-policy comparison,
does not estimate population success, and cannot establish superiority over
FSR-PC because native and CoPE deliberately converge to the same canonical
state and directive.

## Explicitly authorized reserve

The source manifest is the unchanged
`manifests/semantic_oracle_pilot_v1.csv` (SHA-256
`65631c1fcc14fbac5e5e712959ad03601b0bda51c35283ef95d55d459949ac80`).

- state 25: replace pending `butter_1` with `alphabet_soup_1`;
- state 26: cancel pending `butter_1`;
- native FSR-PC and Oracle CoPE each receive an independent reset and replay of
  the same deterministic Oracle prefix;
- states 27--49 remain forbidden regardless of outcome.

The general semantic config remains `rollout_authorized=false`.  The narrow
authorization in `01_AUTHORIZATION.csv` is a one-experiment sidecar justified
by the committed X04 gate.  It does not modify or broadly unlock that config.

## Frozen physical prefix

For every arm:

1. reset the exact assigned LIBERO-10 task-1 state;
2. use `OracleSkillConfig(max_move_steps=60)` and seed equal to state ID;
3. warm up, put `cream_cheese_1` in the basket, then require five consecutive
   additional steps with cream cheese true and butter false;
4. freeze initial-state, action-prefix, RGB, qpos/qvel, end-effector, and object
   pose evidence;
5. generate a non-test live predicate packet and run the X04 common semantic
   path before any post-event action.

Within each event pair, native and CoPE must match on event step, prefix hash,
packet hash, RecoveryInput hash, simulator hash, and checkpoint poses.

## Frozen post-event behavior

Replacement, state 25:

- execute the shared compiled directive through the Oracle skill controller by
  placing `alphabet_soup_1` in the basket;
- at most 280 post-event policy actions;
- final cream cheese and alphabet soup predicates true;
- butter predicate false; completed progress retained.

Cancellation, state 26:

- compiled directive must be `HALT`;
- zero post-event policy actions;
- run exactly 30 neutral environment hold steps for physical verification,
  explicitly excluded from the policy-action budget;
- final cream cheese true and butter false.

## Decision

PASS requires all four arm rows and both pair-audit rows to pass, exact paired
prefix/evidence identity, no provider or GPU, accepted canonical semantic
states, no stale pending-goal action, the frozen budgets, focused tests, and a
clean full regression.  Any failed arm is retained and is NO-GO for a learned
semantic pilot.  A controller failure is reported as an execution-substrate
failure and does not authorize retuning or reusing states 25/26 as fresh data.

The runner must use output-create semantics and reject every state except
25/26.  Once executed, both states are consumed regardless of result.
