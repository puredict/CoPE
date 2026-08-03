# Bounded regrasp independent validation preregistration

Status: candidate frozen; states 15--24 not yet indexed.

## Frozen candidate

The production candidate keeps the historical centered attempt first, then
tries world-frame XY offsets `(+12 mm, 0)`, `(-12 mm, 0)`, `(0, +12 mm)`, and
`(0, -12 mm)`, stopping at the first acquired grasp.  All other controller
parameters equal `OracleSkillConfig(max_move_steps=60)`.

Frozen configuration hashes:

- natural legacy: `8adc9dcd496bc5bdae7e46c7e46e6cab4a4d6c710ad49bff4b0ff97adee4cab7`;
- natural candidate: `56171aef20a9f60e335259ff10abe7c211f6594a98b52b09864effcc7b1d988a`;
- 80-mm stress single: `4344f9fed4987bf206cf4cc15e9f614d369810e32ca1aa7c4ad81bdf17dfbe8a`;
- 80-mm stress candidate: `4fcb8ba265707b48b75f5566694b38d41080b4fb8d318ba0c632a022bcc841f4`.

The validation runner must fail before loading LIBERO if any hash differs.

## Locked validation protocol

- LIBERO-10 task 1; states 15--24, ascending;
- seed equals state ID; resolution 64; independent identical resets;
- four arms in fixed order per state:
  `natural_legacy`, `natural_candidate`, `stress_single_80mm`,
  `stress_candidate_80mm`;
- the stress candidate starts with the identical `+80 mm` target before any
  fallback, so the comparison is paired at the failure-induction step;
- no retry of an episode, no controller/config adjustment, no provider
  credential or call, CPU only;
- states 25--49 are not indexed; state 33 is not retried.

## Endpoints and gates

Natural non-regression gates:

1. candidate succeeds on all 10 stable prefixes;
2. no state succeeds under legacy and fails under candidate;
3. whenever both succeed, their action and simulator-state hashes are exact,
   proving the unused fallback does not change the historical trajectory.

Stress recovery gates:

1. candidate succeeds on all 10 stable prefixes;
2. candidate has strictly more paired successes than single attempt;
3. every candidate episode contains `regrasp_1`;
4. report the exact two-sided McNemar/binomial sign-test p-value for discordant
   stress pairs, descriptively because this is substrate validation rather than
   a CoPE-vs-baseline method comparison.

After any validation outcome, the candidate is not tuned on states 15--24.
Failure blocks it; passage permits its use in a future newly preregistered
formal experiment, never continuation of the interrupted state-27--46 run.

