# Matched valid-arm state-0 result with infrastructure recovery

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**Substantive state-0 gate PASS, with a mandatory infrastructure-interruption
qualification.**

The original process was not uninterrupted: SSH exit 255 killed it after all
eight provider calls and before any replacement embodied row was written. That
interruption is retained at commit
'49bdd2fbcc08aaf66d7975a8ebb44ae5b48e83cc'.

A separately preregistered execution-only resume used the committed semantic
journal, performed zero provider calls, reproduced all prefix and semantic
hashes, and completed the missing replacement executions. Resume result commit:
'2bfa5f7fb6f49a9ab27472cf36714d800f0b1a34'.

## Retained provider result

| Arm | Cancellation semantic | Replacement semantic |
|---|---:|---:|
| CoPE | pass | pass |
| Neutral sparse | pass | pass |
| Corrected compact | fail | fail |
| Metadata-free FSR-PC | fail | fail |

All 8/8 provider calls returned OK with zero retries and four-arm fairness.
CoPE and neutral outputs have distinct response hashes; each independently
materialized the canonical post-state. Compact failed path validation and FSR
failed full semantic-state validation. Neither was repaired.

## Matched execution

- valid cancellation cells: CoPE and neutral 2/2 terminal success, zero actions;
- invalid cancellation cells: compact and FSR 2/2 fail-closed, zero execution;
- valid replacement cells: CoPE and neutral 2/2 terminal success;
- both replacement cells selected 'alphabet_soup_1', retained cream cheese and
  did not execute butter;
- both used exactly 189 post-event actions;
- both action hashes equal
  'bfabcdbe1be872fd21cd60465839f138c125a10cb0aef45f7a0169cb773cc000';
- invalid replacement cells: compact and FSR 2/2 fail-closed, zero execution;
- provider calls during resume: 0.

The source interruption journal SHA-256 remained
'635519a331ce52ced7743214821b8c68f8e3c853738515b48d24da9f307d60ef'.
No reserved state was used.

## Interpretation

The state-0 result supports the sparse-edit structural hypothesis, not a
CoPE-vocabulary advantage: neutral labels and CoPE labels yield the same
validated state and exactly the same physical command trace. The interruption
prevents describing this as one uninterrupted end-to-end process, but it did
not trigger new provider draws or result selection.

Development expansion may proceed only under a new explicit post-recovery
preregistration. Formal reserved states remain locked.
