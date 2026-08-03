# Live-v2 transaction-fair control canary preregistration

Date frozen: 2026-08-03 (Asia/Shanghai), before v2 provider calls or simulator
execution.

## Purpose

Test the corrected live semantic interfaces before any comparative embodied or
reserved-state experiment. The canary separates a sparse-edit advantage from
CoPE operation-name advantage and removes model-authored transaction metadata
from compact and FSR-PC.

## Frozen implementation

- implementation commit:
  '3c87d29ae7c6c2496af940db1e0d11b852710576';
- focused tests: 61 passed;
- full cold-environment regression: 487 passed;
- four arms:
  - CoPE sparse patch with 'Override'/'Expire';
  - neutral-label sparse patch with 'N01'/'N02';
  - corrected generic compact path writes over semantic fields only;
  - FSR-PC complete semantic state without schema/state/evidence metadata;
- the same trusted finalizer and shared transaction envelope own state version,
  evidence version, processed event ID, event hash, payload hash and receipt.

## Frozen run

- LIBERO-10 task 1, development state 0 only;
- replacement and cancellation from the same unchanged physical milestone;
- four provider calls per event, eight calls total;
- model 'qwen/qwen3.5-flash-02-23', reasoning none, temperature 0,
  seed 20260802, completion limit 4096, timeout 90 seconds;
- zero retry, repair, fallback and oracle substitution;
- CPU only in the cold-verified Python environment;
- Phase A only: no post-event controller action;
- new output:
  'research/live_v2_control_canary_2026-08-03/state0_openrouter_v1'.

## Gate

The interface/fairness gate passes only if:

1. all eight calls return OK with zero retries;
2. each four-arm triplet has identical common input, normalized request and
   provider settings hashes;
3. CoPE is parser-valid and semantic-correct on both events;
4. neutral-label sparse is parser-valid and semantic-correct on both events;
5. no arm output supplies transaction metadata and the trusted CoPE envelope
   passes both events;
6. the live predicate packet remains canonical and the simulator/action counts
   are unchanged;
7. no fallback, oracle substitution or reserved state occurs.

Corrected compact and metadata-free FSR-PC semantic correctness are diagnostic
at this canary stage. A schema-valid semantic failure is retained as a method
failure and is never repaired or replaced. The result determines which valid
arms enter a matched-replay development embodied canary.

States 27--49 remain locked; states 47--49 remain permanent reserve.
