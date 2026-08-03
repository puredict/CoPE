# X16 provider-run readiness decision

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**READY_FOR_PROVIDER_RUN, but not executed and not authorized for reserved or
embodied states.**

The semantic corpus satisfies the requested pre-provider gates: 36 independent
templates, balanced required-family coverage, four distinct dispositions,
frozen equal-information arm contracts, frozen oracle and validator, balanced
seeded arm order, frozen scoring/exclusion/statistical rules, an exact power
sensitivity analysis, and complete oracle/fairness/leakage qualification.

Readiness is limited to a future provider-only synthetic X16 run with the exact
freeze ledger. Before any call, the runner must verify every locked SHA-256,
rerun qualification without modifying an input, confirm credentials without
printing them, and confirm zero use of reserved states. Any hash mismatch or
qualification failure changes the decision to NO-GO and requires a newly named
freeze.

## Gates

| Gate | Result | Evidence |
|---|---|---|
| At least 30 independent semantic templates | PASS | 36 cases, 36 unique logic signatures |
| Required family balance | PASS | 17 required families × 2, plus 2 compound cases |
| APPLY / NO_OP / REJECT / ABSTAIN present | PASS | 22 / 4 / 6 / 4 |
| Same information for all arms | PASS | 108/108 common and normalized hashes |
| Three representations express same transition | PASS | 108/108 oracle state equality |
| Validator accepts all canonical oracles | PASS | 108/108 |
| Hidden answer leakage absent | PASS | 108/108 key scans and explicit field audit |
| Arm-specific semantic information absent | PASS | only output representation differs |
| Arm-order randomization frozen and balanced | PASS | seed 20260803; 12/12/12 in every position |
| Seed, prompt, scoring, exclusions, primary test frozen | PASS | preregistration, contracts, algorithm, ledger |
| Power/sensitivity precomputed | PASS | exact threshold and 16-scenario power grid |
| Provider / GPU / simulator / reserved states unused | PASS | local status: all zero/false |

## Statistical adequacy

X16 can produce a statistically meaningful result only for a sufficiently
strong paired asymmetry. Six discordant templates is the mathematical minimum
for two-sided `p < 0.05`, requiring 6–0. With 17 discordances the threshold is
13–4; with all 36 discordant it is 25–11. The design should therefore be
described as capable of confirming a strong representation advantage, not as
well powered for a small advantage. A nonsignificant result must remain
inconclusive/negative; cell counts or secondary family slices cannot override
the primary exact test.

## Explicit non-authorizations

This decision does not authorize OpenRouter in the current stage, model
training, implementation modification, simulator use, robot actions, X15
development-state execution, or any reserved-state access. Existing X14 and
readiness results remain untouched.
