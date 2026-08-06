# Full-state-v2 materialization and equivalence preflight preregistration

Date frozen: 2026-08-02 (Asia/Shanghai)

Pre-implementation parent commit:
`961b280e6a058bf402564f0cfbf86c628140bc6c`

## Question

Can an accepted Oracle-CoPE typed transition be independently checked and
materialized into the exact same canonical full-state-v2 representation used by
a native Oracle-FSR rewrite, with the same validator and compiler?

This is a CPU-only state-equivalence preflight. It does not load LIBERO, inspect
reserved initial states, call a provider, or establish embodied recovery.

## Frozen cases

`01_PREFLIGHT_CASES.csv` contains four positive cases:

1. replacement with cream cheese completed, alphabet soup replacement,
   semantic previous version 0;
2. replacement with butter completed, milk replacement, previous version 5;
3. cancellation with cream cheese completed, previous version 0;
4. cancellation with butter completed, previous version 3.

The nonzero versions, alternate sibling, and alternate replacement prevent the
implementation from passing only the original task-1 example.

`manifests/semantic_oracle_pilot_v1.csv` separately reserves state 25 for the
future replacement pilot and state 26 for cancellation. Its rows are marked
`reserved_uninspected`; it is not a formal atlas and contains no invented state
digest.

## Frozen invariants

For every positive case:

- the typed transition is accepted, oracle-selected, and provider-free;
- receipt before/after hashes match the serialized states and audit record;
- receipt event, operation, target, lifecycle mode, grounding, lineage, source,
  and priority match the authorized event;
- native FSR and materialized CoPE states both pass the same full-state-v2
  validator;
- the two semantic states are byte-canonical equal and have the same stable
  hash;
- the same compiler produces the same prompt or HALT directive;
- materialization emits no controller or simulator action.

Focused negative tests must reject at least: provider-called receipts, wrong
event IDs, corrupted transition hashes, wrong lifecycle modes, wrong grounding,
and wrong override lineage.

## Decision rule

The CPU materialization gate passes only if:

1. all four assigned rows are emitted exactly once and every invariant passes;
2. every focused negative receipt is rejected;
3. the unchanged 123-case corruption audit remains 123/123;
4. CoPE atomicity remains 67/67;
5. the full repository regression is clean.

Passing closes only the shared materialization/compiler CPU gate. It does not
close the real provider, simulator-predicate validator, embodied runner,
checkpoint, formal atlas/provenance, or analysis-stack gates, and does not
authorize state-25/state-26 rollouts by itself.

## No-retuning rule

Cases, expected invariants, and reserved-state allocation may not be changed
after the preflight output is observed. A program defect requires a versioned
superseding result while retaining the original artifact.
