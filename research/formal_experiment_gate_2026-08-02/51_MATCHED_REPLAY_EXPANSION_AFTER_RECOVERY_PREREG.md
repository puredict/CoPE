# Matched valid-arm development expansion after recovery

Date frozen: 2026-08-03 (Asia/Shanghai), before expansion provider calls or
simulator execution.

## Authorization and scope

The recovered state-0 evidence passes the substantive criteria in report 50.
This protocol authorizes one development-only expansion to states 1--4. It does
not repeat state 0 and does not authorize states 27--49.

## Frozen implementation and input

- runner implementation:
  '58c3378198f4ca09bb50be1f0adf409829074663';
- recovered state-0 result commit:
  '2bfa5f7fb6f49a9ab27472cf36714d800f0b1a34'; the runner records the later
  preregistration HEAD in every expansion row;
- focused tests: 63 passed; full regression: 489 passed;
- retained state-0 gate input:
  'research/matched_valid_arm_embodied_2026-08-03/state0_execution_resume_v1/01_RETAINED_SEMANTIC_RESULTS.csv';
- the retained input contains exactly eight four-arm rows and causes no provider
  retry.

## Frozen run

- LIBERO-10 task 1, development states 1--4 only;
- cancellation and replacement in every state;
- four arms, 32 new provider calls;
- execute every semantically valid arm from a matched prefix; fail-close every
  invalid arm;
- model 'qwen/qwen3.5-flash-02-23', reasoning none, temperature 0,
  seed 20260802, completion limit 4096, timeout 90 seconds;
- zero retry, repair, fallback and semantic oracle substitution;
- CPU-only cold environment;
- output:
  'research/matched_valid_arm_embodied_2026-08-03/expansion_states1_4_openrouter_v1'.

The runner may be detached from SSH after secure credential injection so that a
transport disconnect cannot kill the experiment. The credential may exist only
in the child process environment and must not be written to a command, log or
result file.

## PASS rule

1. 32/32 provider calls OK and four-arm fairness for all eight events;
2. CoPE and neutral sparse semantic-correct on all eight events;
3. every semantic-valid arm reproduces the matched prefix and reaches terminal
   success;
4. every semantic-invalid arm has execution_attempted=false and zero actions;
5. valid cancellation arms emit zero actions and suppress butter;
6. within every replacement case, CoPE and neutral use identical action counts
   and action hashes, retain cream cheese, place alphabet soup and avoid butter;
7. no state 0 repeat, reserved state, fallback, semantic oracle substitution or
   credential retention.

Compact and FSR semantic correctness remains measured, not forced. If either
becomes valid, it must be executed under the same replay rule. Any provider,
prefix, semantic, physical or integrity failure yields FAIL with no retry.
