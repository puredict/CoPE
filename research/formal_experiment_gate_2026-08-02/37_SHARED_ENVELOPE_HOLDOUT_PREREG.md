# Shared-envelope 36-case holdout preregistration

Date frozen: 2026-08-03 (Asia/Shanghai), before any holdout provider call.

## Question

With explicit provider-visible delta clauses and one shared trusted commit
envelope, does CoPE-semantic produce more first-pass correct semantic states
than an equally sparse natural-path compact transaction and a neutral typed
interface?

## Corpus

The holdout contains 36 new case IDs (`SCE-H01`--`SCE-H36`) and 36 named
transition programs. It excludes all X14--X17 and shared-envelope development
case IDs. Each program has a unique family label, ordered operation program and
provider-visible rule clause for every oracle semantic operation.

The corpus covers expiry, conjunctive/disjunctive dependency handling,
priority/preemption, replacement, override/release, world/evidence changes,
reversible and non-reversible stopping, progress/checkpoint/retry,
restoration management, subgoal decomposition, deadlines, concurrency,
authority-scoped updates, and compound transitions.

This is a representation-factorization holdout, not a natural-language policy
induction benchmark: every required semantic delta is stated explicitly in the
common rule packet. The inferential unit is one unique transition program.

## Arms and shared envelope

1. CoPE semantic typed delta;
2. neutral typed delta with fixed non-semantic operation labels;
3. compact semantic transaction using natural stable-ID add/replace/remove
   paths;
4. complete semantic state.

All arms exclude state/evidence versions, processed events, event hashes and
receipts. The same trusted envelope generates these fields only after semantic
validation. All arms receive byte-identical common semantic input and differ
only in output contract/schema.

## Frozen provider protocol

- model: `qwen/qwen3.5-flash-02-23`;
- reasoning: `none`;
- temperature: 0;
- seed: 20260803;
- maximum completion tokens: 8192 equally;
- timeout: 90 seconds;
- strict OpenRouter JSON Schema with required-parameter routing;
- zero retry, repair, fallback and oracle substitution;
- 36 cases in manifest/code order;
- four-arm order rotates deterministically, giving every arm nine first
  positions;
- all assignments retained.

## Primary analysis

Two co-primary paired contrasts use two-sided exact McNemar/sign tests:

1. CoPE-semantic versus compact-semantic;
2. CoPE-semantic versus neutral-typed.

Holm correction is applied across the two contrasts. A CoPE-specific positive
decision requires:

- Holm-adjusted `p < 0.05` for CoPE versus compact;
- positive paired direction;
- CoPE at least 18/36 correct;
- CoPE has no more incorrect semantic attempts than compact.

If CoPE ties compact but sparse transactional arms substantially beat full
semantic state, route to representation-agnostic transactional recovery. If
all arms lack a usable ceiling, stop learned-generation experiments.

Family breakdown, bytes, completion tokens and latency are secondary and
cannot override the primary decision.

## Safety and scope

This experiment is provider-only. It uses no GPU, simulator, controller,
development LIBERO state or reserved state. States 27--49 remain locked and
47--49 remain permanent reserve.
