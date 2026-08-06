# Controller substrate qualification result

Date: 2026-08-02

Overall gate: **PASS**.

Interpretation: qualified only for the privileged oracle/mechanism stratum on basket-compatible skills.
It is not a learned manipulation system and is not qualified for the learned/main stratum.

## Behavioral results

| Qualification arm | Updated/intended goal | Stale action | Progress retained |
|---|---:|---:|---:|
| Original goal from reset | 5/5 | not applicable | 5/5 |
| Updated goal from reset | 5/5 | 0/5 butter | 5/5 |
| Checkpoint no edit | 0/5 updated; 5/5 original | 5/5 butter | 5/5 |
| Checkpoint oracle full state | 5/5 | 0/5 butter | 5/5 |
| Checkpoint oracle CoPE patch materialized | 5/5 | 0/5 butter | 5/5 |
| No-event plain | 5/5 original | not applicable | 5/5 |
| No-event semantic scaffold | 5/5 original | not applicable | 5/5 |
| Timing stale controls, three phases | 0/15 final update | 15/15 alphabet soup | 15/15 |
| Timing local-stage recovery, three phases | 15/15 final update | 0/15 alphabet soup | 15/15 |
| Repeated replacement, event two ignored | 0/5 final update | 5/5 alphabet soup | 5/5 |
| Repeated replacement, two patches | 5/5 final update | 0/5 alphabet soup | 5/5 |

The post-lift, mid-transfer, and pre-release local-stage arms each passed 5/5.
Oracle full-state and independently materialized CoPE-patch states had identical
canonical SHA-256 and compiled directives in 5/5 states. The two no-event arms
had identical terminal predicate fingerprints in 5/5 states.

## Frozen-gate audit

| Gate | Pass |
|---|---:|
| original_reset | True |
| updated_reset | True |
| checkpoint_oracle_full | True |
| checkpoint_oracle_patch | True |
| checkpoint_no_edit_stale | True |
| full_progress | True |
| patch_progress | True |
| full_stale_suppression | True |
| patch_stale_suppression | True |
| no_event_plain | True |
| no_event_scaffold | True |
| no_event_terminal_parity | True |
| repeated_double_patch | True |
| repeated_ignore_second | True |
| paired_provenance | True |
| semantic_integrity | True |
| scope_accounting | True |
| post_lift_local_recovery | True |
| post_lift_stale_control | True |
| mid_transfer_local_recovery | True |
| mid_transfer_stale_control | True |
| pre_release_local_recovery | True |
| pre_release_stale_control | True |

## Assigned denominator

- Episodes: 75.
- Method-independent pre-event failures: 0 / 75.
- Paired provenance groups: 35 / 35.
- Reserved state indices used: 0.
- Learned-policy calls: 0; provider calls: 0; GPU execution/inference: 0
  (`CUDA_VISIBLE_DEVICES=""`).
- Full repository regression: 341 passed in 46.38 seconds.

## Scope boundary

Object/region selection, simulator geometry, predicates, event phase, and patch operation are privileged.
Passing does not authorize state 25 and does not qualify caddy insertion or any learned controller.

The upstream LIBERO init-state file is monolithic and was deserialized as a
whole runtime container. Qualification code indexed, reset, hashed, rendered,
and summarized only states 0--4; it did none of those operations for states
25--49. This is the frozen operational holdout definition inherited from the
pre-run storage clarification, not a claim of selective file deserialization.
