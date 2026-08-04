# Occurrence efficacy power sensitivity

Date: 2026-08-04

## Decision

**Keep the frozen 40-case gate; do not inflate it with more lexical object
permutations.** The gate has low sensitivity near its minimum effect threshold,
but mechanically duplicating the same semantic template would create
pseudoreplication rather than convincing independent evidence.

## Sensitivity model

For one CoPE/control comparison, let each case independently fall into
`CoPE-only win` with probability `p_b`, `control-only win` with probability
`p_c`, or a concordant tie otherwise. Exact multinomial enumeration computes
the probability of satisfying RD >= 0.15 plus raw exact-McNemar p < .05
(`weak`) or p < .025 (`strong`).

For two identically distributed, independent controls, the reported joint
quantity is:

`P(both weak and at least one strong) = W^2 - (W-S)^2`.

This matches the two-control Holm boundary but is **not** a formal power
analysis: neutral and governed share the same CoPE output and are not
independent, no data-generating probabilities are known, and locality/safety
gates are omitted. It is an efficacy-only upper-bound sensitivity calculation.

## Key results at n=40

| `p_b` | `p_c` | true net difference | approximate two-control efficacy sensitivity |
|---:|---:|---:|---:|
| 0.15 | 0.05 | 0.10 | 0.026 |
| 0.20 | 0.05 | 0.15 | 0.123 |
| 0.25 | 0.05 | 0.20 | 0.311 |
| 0.30 | 0.05 | 0.25 | 0.540 |
| 0.30 | 0.025 | 0.275 | 0.790 |
| 0.35 | 0.05 | 0.30 | 0.740 |
| 0.40 | 0.05 | 0.35 | 0.873 |

At a true net effect exactly equal to the RD threshold, increasing sample size
does not drive pass probability toward one because sampling estimates remain
on either side of the hard threshold. Under the independence sensitivity
model for `p_b=.20, p_c=.05`, the joint values at n=40, 60, 80, 100, 120 and
160 are approximately .123, .280, .296, .291, .287 and .282.

## Scientific consequence

- A PASS would imply a large, clean effect on this fixed benchmark.
- A near-threshold NO-GO means the preregistered method claim failed; it is not
  proof of zero effect in all tasks/models.
- Adding more ordered triples from the same seven objects would mainly repeat
  lexicalized versions of one transition schema and could make p-values look
  stronger without adding semantic independence.
- The next preregistered expansion, if justified by the frozen outcome, should
  add distinct interruption semantics, tasks, controllers, and models, with
  clustering or hierarchical analysis where cases share templates.

The attached CSV preserves the full n=40 sensitivity grid. No provider call,
simulator access, hypothesis, threshold, or manifest was changed.
