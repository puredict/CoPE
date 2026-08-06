# Matched valid-arm embodied replay preregistration

Date frozen: 2026-08-03 (Asia/Shanghai), before matched-replay provider calls or
simulator execution.

## Question

When two independently generated sparse interfaces both pass the same semantic
validator, do CoPE labels and neutral labels produce the same modified physical
outcome from an exactly replayed milestone? Do semantically invalid compact and
FSR-PC generations fail closed without receiving an execution opportunity?

## Frozen implementation

- implementation commit:
  '58c3378198f4ca09bb50be1f0adf409829074663';
- focused tests: 63 passed;
- full cold-environment regression: 489 passed;
- every valid arm derives its command from its own trusted provider post-state;
- the first valid replacement arm executes from the primary milestone;
- each later valid replacement arm reconstructs the milestone from the same
  init state and must match prompt, predicate trace, action-prefix hash and
  simulator-state hash before execution;
- every invalid arm receives a fail-closed row and zero executor calls;
- semantic and embodied journal records are flushed independently.

## Stage 1

- LIBERO-10 task 1, development state 0 only;
- cancellation first, replacement second;
- CoPE, neutral-label sparse, corrected compact and metadata-free FSR-PC;
- eight provider calls, zero retry/repair/fallback/oracle substitution;
- execute every semantically valid arm; never execute an invalid arm;
- model 'qwen/qwen3.5-flash-02-23', reasoning none, temperature 0,
  seed 20260802, completion limit 4096, timeout 90 seconds;
- CPU-only cold environment;
- output:
  'research/matched_valid_arm_embodied_2026-08-03/state0_openrouter_v1'.

Stage 1 PASS requires:

1. 8/8 provider OK and within-event four-arm fairness;
2. CoPE and neutral sparse semantic-correct on both events;
3. compact and FSR-PC retain their observed validity outcome without repair;
4. each valid cancellation compiles to HALT, executes zero actions, retains
   cream cheese and does not execute butter;
5. each valid replacement selects alphabet soup from its own provider
   post-state and reaches the modified terminal goal;
6. the neutral replacement replay matches the primary prefix and both valid
   sparse arms have identical post-event action count and action hash;
7. invalid arms have execution_attempted=false and zero post-event actions;
8. no reserved state, fallback, semantic oracle substitution or learned-policy
   claim.

## Stage 2

If and only if Stage 1 passes, expand once to development states 1--4 using the
same committed runner and retained Stage-1 CSV. Do not repeat state 0. All
valid-arm terminal, replay identity and invalid-arm fail-closed criteria remain
mandatory. Output:
'research/matched_valid_arm_embodied_2026-08-03/expansion_states1_4_openrouter_v1'.

## Claim boundary

This experiment can show that sparse commitment editing, rather than CoPE
operation vocabulary, drives the executable high-level result. Low-level
Cartesian execution remains a qualified privileged mechanism, not a learned
visuomotor policy.

States 27--49 remain locked in both stages. States 47--49 remain permanent
reserve.
