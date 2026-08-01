# Preregistered fresh-state recovery result

Date: 2026-08-01

Preregistration commit: `7e7b6ce9cc87e6c880886bcbbd731177544c3099`

Evidence class: privileged oracle mechanism experiment on previously
uninspected LIBERO task-1 initial states 15–24. This is not learned-policy CoPE
versus FSR-PC evidence and does not establish safety.



## Assigned denominator and integrity

Valid raw rows: 30/30.
No assigned state was missing an event row. States with complete matching prefixes: 10/10.

| Endpoint | Stale continue | Exact return | Local stage |
|---|---:|---:|---:|
| Physical updated-goal success, assigned denominator | 0/10 | 10/10 | 10/10 |
| Success within fixed 280 post-event actions | 0/10 | 9/10 | 10/10 |
| Success within legacy global 600 steps | 0/10 | 4/10 | 8/10 |
| Expected stale commitment executed | 10/10 | 0/10 | 0/10 |

## Event-qualified recovery evidence

Paired physical successes: 10/10 assigned states.
Local was faster in 10/10 paired successes. Mean
exact-minus-local saving: 36.2 actions; median:
35.5 actions.

| Metric, event-qualified arms | Exact return | Local stage |
|---|---:|---:|
| Mean post-event actions | 274.4 | 238.2 |
| Mean task-relevant peak-force proxy (N) | 51.09 | 47.97 |
| Mean force-impulse proxy (N·s) | 163.67 | 150.59 |
| Any preregistered hazard-proxy episode | 0/10 | 0/10 |
| Robot/protected-object contact episode | 0/10 | 0/10 |
| Robot/environment contact episode | 0/10 | 0/10 |
| Protected/idle displacement >5 mm | 0/10 | 0/10 |

Peak proxy: local lower in 4/10, paired mean delta -3.12 N. Impulse proxy: local lower in 10/10, paired mean delta -13.08 N·s.

## Per-state evidence

| State | Exact goal | Local goal | Stale executed | Exact actions | Local actions | Exact−local | Exact hazard | Local hazard |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 15 | 1 | 1 | 1 | 272 | 238 | +34 | 0 | 0 |
| 16 | 1 | 1 | 1 | 271 | 236 | +35 | 0 | 0 |
| 17 | 1 | 1 | 1 | 269 | 234 | +35 | 0 | 0 |
| 18 | 1 | 1 | 1 | 274 | 238 | +36 | 0 | 0 |
| 19 | 1 | 1 | 1 | 277 | 240 | +37 | 0 | 0 |
| 20 | 1 | 1 | 1 | 275 | 239 | +36 | 0 | 0 |
| 21 | 1 | 1 | 1 | 278 | 241 | +37 | 0 | 0 |
| 22 | 1 | 1 | 1 | 281 | 237 | +44 | 0 | 0 |
| 23 | 1 | 1 | 1 | 272 | 238 | +34 | 0 | 0 |
| 24 | 1 | 1 | 1 | 275 | 241 | +34 | 0 | 0 |

## Frozen decision rule

| Condition | Result |
|---|---|
| C1_prefix_integrity_10_of_10 | PASS |
| C2_local_success_not_fewer_than_exact | PASS |
| C3_both_at_least_8_of_10 | PASS |
| C4_faster_80pct_and_median_at_least_20 | PASS |
| C5_no_increase_in_hazard_episode_count | PASS |

Decision: **RETAIN local staging as an efficiency ablation only**.

The frozen protocol states that a C1 failure invalidates the assigned
comparison, whereas failure of C2–C5 rejects local staging. Any
method-independent substrate failure therefore makes this run inconclusive for
the retain/reject decision. Event-qualified pairs remain conditional mechanism
evidence, but cannot repair an assigned-denominator validity failure. States
15–24 may not be reused as fresh data for a
modified rule.
