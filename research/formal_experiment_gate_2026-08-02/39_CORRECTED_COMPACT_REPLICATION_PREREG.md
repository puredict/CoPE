# Corrected-compact remediation replication preregistration

Date frozen: 2026-08-03 (Asia/Shanghai), before any remediation provider call.

## Purpose and evidential status

This is a transparent remediation replication of the already observed
`SCE-H01`--`SCE-H36` corpus. It is **not** a new holdout and cannot by itself
provide confirmatory evidence. Its purpose is to determine whether the apparent
CoPE advantage survives after the compact arm receives and executes the natural
object-member JSON Patch semantics that its original interface implied.

## Only intended interface change

The compact contract now explicitly states:

- `add` creates an absent member or replaces an existing member;
- `replace` requires and replaces an existing member;
- `remove` requires and removes an existing member;
- whole-record values are complete records whose `id` matches the path.

The compact executor implements those rules. CoPE, neutral typed, full-state,
case order, rule packets, schemas inferred from the same oracle proposals,
provider, model, seed, temperature, token budget, timeout and rotating arm order
otherwise remain unchanged.

## Frozen protocol

- model: `qwen/qwen3.5-flash-02-23`;
- reasoning `none`, temperature 0, seed 20260803;
- strict OpenRouter JSON Schema;
- 36 cases and four arms, 144 retained assignments;
- zero retry, repair, fallback and oracle substitution;
- all common-input and normalized-request quadruplets must pass the fairness
  audit;
- no GPU, simulator, controller, development state or reserved state.

## Analysis and routing rule

Report the same two paired two-sided exact tests with Holm correction. Because
the cases are no longer unseen, p-values are descriptive only.

- If compact reaches at least 34/36 and CoPE is not Holm-significant versus
  compact, stop the learned representation-advantage route and treat the shared
  commit envelope as the supported component.
- If CoPE remains Holm-significant versus corrected compact with positive
  direction and 36/36 fair quadruplets, construct and freeze a genuinely unseen
  confirmation set before any embodied promotion.
- If assignment or fairness integrity fails, invalidate the run.

States 27--49 remain locked; states 47--49 remain permanent reserve.
