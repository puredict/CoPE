# Fresh-state interruption-recovery preregistration

Date frozen: 2026-08-01 (Asia/Shanghai)

## Question

Does the previously selected local-stage recovery rule retain its recovery-cost
advantage over exact return on genuinely uninspected LIBERO initial states,
without changing physical updated-goal success or introducing protected-object
or environment-contact regressions?

This is an oracle mechanism test. It is not an end-to-end learned-policy CoPE
versus FSR-PC comparison and cannot establish a safety claim.

## Frozen evidence split

- Development: state 0.
- Previously observed validation/diagnostic: states 1–4.
- Fresh confirmatory set for this run: states 5–14, selected consecutively
  before inspecting their outcomes.
- Untouched reserve after this run: states 15–49.

No parameter may be changed using states 5–14. If a method fails, the failure
is reported on the assigned denominator; a modified rule may not be rerun and
called a fresh result on these states.

## Frozen code and methods

Remote worktree: `/home/lijingsu/codex-worktrees/fsr-pc-v2-canary`

Pre-experiment parent commit: `09082d945d8fb5a5c4bcfa0f9ae2a0239aa67e43`

Task: LIBERO-10 task 1. Event: second authorized replacement while the obsolete
alphabet-soup commitment is held at the `pre_release` timing. Updated pending
object: tomato sauce. Completed cream-cheese progress must remain valid.

Three independently reset arms per state:

1. `stale_continue`: execute the obsolete commitment; negative control.
2. `safe_return_switch`: return the obsolete held object to its recorded
   stable pose, then execute the replacement.
3. `local_stage_switch`: use the already selected 75%-toward-origin staging
   rule, zero XY offset, staging-descent action limit 1.0, then execute the
   replacement.

All arms use safety telemetry. No geometric-clearance variant or slowdown is
introduced in this run.

## Integrity requirements

For every state, all three arms must match on:

- event step;
- pre-event low-level action SHA-256;
- pre-patch MuJoCo-state SHA-256;
- end-effector position at event;
- held-object position at event.

The semantic patch must preserve simulator state and emit no action. Raw CSV
rows, logs, command record, source hashes, and aggregate hashes are retained.
Task success is computed from simulator predicates for cream cheese and tomato
sauce, not from the obsolete LIBERO BDDL goal naming butter.

## Assigned-denominator endpoints

Primary mechanism endpoint:

- physical updated-goal success for all 10 assigned states.

Primary recovery-cost endpoint:

- post-event environment actions, compared pairwise only when both exact and
  local arms reach the physical updated goal, while still reporting every
  assigned failure.

Secondary endpoints:

- physical success within a fixed 280 post-event-action budget;
- success within the legacy global 600-step horizon;
- stale-commitment execution rate;
- task-relevant net-body peak-force and force-impulse proxies;
- robot/protected-object, task-object/protected-object,
  robot/environment, and obsolete-object/receptacle contact steps;
- protected cream-cheese and idle-butter displacement.

The 280-action budget was selected before this fresh run from the previously
reported descriptive curve. It is not retroactively a preregistered endpoint
for states 0–4.

## Frozen decision rule

Retain local staging as an efficiency ablation only if all conditions hold:

1. pair-prefix integrity passes for 10/10 assigned states;
2. local physical updated-goal successes are not fewer than exact-return
   successes;
3. both arms succeed in at least 8/10 assigned states;
4. among paired physical successes, local uses fewer post-event actions in at
   least 80% of pairs and median savings are at least 20 actions;
5. local does not increase the number of assigned episodes with any
   robot/protected-object contact, any robot/environment contact, or more than
   5 mm displacement of either protected cream cheese or idle butter.

Peak-force and impulse proxies are descriptive and cannot veto or establish a
safety claim because `cfrc_ext` is a filtered net-body proxy rather than a
calibrated per-contact sensor. Their direction must still be reported.

If condition 1 fails, comparison validity fails. If conditions 2–5 fail,
local staging is rejected rather than tuned on this set. If fewer than 8/10
states reach the event substrate in both recovery arms, the result is labeled
substrate-limited and cannot qualify a main manipulation comparison.

## FSR-PC/CoPE gate

No formal CoPE–FSR-PC rollout may be claimed from a deterministic fake
provider. After the fresh oracle run, the main-comparison readiness gate is
re-audited. A real provider adapter, exact common input, neutral validation,
shared compiler/backend, equal provider budget, and non-fake metadata are
mandatory before any end-to-end result.
