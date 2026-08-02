# X18 v1 differential-fuzz result and root cause

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**FAIL.** The decomposed validator is not yet an exact accept/reject substitute
for the event-bound canonical validator.

The frozen run produced:

- 12/12 clean controls accepted by both validators;
- 3,000 assigned mutants;
- 2,997/3,000 candidates actually changed (three multi-mutation sequences
  cancelled themselves);
- exact validator rejected 2,997/3,000;
- decomposed validator rejected 2,973/3,000;
- decision parity 2,976/3,000;
- caller pre-state unchanged 3,000/3,000.

All 24 decision mismatches were exact-reject/decomposed-accept. No mismatch was
hidden or recoded as a crash.

## Root-cause audit

The 24 false accepts reduce to three structural invariants that the exact
canonical comparison enforces and the decomposed predicates omitted:

1. commitment record order was changed by list reversal;
2. entity record order was changed by list reversal;
3. an extra field was added to the affected commitment record.

The decomposed implementation converts record lists to ID-keyed dictionaries,
which discards order. For affected existing commitments it checks required
field values but did not reject surplus keys. These are representation
canonicality holes, not evidence that the candidate was semantically correct
under the frozen full-state-v2 contract.

The three unchanged assignments were mutation-generator cancellations:
duplicate-then-delete of the same list element, or reversing the same list
twice. They remain in the raw table and make the preregistered v1 gate fail.

## Consequence

This result blocks any claim that the current eight-predicate validator is
extensionally equivalent to the exact validator. It does not falsify the core
commitment-editing hypothesis, but it narrows the assurance claim and confirms
that the reserved embodied states must remain locked.

The repair must add explicit canonical record ordering and exact record-field
shape checks without importing or calling the oracle post-state constructor.
The observed seed will be rerun only as a regression. A separately frozen
holdout seed is required for the post-fix decision.
