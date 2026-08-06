# Local-model tri-arm diagnostic preregistration

Frozen: 2026-08-03, before inspecting any model outputs.

## Purpose and non-claim boundary

The frozen primary X13 provider (`qwen/qwen3.5-flash-02-23` through
OpenRouter) cannot run because neither the workstation nor the experiment
server has a provider credential. This diagnostic uses the independently
downloaded `Qwen/Qwen2.5-0.5B-Instruct` checkpoint solely to test whether the
real, non-mocked three-arm generation/evaluation path is operational and to
measure an intentionally weak model's native failure modes.

Its outcomes are **not** substituted for X13, do not unlock reserved LIBERO
states 27--49, and do not support a learned-controller or embodied-recovery
claim. A poor result is informative about model capacity/prompt difficulty,
not evidence against representation factorization. A good result is only a
pipeline and feasibility diagnostic.

## Frozen design

- exact X13 12-case manifest, schemas, fairness audit, common input, validator,
  call-order rotation, and smoke-to-expansion gate;
- arms: CoPE typed patch, generic compact transaction, FSR-PC full state;
- model: `Qwen/Qwen2.5-0.5B-Instruct`, ModelScope artifact, local inference;
- deterministic greedy decoding, temperature 0, seed metadata 20260802;
- maximum 2048 completion tokens, 180-second call timeout;
- zero retries and zero repairs;
- OpenAI-compatible localhost transport; no model output is executed as a
  robot command;
- expansion occurs only when every smoke provider call returns and fairness
  passes. Invalid model syntax/semantics does not itself stop expansion.

## Required reporting

Retain per-call output hashes, parser/semantic outcomes, proposal bytes,
token counts, latency, failure taxonomy, run status, exact command, git commit,
checkpoint file SHA-256, and result-file checksums. Clearly label every table
and conclusion `NON-PRIMARY LOCAL-MODEL DIAGNOSTIC`.
