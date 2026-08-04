# Next critical experiment: noninferiority and efficiency replication (draft)

Status: design draft only; not launched. Date: 2026-08-04.

## Question

Does an occurrence-addressed CoPE output match the exact recovery reliability
of a field-complete generic transaction while reducing generated tokens,
latency, and output size across models and unseen task vocabularies?

## Proposed design

- Primary arms: CoPE and neutral generic transaction.
- Diagnostic arms: full replan and FSR-PC. Governed delta is retained only if
  its ordering convention is represented canonically by code rather than
  requiring the model to sort records.
- At least three independently selected model families or sizes, declared
  before outcomes; no model is dropped for poor results.
- At least 120 paired cases per model, split across replacement, cancellation,
  restoration, repeated-grounding, and stale-event families.
- Disjoint vocabulary and event templates from v1--v3.
- One draw, temperature 0, zero semantic repair, fixed retry policy, balanced
  arm position, identical common input within each pair.

## Co-primary gate

1. Exact recovery noninferiority of CoPE versus neutral with a margin of 5
   percentage points, evaluated per model and in a model-stratified aggregate.
2. At least 50% median reduction in completion tokens and proposal bytes.
3. At least 25% median latency reduction.
4. No excess history, invariant, or unsafe-directive failures.

Multiplicity adjustment, confidence-interval method, sample-size calculation,
provider/model versions, contracts, manifests, and analysis code must be frozen
before calls. Model-specific superiority is exploratory and cannot substitute
for aggregate noninferiority.

## Embodied unlock

Only a passed replication unlocks a separately preregistered embodied study.
That study's primary outcomes should be task completion, completed-step
regression, extra low-level actions, persistent-history corruption, and
end-to-end recovery latency under repeated interruptions. CoPE, neutral edit,
and full replan must all receive the same perception and action substrate.
