# Occurrence contract-explicit v2 result

Date: 2026-08-04

## Status

This is a post-v1 exploratory diagnostic. It does not replace the immutable v1
result and cannot unlock embodied experiments by itself.

- Calls/results: 200/200, zero retries, zero infrastructure stops.
- CoPE: 40/40 complete successes.
- Neutral JSON transaction: 0/40 strict successes.
- Governed affected-scope delta: 12/40.
- FSR-PC full semantic state: 30/40.
- Full replan: 13/40.
- Frozen decision: `NO_GO_PRIMARY_NEUTRAL_COMPARISON`.
- Governed primary gate: pass (risk difference 0.70; 12 valid locality pairs;
  median relative CoPE byte reduction 0.8606).
- Neutral primary gate: fail because there were no strict semantic-valid pairs.

## Required ambiguity audit

The strict neutral 0/40 is not an interpretable measure of recovery reasoning.
Thirty-eight of forty outputs used an add path ending in
`/commitments/+/`, treating `+` as an append operator. The validator instead
requires the new record ID as the third path component. The v2 prose used the
shorthand `/commitments/+/<replacement_id>` but did not show a literal path or
say that the path must not end in `/`.

In a read-only post-hoc diagnostic, replacing only that trailing add path with
the ID already present in the same output caused 35/40 proposals to equal the
frozen oracle and materialize successfully. This counterfactual is diagnostic
only; it is not a reported v2 success rate and is not used in the gate.

The five remaining neutral errors were two malformed add-address variants and
three content mismatches (principally an empty plan; one also misplaced the
plan dependency into the new commitment). Other component checks were strong:
current goal 40/40 exact, target lifecycle/validity/supersession updates 40/40
exact, and plan 37/40 exact after path normalization.

The governed arm improved from 0/40 in v1 to 12/40 in v2, demonstrating that
contract completeness materially affected the original comparison. Its v2
failures were mainly selection of the wrong historical occurrence: only 12/40
affected-scope lists exactly matched the event target and replacement, while
the blackboard delta was exact in 36/40.

## Conclusion

The data support a narrower hypothesis: an occurrence-addressed CoPE carrier
is much easier for this model to serialize correctly on the first draw than
the tested richer state-edit carriers. They do not yet establish a fair
primary-control advantage because v2 retained a mechanical path ambiguity.

The next decisive test is a new, outcome-locked v3 on disjoint object names.
All contracts must use exact event field names; the neutral path grammar must
include a non-case-specific literal example; the strict frozen analyzer must
be used without post-hoc normalization. No embodied experiment is authorized
unless both primary comparisons pass and the failure audit finds no new
contract asymmetry.
