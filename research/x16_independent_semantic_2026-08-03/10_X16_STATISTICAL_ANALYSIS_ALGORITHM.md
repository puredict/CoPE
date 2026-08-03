# X16 frozen statistical analysis algorithm

## Input retention and scoring

Read exactly 36 manifest case IDs and exactly one result row for each
`case_id × arm`. Refuse analysis if IDs are missing/duplicated, the freeze
ledger fails, qualification is not PASS, a fairness flag is false, a retry or
repair occurred, or an unregistered arm exists. Do not delete provider errors,
timeouts, parser failures, or invalid proposals.

For each cell, set `correct = 1` only when all frozen correctness conditions in
the preregistration pass; otherwise set it to 0. For each case form the paired
values `(CoPE_correct, compact_TX_correct)`.

## Primary calculation

1. Count `b = Σ[CoPE=1 and compact=0]`.
2. Count `c = Σ[CoPE=0 and compact=1]`.
3. Let `d = b + c`.
4. If `d = 0`, set `p = 1`.
5. Otherwise set
   `p = min(1, 2 * Σ_{k=max(b,c)}^d choose(d,k) / 2^d)`.
6. Report `b`, `c`, `d`, the two arm rates over all 36 templates, their paired
   risk difference, and this two-sided exact p-value.
7. Declare confirmatory CoPE superiority only if `p < 0.05`, `b > c`, and the
   CoPE unsafe-mutation count is not greater than compact TX's.

This is the exact McNemar test. Each template contributes at most one paired
observation. No context, family label, operation, state record, or token is an
additional statistical unit.

## Confidence interval and secondary reporting

Report a 95% paired bootstrap interval for the risk difference by enumerating
or deterministically sampling complete templates with replacement using seed
20260803 and at least 100,000 resamples. The interval is descriptive; it does
not replace the exact primary test. Also report raw correctness and failure
counts by frozen primary family and disposition. FSR-PC and cost results are
secondary. If both CoPE-vs-FSR-PC and compact-TX-vs-FSR-PC exact tests are given
inferential labels, apply Holm correction to those two p-values.

## Exact sensitivity algorithm

For every possible discordant count `d=1..36`, search the smallest CoPE-only
win count `b > d/2` whose two-sided exact p-value is below 0.05. Conditional
power at an assumed CoPE win probability `π` among discordant templates is the
sum of the upper and lower exact-binomial rejection tails. Unconditional power
at discordance rate `q` averages that conditional power over
`D ~ Binomial(36,q)`. The frozen numeric output is
`07_X16_POWER_SENSITIVITY.csv`.

The qualification program contains the executable standard-library
implementation of the exact p-value, threshold, conditional-power, and
unconditional-power calculations.
