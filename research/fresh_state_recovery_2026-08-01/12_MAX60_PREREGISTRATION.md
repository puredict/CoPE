# Max-60 controller fresh-state preregistration

Date frozen: 2026-08-01 (Asia/Shanghai)

Pre-experiment parent commit:
`2c4cbddd05d3f15c56066376f483528c21ca28c1`

## Motivation fixed before outcomes

The first fresh run on states 5–14 was inconclusive because state 5 failed
before the semantic event in all arms. Correct-target diagnostics on that
already consumed state showed that the default 40-step motion-phase limit
stopped grasp descent at 8.45 mm error and failed to retain the object, whereas
`max_move_steps=60` converged in 45 descent steps and completed the physical
cream-cheese milestone.

This experiment tests that controller-cap change on untouched states. It does
not change local-stage geometry or reuse states 5–14 as fresh data.

## Frozen split

- Controller development: state 5 only.
- Consumed prior evidence: states 0–14.
- Fresh confirmatory set: states 15–24, selected consecutively before outcomes.
- Untouched reserve after this run: states 25–49.

No rule or threshold may be changed using states 15–24. Missing or failed
assignments remain in the denominator and may not be silently retried.

## Frozen arms and parameters

Task/event: LIBERO-10 task 1, authorized second replacement at pre-release.

Arms per independently reset state:

1. `stale_continue` negative control;
2. `safe_return_switch` exact-return comparator;
3. `local_stage_switch` 75%-toward-origin staging, zero XY offset,
   stage-descent action limit 1.0.

Common controller parameter: `max_move_steps=60` for every Cartesian motion
phase in every arm. All arms use corrected safety telemetry. No other
controller, semantic, staging, force, contact, or scoring parameter changes.

## Endpoints and integrity

Assigned denominator: 10 states and 30 arms.

All three arms must match event step, pre-event action SHA-256, pre-patch
MuJoCo-state SHA-256, end-effector event pose, and held-object event pose.
Semantic patches must preserve simulator state and emit no action.

Primary endpoints:

- assigned physical updated-goal success;
- pairwise post-event actions when both recovery arms physically succeed.

Secondary endpoints:

- physical success within the already fixed 280 post-event-action budget;
- legacy global 600-step gate;
- stale commitment execution;
- corrected net-body peak-force and force-impulse proxies;
- robot/protected, robot/environment, and >5 mm protected/idle displacement
  episode flags.

## Frozen decision rule

1. C1: complete matching prefixes for 10/10 states. Failure makes the assigned
   comparison inconclusive.
2. C2: local physical successes are not fewer than exact successes.
3. C3: both recovery arms physically succeed in at least 8/10 assigned states.
4. C4: local is faster in at least 80% of paired physical successes and median
   exact-minus-local savings are at least 20 actions.
5. C5: local does not increase the number of episodes with robot/protected
   contact, robot/environment contact, or >5 mm protected/idle displacement.

If C1 passes and any of C2–C5 fails, reject local staging. If all pass, retain
local staging only as an efficiency ablation. Force/impulse proxies remain
descriptive and cannot establish safety.

The global 600-step horizon is not a primary recovery-cost endpoint because
the max-60 controller can change pre-event duration. No result from this run
will authorize a formal CoPE–FSR-PC comparison while the real provider,
validator, semantic runner, and shared compiler blockers remain unresolved.
