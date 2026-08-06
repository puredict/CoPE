# CoPE vs FSR-PC native-output N-track preregistration

Frozen date: 2026-08-02 (Asia/Shanghai)

## Scope and claim boundary

This is a CPU/offline generation-and-validation experiment. It does not run a
robot, simulator, controller, planner, or embodied rollout, and it does not
read LIBERO states 25--49. The only question is whether one frozen model, given
the same canonical `RecoveryInput`, more reliably emits (A) a CoPE typed minimum
patch or (B) an FSR-PC canonical full-state-v2 rewrite.

A higher CoPE valid rate may support generation factorization, inductive-bias,
or assurance claims only. It cannot establish stronger execution expressivity
or embodied task success. Equivalent results weaken the broad necessity claim.
If oracle transitions pass but both native arms are poor, attribution is to
generation/provider behavior, not a controller.

## Frozen corpus

`01_CASE_MANIFEST.csv` assigns 12 public, non-reserve cases. They cover no-op,
cancel sibling, replace pending target, activate/release override, release after
world change, wrong-source revoke, stale version, idempotence, irrelevant
sibling change, and valid/invalid executing-action continuity. The two controls
derived from the prior 123-case contract are legal no-op/diagnostic-isolation
extensions only; malformed reserved examples are not read.

The first four pairs are smoke cases. The remaining eight pairs run only when
every smoke pair passes the byte/fairness audit and all eight provider calls
return without outage or timeout. Expansion does not depend on either method's
validity or correctness.

## Frozen provider and sampling policy

- Adapter: non-fake OpenAI-compatible chat-completions adapter.
- Provider endpoint: OpenRouter-compatible endpoint supplied on the command line.
- Model/version: `qwen/qwen3.5-flash-02-23`.
- Temperature: `0.0`.
- Seed policy: fixed integer `20260802` for every arm and case.
- Maximum completion tokens: `4096` for both arms.
- Maximum prompt budget: `12000` for both arms.
- Sampling: one call per arm/case; no best-of-N.
- Retry budget: zero.
- Repair/feedback budget: zero.
- Timeout: 90 seconds per call.
- Calls are paired in the fixed order CoPE then FSR-PC; this order is a known
  limitation and is retained in the audit.

Credentials are read only from the named environment variable. Credentials,
authorization headers, and response bodies are not written to research reports.
The raw provider envelope is represented by SHA-256 only.

## Fairness contract

The canonical `RecoveryInput` payload and its byte serialization must be
identical within every pair. The provider-visible request must be identical
after replacing only the arm-specific output-contract message with one sentinel.
Model, temperature, seed, token ceiling, timeout, retry, and repair budgets must
match. The patch arm receives no state outside the pre-state already embedded in
the common input. Any pair failing these checks is excluded from method-validity
interpretation but retained in the assigned results.

Each response first enters its arm-specific parser. A parsed CoPE patch is
atomically materialized; the FSR-PC response is parsed as full-state-v2. Both
then enter the same event-bound canonical validator/compiler exactly once.
Provider `controller_prompt` is not accepted by either parser and is never run.
The validator is frozen independently of model output and is not relaxed after
observing failures.

## Outcomes

Primary descriptive outcomes are first-pass valid rate and semantic correctness.
Required decompositions are unauthorized/stale edit, progress corruption,
continuity error, prompt/completion tokens, latency, validator calls, provider
outage/timeout, parser failure, and semantic-validator failure. Repair success is
reported as `not_enabled` because the frozen common repair budget is zero.

No null-hypothesis superiority test is planned for 12 pairs. Counts and rates are
pilot estimates only. All assigned calls remain in the table; provider outage
and timeout are reported separately from method-invalid output.

## Stop and interpretation rules

1. Missing credentials stop before provider calls and produce no experimental
   validity claim.
2. Any smoke fairness mismatch or provider outage/timeout stops expansion.
3. Method-invalid smoke output does not stop expansion.
4. CoPE > FSR-PC permits only factorization/assurance language.
5. CoPE = FSR-PC weakens the broad necessity claim.
6. Oracle controls correct with both native arms low implies generation/provider
   failure; it is not controller evidence.
