# Occurrence v1 result and contract-explicit v2 diagnostic preregistration

Date: 2026-08-04
Status: written after v1 outcomes and before any v2 provider call

## Immutable v1 result

The frozen v1 run completed all 200 zero-retry calls with no infrastructure
failure. CoPE succeeded in 40/40 cells, neutral in 0/40, governed in 0/40,
FSR-PC in 8/40, and full replan in 0/40. The preregistered joint gate is false
because locality had zero jointly semantic-valid primary pairs. The official
claim status remains `NO_GO_PRIMARY_NEUTRAL_COMPARISON`; v2 may not alter,
replace, pool with, or rescue that decision, and embodied v2 remains locked.

## Outcome-triggered construct concern

The v1 failure taxonomy exposed output-contract incompleteness that the
model-free oracle capability gate did not test:

- the governed prompt requested a canonical "after-record" but did not name
  the required JSON key `after`; the model used `after_record` in 40/40 cells;
- the full-replan prompt did not specify the nested completed-fact shape or
  that remaining occurrences must be ID strings rather than plan objects;
- neutral identified both correct occurrence IDs in 40/40 cells, but the
  prompt did not enumerate the six canonical writes or all nested record
  shapes;
- the CoPE prompt already named all six top-level fields and their value
  sources.

Therefore v1 establishes performance under the frozen v1 prompt distribution,
not an information-complete representation comparison.

## v2 diagnostic question

After making every arm's serialization contract explicit while leaving the
common input, model, seed, temperature, cases, materializers, canonical oracle,
call budget, and zero-retry policy unchanged, does CoPE still outperform both
primary sparse controls?

This reuses the 40 v1 cases and was designed after observing v1. It is an
exploratory construct-validity diagnostic, not a new confirmatory paper gate.

## Frozen changes

- CoPE contract: byte-identical to v1.
- Neutral: explicitly enumerates the six writes, exact path grammar, and
  nested predicate/plan/commitment shapes.
- Governed: explicitly names `after`, the sorted two-occurrence scope, record
  fields, and blackboard shapes.
- FSR-PC: explicitly states full commitment identity consistency.
- Full replan: explicitly states predicate-record shape and ID-only lists.

No expected values are injected by an oracle; every value must still be
derived from the byte-identical common pre-state and event. Existing strict
materializers and analyzer are reused unchanged.

## Calls and artifacts

- manifest: unchanged 40-case v1 manifest;
- five arms, one draw per case/arm: 200 maximum calls;
- retry budget: zero;
- output directory:
  `/home/lijingsu/cope-runs/occurrence-contract-explicit-v2`;
- analysis directory:
  `/home/lijingsu/cope-runs/occurrence-contract-explicit-v2-analysis`.

## Interpretation

- If neutral/governed become successful and close the efficacy gap, v1's
  apparent CoPE advantage is substantially attributable to contract
  completeness; stop architecture/method claims and redesign on held-out data.
- If CoPE retains a large dual-control advantage and valid locality pairs now
  exist, the result justifies designing a new disjoint-vocabulary,
  outcome-blind confirmatory v3. It does not itself support a paper claim.
- If primary controls remain uniformly invalid, v2 is inconclusive unless the
  failures are genuine occurrence/transition errors rather than serialization
  mismatches.
- Under no v2 outcome may the locked embodied experiment be launched from the
  original false v1 joint gate.

