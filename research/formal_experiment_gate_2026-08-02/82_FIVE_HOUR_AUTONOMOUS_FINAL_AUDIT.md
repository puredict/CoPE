# CoPE autonomous run final audit

Date: 2026-08-04

## Decision

**Technical GO for the locked 32-call development-only live-provider smoke.**

**Not GO for the 320-call formal run until that smoke passes.**

**Not yet submission-ready.**  The corrected learned-output comparison has not
run, so no evidence currently establishes that CoPE beats the generic JSON-path
neutral patch.  Technical gate completion is not a positive method result.

The only remaining launch blocker is external: the remote process environment
does not contain `OPENROUTER_API_KEY`.  Both runners have independently stopped
before provider calls or simulator indexing under this condition.  No key
prefix is present in the local or remote repository.

## Closed evidence

- task-1 authorized diagnostic states 5--14: prefix **10/10**, zero provider;
- task-1 independent states 15--24: natural candidate **10/10**, exact shared
  natural trajectories, stress candidate **10/10** versus single-grasp **0/10**,
  paired exact p `0.001953125`, zero provider;
- controller change is a bounded regrasp substrate repair, not method evidence;
- task-0/task-7 development prefixes: **10/10 + 10/10**;
- task-0 reverse prefix: **10/10**;
- full task-0 terminal action after both prefixes: **20/20**, no regrasp and no
  stale B/C placement;
- true sequential persistent semantics: event 2 consumes event-1 post-state,
  revision `1 -> 2 -> 3`, logical and typed hash continuity;
- corrected four-arm oracle interface gate: **16/16**;
- generic JSON-path transaction replaces the earlier isomorphic neutral arm;
- formal manifest contains 40 matched sequence units, balanced arm order and
  exactly 320 scheduled calls maximum;
- cold preflight: **320/320 requests constructed**, zero provider and zero
  formal-state indexing;
- final repository regression: **537/537 passed in 48.99 s**.

No task-1 state 33 retry occurred.  Task-1 states 34--49 were not indexed.
Formal task-0 states 10--29 were not indexed during credential/preflight gates;
task-0 states 30--49 remain reserve.

## Frozen integrity and interpretation

The runner now hard-locks the formal manifest, controller configuration, all
four output contracts, model, decoding settings, token/timeout budgets,
zero-retry rule, arm set and smoke case manifest.  It fsyncs event/trace
journals, refuses existing outputs and dirty worktrees, and supports derivation
only from complete unique journals after disconnect.  Partial journals cannot
be filled by replacement calls.

Analysis independently requires 320 unique cells, shared substrate eligibility,
identical physical prefix hashes, identical common-input hashes across attempted
same-event calls, zero retries and valid dependency skips.  The necessary
decisive-experiment gate was frozen before learned outcomes:

1. CoPE versus neutral exact McNemar `p < 0.05` and paired success difference
   at least `+0.15`;
2. no excess CoPE stale-execution or invariant/hash-continuity failures;
3. on pairs with two valid outputs in both methods, at least 20% median relative
   proposal-byte reduction and two-sided exact sign-test `p < 0.05`.

Passing remains insufficient for submission because the design has one task
identity with two prefix orientations.  A tie/loss against neutral, safety
excess or failed locality gate requires the assurance-framework reframe.  A
positive decisive result still needs fresh cross-task replication.

## Locked next transition

Use `81_LOCKED_LAUNCH_RUNBOOK.md`.  Securely establish the credential in the
remote caller environment without printing or persisting it; run the symbolic
smoke detached with its log outside the repository; commit PASS evidence and
restore a clean worktree; only then launch formal.  No prompt repair, call retry,
state substitution or result imputation is authorized after outcome exposure.
