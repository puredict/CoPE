# Occurrence-addressed restoration gate result

Date: 2026-08-04  
Implementation commit: `8295a0fc29bf9e5e5d9a82ca5272956a604ff3aa`

## Decision

**PASS for symbolic/interface feasibility.** Occurrence identity is necessary
for the recurring-commitment case, but it is not unique to CoPE's carrier.

## Results

- Five arms x two sequence types x two events: **20/20** canonical-equivalent
  materializations.
- Negative cases: **5/5** rejected (stale revision, wrong target occurrence,
  historical-occurrence reactivation, duplicate new occurrence, and omitted
  historical record).
- Provider calls: **0**; simulator states indexed: **0**.
- In all five restore arms, cream-cheese occurrence 1 stayed `superseded`,
  tomato-sauce occurrence 1 became `superseded`, and cream-cheese occurrence 2
  became `active`.
- All restore arms compiled to
  `place_in(cream_cheese_1, basket_1_contain_region)` and shared one final
  canonical state hash. All cancel arms compiled to `HALT` and shared one
  final canonical state hash.
- Full repository regression before the result: **594/594** tests passed.

## Carrier size (four event proposals per arm)

| Arm | Median bytes | Total bytes |
|---|---:|---:|
| CoPE | 323.0 | 1,222 |
| Full replan | 399.0 | 1,646 |
| Neutral patch | 1,848.5 | 6,160 |
| Governed delta | 2,089.0 | 7,308 |
| FSR-PC | 2,431.0 | 9,858 |

CoPE is compact, but full replan is again a near-sized control. These are
oracle-carrier bytes, not learned accuracy or token-cost outcomes.

## Interpretation

The old object-derived identifier conflated predicate identity with temporal
commitment identity and correctly refused to overwrite history. The new schema
separates them: predicates still ground physical meaning, while positive
occurrence numbers address immutable lifetime records. This supports a narrow
benchmark/method requirement for recurring commitments.

It does not restore an assurance-architecture novelty claim. Neutral,
governed, FSR-PC, and full-replan controls all express the correct result once
given occurrence IDs. A learned comparison must therefore ask whether the
compact occurrence-addressed interface improves first-pass generation, not
whether generic state governance is impossible.
