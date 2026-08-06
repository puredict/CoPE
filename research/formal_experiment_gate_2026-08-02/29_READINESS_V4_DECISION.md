# CoPE formal readiness v4 decision

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**GO for independent synthetic X16 and development embodied-canary design;
NO-GO for reserved-state formal rollout.**

The main readiness-v3 scientific integration blocker is closed: X15 made
provider outputs drive the live semantic materializer and obtained CoPE 10/10
over two event families and five development states, with no oracle
substitution, fallback, repair, retry or controller action.

The current-host content-addressed runtime also passes its 53-check preflight.
However, fully reproducible cold rebuild remains incomplete because the exact
wheel/sdist artifact set has not been retained in a hash-locked wheelhouse or
immutable image.

Reserved states remain locked for three reasons:

1. X15 covers only replacement and cancellation, not the independent safety
   and conflict families on which X14 exposed failures;
2. compact TX failed its path contract in 10/10 X15 cells, so a neutral or
   constrained generic transaction control is needed before attributing the
   difference to CoPE semantics;
3. X15 intentionally ended before any post-interruption action and therefore
   does not yet show terminal embodied recovery.

## Immediate sequence

1. Execute the frozen 36-template X16 provider-only run without changing its
   corpus, oracle, contracts, arm order, scoring or stopping rule.
2. Freeze a development embodied-canary protocol using accepted learned output
   and zero oracle substitution; use no reserved state.
3. Add the neutral/constrained sparse transaction attribution control.
4. Only after those results and a refreshed provenance audit decide whether to
   unlock states 27--46. States 47--49 remain permanent reserve.
