# Bounded regrasp development preregistration

Status: design frozen before embodied repair development.

## Diagnosis after states 5--14

The committed baseline prefix audit succeeded on 10/10 diagnostic states with
zero provider calls.  Together with the repeated state-33 centered-grasp
failure, this supports a narrow diagnosis: the historical single centered
grasp has insufficient coverage for some initial configurations, rather than
being broadly unreliable on ordinary development states.

No state-33 geometry is inspected and state 33 is never retried.  States 15--24
remain locked for independent validation; states 25--49 remain outside this
development program.

## Candidate mechanism

- Preserve the historical centered grasp as attempt zero.
- Only after `is_grasping` is false, open the gripper and relocalize from the
  object's current simulator geometry.
- Permit a finite ordered list of absolute XY grasp offsets.
- Keep the legacy default at exactly one `(0, 0)` attempt.  Robust regrasp is
  opt-in through a committed controller configuration.

The candidate natural configuration is frozen provisionally as centered grasp
followed by offsets `(+12 mm, 0)`, `(-12 mm, 0)`, `(0, +12 mm)`, and
`(0, -12 mm)`.  The first-successful attempt terminates the search.

## Development experiment

Use task-1 states 0--4 only.  For each state, create four independent episodes
from identical reset and seed:

1. `natural_legacy`: centered grasp only;
2. `natural_candidate`: centered grasp plus the four bounded alternatives;
3. `stress_single`: a single deliberate `(+40 mm, 0)` acquisition target;
4. `stress_candidate`: the same `(+40 mm, 0)` first target, followed by center
   and the four bounded alternatives.

The stress condition is an explicit acquisition-target perturbation, not a
claim that it reproduces state 33.  It tests whether the fallback is physically
executable after a failed close.  It is kept separate from natural success.

## Development gates

- focused unit tests pass, including fail-closed legacy behavior and injected
  first-check recovery;
- all `natural_legacy` episodes succeed;
- all `natural_candidate` episodes succeed and have exact action hashes equal
  to their natural legacy pair, proving no change when attempt zero succeeds;
- `stress_candidate` has strictly more prefix successes than `stress_single`;
- no provider credentials or calls; no states above 4 indexed by this runner.

Failure of a gate triggers repair using only states 0--14.  Passing all gates
permits freezing a separate state-15--24 validation preregistration, but never
authorizes resuming the interrupted formal run.

