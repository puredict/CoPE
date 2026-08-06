# Bounded regrasp stress v2 preregistration

Status: frozen after retaining v1 and before v2 execution.

Development v1 showed 5/5 success for both the `+40 mm` single-attempt stress
arm and its fallback candidate.  The natural legacy/candidate arms were 5/5
with exact paired action hashes, but the stress superiority gate failed because
the perturbation remained inside the effective grasp region.

## Single frozen change

Increase the first acquisition-target displacement from `+40 mm` to `+80 mm`
in world X.  Do not change controller implementation, movement parameters,
candidate natural configuration, alternative offsets, task, states, seeds or
predicate checks.

## Execution

- task-1 states 0--4 only, ascending order;
- `stress_single_80mm`: exactly one `(+80 mm, 0)` target;
- `stress_candidate_80mm`: the identical first target, followed by center and
  the frozen `+/-12 mm` X/Y alternatives;
- independent identical resets; single arm order fixed as listed above;
- no per-state retry, no provider credential/call, CPU only;
- states 5--49 are not indexed by this runner.

## Gates

1. `stress_candidate_80mm` succeeds on all five stable prefixes;
2. it has strictly more successes than `stress_single_80mm`;
3. every candidate episode activates `regrasp_1`, proving the recovery path—not
   the first displaced grasp—caused the result.

Passing supports freezing the candidate for independent validation on states
15--24.  It does not claim the 80-mm perturbation reproduces state 33 and does
not authorize another state-33 or formal-state attempt.

