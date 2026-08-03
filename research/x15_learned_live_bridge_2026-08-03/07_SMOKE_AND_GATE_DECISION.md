# X15 smoke and gate decision

Date: 2026-08-03 (Asia/Shanghai)

## Credential and smoke status

`OPENROUTER_API_KEY` was not available in the process environment. Per the X15
preregistration, no provider result was fabricated and no model call, simulator
state indexing, controller action, or state-0 smoke was run.

- state-0 replacement smoke: NOT RUN (credential unavailable)
- state-0 cancellation smoke: NOT RUN (credential unavailable)
- development states 1--4: NOT AUTHORIZED / NOT RUN
- reserved states 27--49: NOT TOUCHED
- fallback or oracle substitution: none executed

## Decision

**Expansion to development states 1--4: NO.** The mandatory retained state-0
provider-backed triplets do not exist.

**X15 gate: NOT SATISFIED.** Implementation, adversarial tests, fairness guards,
and regression tests pass, but the empirical provider-backed state-0 condition
is unevaluated. This is a credential blocker, not a semantic success or failure.

Replacement and cancellation must remain separate in any future result. X14
CoPE replacement was 0/5; no pooled score may conceal that family.
