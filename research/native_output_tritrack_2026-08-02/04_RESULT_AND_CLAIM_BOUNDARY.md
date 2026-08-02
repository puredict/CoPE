# X13 result: tri-arm matched-provider track is ready, but no learned result exists

Date: 2026-08-02 (Asia/Shanghai)

## Decision

The earlier two-arm CoPE-vs-FSR-PC provider design is superseded. Any future
matched-provider N-track must include all three arms:

1. CoPE typed minimum patch;
2. generic compact path/value transaction;
3. FSR-PC canonical full-state-v2 rewrite.

This correction is required by X11--X12: a generic transactional carrier was
semantically equivalent on the frozen cases, and its compact executable output
was smaller than FSR-PC on 12/12. Omitting it would make CoPE look stronger by
comparison only with an already-dominated full-state baseline.

## What actually ran

- 12 frozen public-synthetic case triplets, 36 assigned arm cells;
- identical model, sampling, timeout, retry, repair, and common input settings;
- normalized request-hash fairness audit;
- three independent parsers/materializers feeding one common semantic
  validator/compiler;
- 36 mocked canonical transport calls, clearly marked `test_only`;
- credential preflight for the assigned OpenRouter-compatible provider;
- focused tests and the complete repository regression suite;
- CSV-only independent audit that imports no CoPE implementation.

No GPU, simulator, robot, controller rollout, or reserved LIBERO state 27--49
was used.

## Audited results

| Check | Result | Interpretation |
|---|---:|---|
| Fair common-input/request triplets | 12/12 | hashes match within every tri-arm case |
| Balanced first call position | 4/4/4 | each arm is first exactly four times |
| Mocked canonical transport cells | 36/36 | all three parser/materializer paths reach the common validator correctly |
| Provider-assigned cells | 36 | full ledger retained |
| Configuration-blocked cells | 36/36 | `OPENROUTER_API_KEY` unavailable |
| Actual learned-provider calls | 0 | no network/model output was produced |
| Method-evaluable learned cells | 0 | **not** a 0% success result |
| Independent CSV-only audit | 15/15 | PASS |
| Focused tests | 26 passed | tri-arm/provider/compact tests |
| Complete regression | 406 passed | 46.62 seconds |

The first complete-regression attempt lost its SSH connection after printing
17%; it supplied no pass/fail conclusion. A fresh run then completed with 406
passes. The disconnect is treated as transport interruption, not a test failure
or a partial success.

## What the mocked result proves—and does not prove

The 36/36 mocked control establishes wiring: when each arm receives its own
canonical representation of the same correct post-event state, its parser and
materializer produce a state accepted by the shared validator/compiler.

It does **not** measure whether the learned provider can generate those
representations. The provider ledger contains no responses, token counts,
latencies, parser outcomes, or semantic outcomes. Therefore there is currently
no learned ranking among CoPE, compact TX, and FSR-PC.

## Claim boundary after X13

Safe claim now:

> A preregistered, same-provider, same-input tri-arm evaluation path exists and
> passes fairness and canonical transport controls. Real evaluation is blocked
> solely at credential configuration, before any provider call.

Unsafe claims:

- CoPE generates more reliably than compact TX or FSR-PC;
- any arm has 0% or 100% learned success;
- mocked controls are model samples;
- representation correctness implies embodied recovery success;
- CoPE has unique sparse expressivity or universal size advantage.

## Next execution rule

When a legitimate credential is available, run exactly the frozen smoke gate.
Do not change the model, prompts, budgets, manifest, order, or scoring after
seeing outputs. Expansion is allowed only under the preregistered availability
and fairness gate. Until then, the useful work is to expand and audit the case
corpus offline, not to fabricate provider outcomes.

