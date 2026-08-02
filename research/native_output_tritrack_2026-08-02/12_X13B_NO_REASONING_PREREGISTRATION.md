# X13b matched no-reasoning control preregistration

Frozen: 2026-08-03 before implementation or provider calls.

## Motivation

X13 recovery smoke produced 2/4 correct CoPE, 2/4 correct compact TX and 0/4
FSR-PC, with FSR-PC reporting 114,062 completion tokens across four calls.
OpenRouter's current model metadata says `qwen/qwen3.5-flash-02-23` supports the
`reasoning` parameter and reasoning is not mandatory. Official documentation
counts reasoning tokens as output tokens.

## Single controlled change

Repeat the exact 12-case X13 runner and smoke gate with one additional identical
wire field in every arm:

```json
{"reasoning":{"effort":"none"}}
```

Everything else remains unchanged: model, endpoint, common input, contracts,
temperature 0, seed 20260802, 4,096 completion ceiling, 90-second timeout, zero
retry/repair, call-order rotation, validators and output directory exclusivity.

The first four triplets run as smoke. Expansion occurs only if all 12 smoke
calls have provider status `ok` and all fairness checks pass. Method-invalid
output alone does not stop expansion.

## Interpretation

- If FSR-PC budget failures disappear, X13 primarily diagnosed default
  reasoning-mode interaction rather than representation alone.
- If FSR-PC remains disproportionately invalid/over-budget, the sparse-output
  factorization signal strengthens.
- CoPE must beat compact TX to support a CoPE-specific learned-generation claim.
- Any result remains a repeated-case configuration diagnostic and does not
  unlock reserved embodied states without a larger fresh paired corpus and
  true-clean provenance PASS.
