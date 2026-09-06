# X20 canonical record-order policy preregistration

Frozen date: 2026-08-03 (Asia/Shanghai)

## Question

X18 v2 left 14 exact-reject/decomposed-accept divergences caused only by
reversing top-level `commitments` or `entities` record lists. The record order
is not used by the decomposed semantics, but canonical bytes and receipt hashes
are order-sensitive. X20 chooses an explicit protocol policy.

## Frozen policies

1. **Strict input order:** records must already be in the protocol's canonical
   stable-key order; otherwise reject.
2. **Normalize before validation/publication:** after schema and stable-key
   checks, sort records deterministically, then validate and hash the normalized
   state. Receipts must name the normalization version.

The candidate canonicalizer covers only unordered record collections:

- `commitments` by string `id`;
- `entities` by string `id`;
- `progress_ledger` by string `milestone_id`.

It does not reorder plan actions, pending restorations, grounding arguments, or
goal atoms. Missing/non-string keys, duplicate keys, non-list collections, or
non-mapping records fail closed. The function must deep-copy and never mutate
caller state.

## Frozen tests

- 12 legacy clean states: normalization succeeds, is idempotent, preserves
  decomposed semantic acceptance when both stored pre-state and candidate are
  normalized, and produces a versioned deterministic hash;
- 14 X18 reorder candidates reconstructed from the frozen rows: normalized
  bytes/hash equal their corresponding normalized clean state;
- strict policy accepts all normalized clean states and rejects all 14 reversed
  provider candidates;
- normalize policy accepts and canonicalizes all 14;
- duplicate key, missing key, non-string key, non-list collection, and
  non-mapping record faults reject with caller input unchanged;
- 20 warm-ups and 1,000 timed normalizations per clean state, rotating case
  order; report per-case median and aggregate median. Frozen diagnostic gate:
  aggregate median below 1 millisecond on the assigned CPU.

## Decision rule

Prefer normalization if all semantic/hash/idempotence/fault gates pass and the
timing gate passes. Otherwise prefer strict rejection. This decision applies to
future protocol-v2 artifacts only; do not silently reinterpret existing hashes.

Passing is an engineering result on small states, not a scalability or robot
claim. Use no provider, credential, LLM, GPU, simulator, robot, or LIBERO state
27--49.

