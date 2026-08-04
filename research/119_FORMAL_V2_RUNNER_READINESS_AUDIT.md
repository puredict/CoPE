# Formal v2 runner readiness audit

Date: 2026-08-04  
Runtime commit: `821dad8fb947697f03aff4f2e99790abe6e2e59b`  
Manifest: `manifests/sequential_formal_40x5x2_v2.csv`  
Manifest SHA-256: `9788ceff3c4366e5928bef028cc5e24c594dc30d6c8a559c2403b78bb5a858e5`

## Decision

**PASS for implementation readiness; BLOCKED for formal execution until the
credential and smoke gates are satisfied.** This is not an experimental
outcome and does not change the current paper-level NO-GO/HOLD decision.

## Frozen v2 design

- 40 complete two-event sequence units on LIBERO-10 task 0, states 10--29.
- Five arms: CoPE, neutral JSON patch, governed affected-scope delta, FSR-PC,
  and full replan.
- Two calls per arm and no retries: 400 planned provider calls.
- CoPE must pass co-primary efficacy and locality comparisons against both
  neutral and governed controls. A secondary arm cannot rescue either failure.
- The v1 runner and v1 evidence remain untouched.

## Executed checks

1. The complete test suite passed: **586/586** tests.
2. The credential-free request preflight built **400/400** audited requests and
   made **0** provider calls and **0** simulator-state reads.
3. All **80/80** sequence-event groups contained exactly five arms, exactly one
   common `input_sha256`, and exactly one arm-normalized request hash.
4. Each arm contributed exactly 80 request rows.
5. Running the real v2 runner without `OPENROUTER_API_KEY` exited with code 3
   before suite construction or initial-state indexing, recording
   `provider_calls=0` and `simulator_states_indexed=0`.
6. The runner rejects a dirty worktree and pins the manifest, controller,
   output-contract, and provider-protocol hashes.
7. The only authorized formal state IDs are 10--29. Task 1 state 33 was not
   retried, and task 1 states 34--49 were not indexed.

## Prompt-size observation

Median serialized request sizes were 5,375.5 bytes (CoPE), 5,640.5 (neutral),
5,942.5 (governed), 5,371.5 (FSR-PC), and 5,480.5 (full replan). These differ
because the frozen output contracts differ; all common recovery inputs and
provider settings are matched. Token/byte differences must be reported rather
than treated as an efficacy explanation after outcomes are observed.

## Remaining execution gate

Formal calls may start only after a credential is supplied through the named
environment variable without logging it and a separately recorded smoke call
passes the same adapter/model/zero-retry configuration. No credential was
stored or reused in this audit.
