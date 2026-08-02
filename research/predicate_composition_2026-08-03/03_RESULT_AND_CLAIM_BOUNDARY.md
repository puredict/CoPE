# X17 result: decomposed predicates compose cleanly through third order

Date: 2026-08-03 (Asia/Shanghai)

## Bottom line

The decomposed validator rejected all 64 white-box candidates containing one,
two, or three isolated predicate-level errors. For every candidate, the
observed violated-group set exactly matched the component mutations, with no
missing or spurious group.

All eight predicate groups now have an isolated singleton for which removing
that group alone would produce a fail-open. This resolves the X16 ambiguity
where goal consistency and restoration/entity had zero unique catches only
because prior faults were correlated.

## Audited result

| Check | Result |
|---|---:|
| Canonical clean states accepted | 12/12 |
| Single-error candidates | 8/8 |
| Two-error combinations | 21/21 |
| Three-error combinations | 35/35 |
| Total changed noncanonical candidates | 64/64 |
| Decomposed validator rejected | 64/64 |
| Exact validator rejected | 64/64 |
| Exact expected/observed predicate attribution | 64/64 |
| Predicate groups with singleton ablation fail-open | 8/8 |
| Independent CSV-only audit | 15/15 |
| Focused tests | 3 passed in 0.14 s |
| Complete repository regression | 428 passed in 47.21 s |

No provider, credential, LLM, GPU, simulator, robot, or reserved LIBERO state
27--49 was used.

## What was composed

Seven isolated edits were applied to the same correct replacement state:
extra version advance, wrong target lifecycle, extra goal atom, dropped
progress, missing plan, missing replacement entity, and unrelated sibling
corruption. Every combination of size one through three was enumerated.

The eighth singleton used a rejected low-authority event with an illegal
evidence change, isolating authorization/no-op behavior.

Each non-authorization mutation appeared in 22 candidates: once alone, six
pairs, and fifteen triples. The authorization mutation appeared once because it
requires a different event contract.

## Interpretation

The result strengthens two engineering claims:

1. the eight checks are independently necessary on at least one explicit
   counterexample;
2. their violation reports compose without masking or cross-talk for the frozen
   order-1 to order-3 construction.

It does not establish formal soundness or completeness. The mutations were
white-box and deliberately chosen to isolate known checks, so exact attribution
is partly a construction property. The test does not explore adversarial
edits designed to exploit missing predicates, semantic equivalences, novel
schema fields, or long-horizon state growth.

## Claim boundary

Supported:

> Eight named event-contract predicate groups independently catch targeted
> counterexamples and compose correctly through third-order deterministic
> mutations on the frozen N-track state.

Not supported:

- these eight groups are complete for arbitrary robot tasks;
- third-order composition covers adaptive adversaries;
- white-box state mutations represent learned-model frequencies;
- passing candidate validation predicts embodied recovery success.

The next evidence increase should come from an independently generated or
property-based candidate corpus, not more hand-picked mutations of the same
replacement state.

