# X14 fresh-context 60-triplet preregistration

Frozen: 2026-08-03 before implementing the variant generator, inspecting
oracle qualification outcomes, or making provider calls.

## Motivation and claim boundary

X13b produced 7/12 correct CoPE, 3/12 compact TX and 0/12 FSR-PC under matched
`reasoning.effort=none`, but reused the 12 development templates after a
default-reasoning diagnostic. X14 tests whether that ordering survives fresh,
unseen context variants. It remains a synthetic N-track and cannot establish
embodied task success or cross-task generalization.

## Corpus

The 12 frozen semantic templates each receive five deterministic context
variants, yielding 60 unique `RecoveryInput` instances. Variant index `k=1..5`
changes only pre-event context and identifiers, never the event semantics:

- state version becomes `10+k`; authorized events bind to it, while the stale
  event binds to one less;
- unique event ID and world/evidence versions;
- `k` irrelevant object/commitment/goal/progress bundles are appended in
  canonical order and must be preserved;
- `k` completed public action-history records are added;
- the affected target retains a variant-specific validity deadline and, for
  `k>=3`, dependencies on the first irrelevant satisfied commitment.

Noise commitments are satisfied, have unique stable IDs, use the existing dock,
and are not event targets. No plan action is added. The generator may not change
authorization, event type, conflict flag, replacement/override target, or
ground-truth transition rule.

## Mandatory oracle qualification before provider use

All 60 variants must satisfy:

1. unique case IDs and unique canonical input hashes;
2. CoPE canonical patch, compact generic transaction and FSR-PC canonical full
   state materialize to the same post-state;
3. the common validator/compiler accepts every canonical arm;
4. triplet common-input bytes and normalized requests match;
5. maximum canonical common-input UTF-8 length stays below the frozen prompt
   budget with an explicit retained margin;
6. no provider, GPU, simulator or reserved state is used during qualification.

Any failure blocks X14 provider calls and is retained.

## Provider design

- exact X13b provider/model/contracts/validator;
- model `qwen/qwen3.5-flash-02-23`;
- `reasoning.effort=none`, temperature 0, seed 20260802;
- 4,096 completion ceiling, 90-second timeout, zero retry and zero repair;
- six fresh smoke triplets spanning no-op, replacement, authorization,
  continuity conflict, cancellation and override;
- smoke call-order offsets are balanced 2/2/2;
- all 54 remaining triplets run only if every smoke call has provider status
  `ok` and every smoke fairness check passes;
- across all 60 manifest positions, each arm is first exactly 20 times.

## Outcomes

Primary: first-pass semantic correctness, paired CoPE versus compact TX.
Secondary: FSR-PC correctness, parser/semantic failure taxonomy, unauthorized or
stale edits, progress/continuity errors, tokens, bytes and latency.

The 60 cells are clustered within 12 semantic templates. Cell-level rates are
descriptive. The inferential unit is the base template: compute each arm's
correct rate over its five variants, then count templates with positive,
negative or tied CoPE-minus-compact difference. Any exact sign calculation uses
only non-tied template differences and is labelled exploratory unless separately
locked before provider use.

## Decision

- GO toward true-clean embodied preparation only if CoPE exceeds compact TX in
  both total correct cells and more base templates than it loses, has no new
  safety-failure excess, and the effect is not confined to no-op/version cases.
- Tie or compact advantage: CoPE-specific learned-factorization claim fails.
- All arms low or smoke failure: stop before embodied states.
- X14 alone never unlocks states 27--49; provenance must also be regenerated.
