# X18 decomposed-validator differential fuzzing preregistration

Frozen: 2026-08-03 before running the mutator.

## Question

Do the exact event-bound validator and the eight-predicate decomposed validator
make the same accept/reject decision beyond the hand-authored single-fault and
order-1-to-3 composition suites?

## Frozen experiment

- corpus: the 12 frozen public synthetic native-output cases;
- clean control: canonical post-state for every case must be accepted by both;
- seed: `20260803`;
- 250 independently generated candidates per case, 3,000 total;
- 1--4 mutations per candidate;
- mutation families: scalar replacement, dictionary key deletion/addition,
  list-element deletion/duplication, and list reversal;
- the mutator is generic over the JSON tree and does not select expected
  predicate groups or inspect validator outputs;
- compare only final accept/reject decisions; retain exceptions and decomposed
  attribution for diagnosis;
- verify every candidate differs from its canonical control and the caller's
  pre-state remains unchanged.

## Frozen gate and interpretation

PASS requires 12/12 clean acceptance, 3,000/3,000 changed candidates,
3,000/3,000 exact/decomposed decision parity, and no caller-state mutation.
Any mismatch is retained and makes the gate FAIL.

A PASS is robustness evidence only for this deterministic synthetic mutation
distribution. It does not prove semantic completeness, learned generation,
embodied safety, or CoPE-specific advantage. A FAIL blocks the decomposed
assurance argument until the mismatch is understood; it does not by itself
falsify the core commitment-editing hypothesis.
