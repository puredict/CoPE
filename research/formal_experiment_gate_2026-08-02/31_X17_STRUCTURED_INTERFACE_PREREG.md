# X17 structured-interface attribution preregistration

Date: 2026-08-03 (Asia/Shanghai)

## Purpose

X16 could not test broad APPLY correctness because every arm scored 0/22 APPLY,
and the CoPE prompt omitted the exact operation discriminator and field schema.
X17 separates interface learnability from representation semantics without
relabeling X16 as a successful result.

## Stage A: exploratory interface qualification

Use development-only cases that are excluded from the confirmatory holdout.
Compare four interfaces under identical common input and model settings:

1. CoPE exact JSON schema with every typed operation and required field;
2. neutral typed operations with permuted/non-semantic operation labels;
3. compact TX exact JSON schema with fully specified stable-ID paths;
4. FSR-PC exact full-state schema.

Plain prompting and provider-supported structured JSON/function calling are
crossed where the provider supports them. No repair, retry, or fallback is
allowed. Stage A passes only if each sparse arm reaches at least 4/6 correct
APPLY outputs and every generated oracle example passes the same validator.

X16 may be replayed only as an explicitly exploratory error-analysis appendix;
it cannot supply X17's confirmatory p-value.

## Stage B: new independent holdout

Before any Stage-B provider call, freeze at least 36 new independent templates
that were not used in X14, X15, X16, or Stage A. Freeze the corpus, oracle,
exact schemas, neutral-label permutation, prompt, function definitions, arm
order, seed, scoring, missingness and primary tests by SHA-256.

Primary contrasts:

1. CoPE exact schema versus compact TX exact schema;
2. CoPE semantic labels versus neutral typed labels.

The independent unit is one transition template. Use two-sided exact McNemar
tests with Holm correction across the two primary contrasts. A CoPE-specific
positive conclusion requires:

- corrected `p < 0.05` in the CoPE-versus-compact contrast;
- CoPE direction positive;
- no excess unsafe mutation attempts;
- at least 50% APPLY correctness for CoPE;
- no systematic reverse on stale-version, idempotence, authorization, or
  continuity-conflict families;
- the label-neutral control shows that the result is not solely operation-name
  alignment.

If CoPE ties compact TX after exact schemas, route the paper to
representation-agnostic transactional recovery. If all arms again lack an
APPLY ceiling, stop provider experiments and improve the task/interface before
any embodied formal rollout.

## Embodied boundary

X17 is provider-only and uses no simulator or reserved state. The X15
development embodied canary may be engineered in parallel, but reserved states
27--49 remain locked. States 47--49 remain permanent reserve.
