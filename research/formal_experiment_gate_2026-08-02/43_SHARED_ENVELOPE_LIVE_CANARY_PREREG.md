# Shared-envelope live Phase-A canary preregistration

Date frozen: 2026-08-03 (Asia/Shanghai), before canary provider calls or
simulator execution.

## Purpose

Verify that a provider-selected CoPE semantic transition from a real live
LIBERO predicate packet can be committed by the shared trusted transaction
envelope without emitting an action or changing simulator state.

This is a development-only integration canary, not a formal accuracy study.

## Frozen implementation

Commit `fe2aae5effd38a7ba2038abebd734608b51a6bea` adds the live adapter:

- provider selects only the existing CoPE `Override` or `Expire` semantic patch;
- any model-generated state version, evidence version, processed-event record,
  event hash, or receipt is rejected;
- trusted envelope checks base version and idempotence, increments state version,
  binds evidence version to the live world version, and hashes the complete
  event into the processed-event record;
- shared semantic-state and transaction-metadata hashes are retained separately.

Thirty-seven focused live-semantic and shared-envelope tests pass, including rejection of
model-generated transaction metadata and duplicate stable IDs.

## Frozen canary

- LIBERO-10 task 1, development init state 0 only;
- one replacement and one cancellation event after the previously frozen
  physical milestone;
- real production predicate packet bound to RGB observation, simulator state,
  policy step, event ID, and producer commit;
- three existing provider arms per event, six calls total;
- model `qwen/qwen3.5-flash-02-23`, reasoning none, temperature 0,
  seed 20260802, max completion 4096, timeout 90 seconds;
- zero retry, repair, fallback and oracle substitution;
- CPU-only Phase A (`CUDA_VISIBLE_DEVICES` empty);
- cold-verified venv `/home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1`;
- output written to a new absent directory under `research/`.

## PASS rule

PASS requires both event triplets to satisfy all of:

- all three provider calls OK and same common-input/settings hashes;
- CoPE parser, semantic validator and oracle-equivalence checks pass;
- shared envelope pass true;
- transaction metadata model generated false;
- trusted transaction metadata contains exactly the current event and advances
  version/evidence correctly;
- production predicate validator non-fake and live outcome canonical;
- simulator state unchanged during Phase A;
- post-interruption controller action delta exactly zero;
- no fallback or oracle substitution.

Compact and FSR correctness are diagnostic and cannot veto a valid CoPE canary.
Any integrity/provider failure yields FAIL; no retries are allowed.

## Safety

Only development state 0 may be indexed. States 27--49 remain locked and
unread; states 47--49 remain permanent reserve. A PASS permits formal
preregistration, not automatic consumption before that preregistration is
frozen.
