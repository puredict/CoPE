# Preregistered fresh-state recovery result

Date: 2026-08-01

Preregistration commit: `e4e923e22880f079a343c1ad450f0e8158b1e819`

Evidence class: privileged oracle mechanism experiment on previously
uninspected LIBERO task-1 initial states 5–14. This is not learned-policy CoPE
versus FSR-PC evidence and does not establish safety.

This protocol-corrected report supersedes the preliminary `03_RESULT.md`,
which incorrectly converted a C1 validity failure into method rejection.

## Assigned denominator and integrity

Valid raw rows: 27/30.
State 5 produced no event row in all three arms because completed-progress
validation found the cream-cheese placement physically false. This is a
method-independent substrate failure, retained on the assigned denominator and
not technically retried. States with complete matching prefixes: 9/10.

| Endpoint | Stale continue | Exact return | Local stage |
|---|---:|---:|---:|
| Physical updated-goal success, assigned denominator | 0/10 | 9/10 | 9/10 |
| Success within fixed 280 post-event actions | 0/10 | 9/10 | 9/10 |
| Success within legacy global 600 steps | 0/10 | 5/10 | 9/10 |
| Expected stale commitment executed | 9/10 | 0/10 | 0/10 |

## Event-qualified recovery evidence

Paired physical successes: 9/10 assigned states.
Local was faster in 9/9 paired successes. Mean
exact-minus-local saving: 36.9 actions; median:
37.0 actions.

| Metric, event-qualified arms | Exact return | Local stage |
|---|---:|---:|
| Mean post-event actions | 274.0 | 237.1 |
| Mean task-relevant peak-force proxy (N) | 49.44 | 53.75 |
| Mean force-impulse proxy (N·s) | 163.11 | 150.93 |
| Any preregistered hazard-proxy episode | 0/10 | 0/10 |
| Robot/protected-object contact episode | 0/10 | 0/10 |
| Robot/environment contact episode | 0/10 | 0/10 |
| Protected/idle displacement >5 mm | 0/10 | 0/10 |

Peak proxy: local lower in 1/9, paired mean delta +4.31 N. Impulse proxy: local lower in 8/9, paired mean delta -12.18 N·s.

## Per-state evidence

| State | Exact goal | Local goal | Stale executed | Exact actions | Local actions | Exact−local | Exact hazard | Local hazard |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | SUBSTRATE | SUBSTRATE | SUBSTRATE | NA | NA | NA | NA | NA |
| 6 | 1 | 1 | 1 | 273 | 236 | +37 | 0 | 0 |
| 7 | 1 | 1 | 1 | 276 | 235 | +41 | 0 | 0 |
| 8 | 1 | 1 | 1 | 274 | 237 | +37 | 0 | 0 |
| 9 | 1 | 1 | 1 | 267 | 235 | +32 | 0 | 0 |
| 10 | 1 | 1 | 1 | 280 | 238 | +42 | 0 | 0 |
| 11 | 1 | 1 | 1 | 271 | 235 | +36 | 0 | 0 |
| 12 | 1 | 1 | 1 | 276 | 239 | +37 | 0 | 0 |
| 13 | 1 | 1 | 1 | 275 | 241 | +34 | 0 | 0 |
| 14 | 1 | 1 | 1 | 274 | 238 | +36 | 0 | 0 |

## Frozen decision rule

| Condition | Result |
|---|---|
| C1_prefix_integrity_10_of_10 | FAIL |
| C2_local_success_not_fewer_than_exact | PASS |
| C3_both_at_least_8_of_10 | PASS |
| C4_faster_80pct_and_median_at_least_20 | PASS |
| C5_no_increase_in_hazard_episode_count | PASS |

Decision: **INCONCLUSIVE — assigned comparison validity failed**.

The frozen protocol states that a C1 failure invalidates the assigned
comparison, whereas failure of C2–C5 rejects local staging. Therefore the
state-5 method-independent substrate failure makes this run inconclusive for
the retain/reject decision. The nine event-qualified pairs remain conditional
mechanism evidence, but they cannot repair the assigned-denominator validity
failure. States 5–14 may not be reused as fresh data for a modified rule.
