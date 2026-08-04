# Occurrence learned runner readiness audit

Date: 2026-08-04  
Runtime commit: `bb50a706f590d911cc3c51ff0d4039f2c1ad9dd1`

## Decision

**Implementation-ready; execution blocked on a secure credential and
operational smoke.** No learned formal output exists.

## Evidence

- Full regression: **601/601** tests passed.
- Frozen manifest: 40 cases, 5 arms, 200 one-draw cells.
- Runner pins manifest, contract-family, and provider-protocol hashes.
- Durable call intent precedes each request; a received response is persisted
  before materialization; resume never repeats a cell.
- Intent without response becomes
  `ambiguous_interrupted_call_no_retry` and invalidates analysis.
- Neutral outputs must contain the exact minimum write set; governed outputs
  must contain the exact sorted changed occurrence scope.
- Analyzer requires Holm-adjusted efficacy and locality gates against both
  neutral and governed controls; FSR-PC/full-replan cannot rescue either.
- A real clean-commit runner invocation without `OPENROUTER_API_KEY` exited
  with code **3**, recording zero provider calls, zero symbolic cases
  materialized, and zero simulator states indexed.

## Remaining gate

The project does not possess a securely injected credential in the server
environment. A key pasted into chat was not stored or reused. Before the
200-call run, one separately logged, outcome-independent transport/JSON smoke
must pass with the same endpoint, model, temperature, seed support, reasoning
setting, timeout, and zero-retry adapter.
