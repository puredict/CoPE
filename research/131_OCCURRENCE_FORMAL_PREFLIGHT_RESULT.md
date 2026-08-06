# Occurrence-sensitive learned formal preflight result

Date: 2026-08-04  
Runtime commit: `793e130f4fb4e38279382dc2c4b992895608184d`  
Manifest SHA-256: `21f22b95dd106dc91c58ef288ecf22c7b5dcd093d279320b60be392d652992b8`

## Decision

**PASS for manifest, oracle-interface, and request-equivalence readiness.** No
learned outcome exists; execution remains blocked until the crash-safe runner,
locked analyzer, secure credential, and smoke gate pass.

## Exact checks

- 40 unique cases = 10 object triples x recurrence depths 1--4.
- Five arms occupy every order position exactly 8 times.
- 200/200 oracle proposals materialized to the canonical expected state.
- All 40 case groups had exactly one common input hash, one arm-normalized wire
  hash, and one oracle candidate hash across five arms.
- Planned provider calls: 200; calls made: **0**.
- Simulator states indexed: **0**.
- Full repository regression before preflight: **596/596** tests passed.

## Frozen request and oracle-carrier sizes

| Arm | Median oracle proposal bytes | Median wire bytes | Maximum wire bytes |
|---|---:|---:|---:|
| CoPE | 278.5 | 7,678.5 | 9,584 |
| Full replan | 561.0 | 7,599.5 | 9,505 |
| Neutral patch | 1,743.5 | 7,741.5 | 9,647 |
| Governed delta | 2,003.5 | 7,747.5 | 9,653 |
| FSR-PC | 4,405.5 | 7,540.5 | 9,446 |

Median wire size by recurrence depth was 5,927, 7,080, 8,229, and 9,392
bytes for depths 1--4. Contract text causes the small cross-arm wire-size
differences; common recovery input and provider settings are identical.

## Claim boundary

The byte table is oracle accounting, not evidence that a model will generate a
valid output. Full replan remains a near-sized carrier and must be reported.
The formal learned question is whether first-pass CoPE outputs beat both
neutral and governed occurrence-aware controls; FSR-PC weakness cannot rescue
a primary tie.
