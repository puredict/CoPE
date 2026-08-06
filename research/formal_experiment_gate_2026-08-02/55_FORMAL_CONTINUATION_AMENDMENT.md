# Formal state-33 continuation amendment

Date frozen: 2026-08-03 (Asia/Shanghai), after the state-33 common-prefix
failure and before any state-33 provider call or prefix restart.

## Why this amendment exists

The original formal process completed states 27--32 and stopped when the first
state-33 common prefix returned `grasp_not_acquired`. The retained journal is
immutable at commit `0722410cc8d5b02c9a499e5b611b661378e5d7ae` with SHA-256
`36f6450761bb01442660f59f8bfaf5977cc961cdb19bb263bcdf53c4170f96eb`.
It contains 48 completed provider calls and no state-33 provider call.

The original uninterrupted-run integrity claim remains failed and will be
reported as such. This amendment permits one segmented continuation; it does
not erase or relabel the interruption.

## Frozen continuation

- implementation commit: `e7bf838a82567bf59e2903fb40e42bbb6c2d77b1`;
- zero-credential continuation preflight:
  `d4c7e030e4eb15d06823a137eafa0af9ed036017`;
- runtime HEAD must be the clean commit containing this amendment;
- the runner must cryptographically validate the retained 60-record journal;
- start at state 33 and run through state 46 in order;
- never initialize states 27--32 again and never index states 47--49;
- retain the original four interfaces, model, seed, temperature, timeout,
  token limits, zero provider retries/repairs/fallback and CPU-only runtime;
- output:
  `research/formal_matched_valid_arm_2026-08-03/continuation_states33_46_v1`.

This is exactly one declared restart of the common state-33 physical prefix
with unchanged seed and controller. If state 33 again returns a prefix failure,
the process must stop before provider calls and no second restart is allowed.
If it succeeds, the continuation issues 112 calls for states 33--46. Completed
states 27--32 are never redrawn.

## Combined analysis rule

If the continuation completes, combine the retained 48 calls with the new 112
calls for the originally preregistered 160-call, 40-case analysis. Report both
segment commits and the original interruption prominently. The same paired
endpoint and exact McNemar tests in preregistration 53 remain fixed.

Combined integrity requires:

1. segment 1 journal hash matches the pinned value;
2. segment state sets are exactly 27--32 and 33--46 with no overlap;
3. every original case occurs exactly once and every case has four provider and
   four embodied rows;
4. provider settings, manifests, shared-envelope checks and execution rules are
   unchanged;
5. state 33 has no provider draw before the successful common prefix;
6. states 47--49, credentials, retries, repairs and fallback remain absent.

The physical-prefix restart is an infrastructure qualification, not a method
success. The result may be described only as a hash-locked segmented formal
run, never as one uninterrupted run.
