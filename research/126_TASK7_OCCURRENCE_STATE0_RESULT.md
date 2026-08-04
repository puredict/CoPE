# Task-7 occurrence-restoration state-0 canary result

Date: 2026-08-04  
Runtime commit: `04558b68e891a9014e2d98c64c684660c0b434ba`

## Decision

**PASS (2/2 independent episodes).** Task 7 is restored as a viable physical
development candidate under the redesigned three-object,
occurrence-addressed sequence. This is a substrate result, not a learned
method result.

## Exact outcomes

| Mode | Prefix | Semantic no-action / simulator preservation | History | Terminal | Steps |
|---|---|---|---|---|---:|
| cancel | PASS | PASS / PASS | PASS | `HALT`, predicates PASS | 185 |
| restore | PASS | PASS / PASS | PASS | cream-cheese placement PASS | 330 |

- Both independently reset arms shared the exact prefix action hash
  `9e3b67e22d4c534b563c6d062a72ec06de0c02a29cd5a118fd9781d372e3ccb8`.
- Five prefix and five final predicate checks passed in each episode.
- The restore episode preserved superseded cream-cheese occurrence 1 and
  tomato-sauce occurrence 1 while activating cream-cheese occurrence 2.
- Provider calls: **0**; learned policy: **false**.
- Only task-7 state 0 was indexed. Task-7 states 1--49 remained unopened;
  task-1 state 33 was not retried; task-1 states 34--49 remained unopened.

## Interpretation

The previous task-7 stop was caused by referencing absent `butter_1`. Replacing
that invalid four-object design with a recurring three-object commitment gives
a physically executable sequence while adding a harder identity/provenance
case. The pass justifies development validation on untouched task-7 states
1--9 under a new preregistration. It does not authorize provider calls or
formal states.
