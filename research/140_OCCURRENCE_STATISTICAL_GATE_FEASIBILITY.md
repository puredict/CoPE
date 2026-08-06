# Occurrence statistical gate feasibility audit

Date: 2026-08-04

## Decision

**The 40-pair co-primary gate is arithmetically feasible, but intentionally
demanding.** It cannot pass on a marginal one-control advantage or on two
borderline comparisons.

## Exact boundary

Let `b` be cases where CoPE succeeds and a control fails, and `c` cases where
the control succeeds and CoPE fails. The paired risk difference is
`(b-c)/40`. The analyzer uses a two-sided exact McNemar p-value and Holm
correction across neutral and governed.

At the most favorable boundary:

- `6-0` gives RD `0.15` and raw p `0.03125`;
- `7-0` gives RD `0.175` and raw p `0.015625`;
- one `7-0` comparison plus one `6-0` comparison passes Holm for efficacy;
- two `6-0` comparisons do **not** pass because the first Holm-adjusted p is
  `0.0625` and monotonicity propagates it to both;
- if either comparison has a raw p of at least `0.05`, the joint claim fails;
- at least one comparison must have raw p below `0.025`.

The attached frontier CSV enumerates the minimum `b` at each `c` for raw
thresholds `.05` and `.025`, already respecting RD >= `.15`. With 40 cases, a
raw `.025` boundary becomes impossible once `c >= 13`, and raw `.05` becomes
impossible once `c >= 14`.

## Locality family

The same two-sided exact sign test and two-control Holm logic applies to
`cope_smaller` versus `control_smaller`; ties are excluded from the sign test.
In addition, the median paired relative byte reduction must be at least 20%.
Therefore many tiny byte wins cannot pass through significance alone, and one
large outlier cannot rescue a weak median.

## Multiplicity interpretation

Efficacy and locality are separate Holm-corrected two-control families, and
the claim requires every gate in both families. This is an intersection-union
decision: failure of any neutral/governed efficacy, safety, or locality gate
rejects the claim. Secondary FSR-PC/full-replan comparisons remain
non-rescuing.

## Limits

This audit proves decision-rule feasibility, not prospective statistical power
under an assumed data-generating distribution. The 40 cases are a fixed,
balanced benchmark population; any generalization beyond it still requires
model and embodied replication.

## Verification

A unit test now locks the `6-0`/`7-0` Holm boundary so later statistical-library
or implementation changes cannot silently relax the preregistered gate.
