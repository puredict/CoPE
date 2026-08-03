# Persistent-state scaling experiment preregistration

Date frozen: 2026-08-03 (Asia/Shanghai), before any scaling provider call.

## Core question

When a long-horizon task accumulates many persistent commitments but an
interruption changes only a small subset, does editing the affected commitment
state remain more reliable than regenerating the complete semantic state?

This is the direct test of CoPE's fixed core hypothesis. It is a
representation-fidelity and state-preservation experiment, not a policy
induction benchmark: every required semantic operation is stated in the common
rule packet.

## Frozen corpus

The corpus has 108 new common inputs: 36 matched transition programs at each of
4, 16, and 32 persistent commitments (`SCE-S04-*`, `SCE-S16-*`, and
`SCE-S32-*`). Each transition changes one to four semantic records. Larger
states add commitments, actions, progress records, restoration records, and
facts that must be preserved unchanged.

The 36 transition programs reuse the previously audited semantic families.
Therefore the new inferential factor is persistent-state scale and preservation,
not unseen transition semantics. The generator, all inputs, oracle states,
schemas, contracts and hashes were frozen before provider calls in commit
`a8e198d5bfe89d3a2fd358d8e2aea25b1f48695a`.

Preflight results:

- 108/108 four-arm common-input and normalized-request fairness checks pass;
- 432/432 oracle proposals materialize to identical semantic state plus shared
  transaction envelope;
- 36 cases occur at each frozen size `(4, 16, 32)`;
- 18 implementation/qualification tests pass;
- provider calls before freeze: zero.

## Arms

1. CoPE semantic typed delta (sparse persistent-commitment edit);
2. neutral typed delta (operation-label ablation);
3. corrected natural-path compact transaction;
4. complete semantic-state regeneration (FSR).

All arms receive byte-identical common semantic input and exclude transaction
metadata. The same trusted commit envelope supplies versions, event hashes,
processed-event records and receipts after semantic validation.

## Provider protocol

- OpenRouter model `qwen/qwen3.5-flash-02-23`;
- reasoning `none`, temperature 0, seed 20260803;
- strict JSON Schema and required-parameter routing;
- maximum prompt tokens 32,000 and maximum completion tokens 16,384 equally;
- timeout 90 seconds;
- zero retry, repair, fallback and oracle substitution;
- deterministic four-arm rotation in manifest order;
- all 432 assignments retained.

## Primary endpoint and decision

The single primary comparison is paired first-pass semantic correctness for
CoPE versus FSR on the 36 largest (`SCE-S32-*`) states. Use a two-sided exact
McNemar/sign test. There is one primary hypothesis, so no multiplicity
adjustment is applied.

PASS requires all of:

- positive paired direction (`CoPE-only > FSR-only`);
- exact `p < 0.05`;
- CoPE at least 18/36 correct at size 32;
- 108/108 complete assignments and fair four-arm groups.

Per-size accuracy, completion tokens, proposal bytes and latency are secondary.
Largest-state CoPE versus compact and neutral are descriptive representation
ablations and cannot override the primary decision.

## Routing

- PASS: prepare a development-only embodied canary using the shared envelope;
  reserved states remain locked until runtime provenance and the canary pass.
- FAIL with all arms near ceiling: the benchmark is insufficiently stressful;
  do not claim a learned CoPE advantage.
- FAIL with CoPE and FSR both poor: stop promotion and redesign the learned
  semantic generator.
- Integrity failure: invalidate the run.

No GPU, simulator, controller, development LIBERO state, or reserved state is
used. States 27--49 remain locked; states 47--49 remain permanent reserve.
