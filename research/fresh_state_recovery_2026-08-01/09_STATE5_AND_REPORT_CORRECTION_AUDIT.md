# State-5 failure and analysis-correction audit

Date: 2026-08-01

## Authoritative finding

In the preregistered states 5–14 run, state 5 produced no CSV for any of the
three arms. Every raw TXT log ends before the semantic event with
`FullStateValidationError: completed progress is not physically true`.
Because the failure occurs before the methods diverge, it is a
method-independent execution-substrate failure, not evidence for or against
local staging.

A diagnostic replay using the same correct target symbol,
`basket_1_contain_region`, confirmed the underlying controller failure:

- default `max_move_steps=40`: `descend_to_grasp` consumes all 40 steps and
  ends at 8.45 mm error; grasp is initially detected but the object is not
  retained during lift, lift displacement is 0, and the physical completion
  predicate remains false;
- diagnostic `max_move_steps=60`: the descent converges in 45 steps at 7.75 mm
  error, the object is retained and lifted 197.4 mm, and cream cheese is
  physically placed in the target region.

The max-60 replay is post-hoc development evidence on an already failed state.
It does not repair the first fresh run and cannot be inserted into its assigned
denominator.

## Invalid diagnostic artifacts retained for transparency

`04_STATE5_DIAGNOSTIC.txt` and
`06_STATE5_CONTROLLER_MAX60_DIAGNOSTIC.txt` passed `basket_1` rather than the
formal experiment's `basket_1_contain_region`. They are invalid for explaining
the formal failure and must not be cited. They are retained rather than
deleted so the correction is auditable.

Authoritative replacements:

- `07_STATE5_CORRECT_TARGET_MAX40.txt`
- `08_STATE5_CORRECT_TARGET_MAX60.txt`

## Decision-rule correction

The preliminary `03_RESULT.md` interpreted failure of C1
(`10/10` complete prefix integrity) as rejection of local staging. The frozen
preregistration instead says:

- C1 failure invalidates the assigned comparison;
- C2–C5 failure rejects local staging.

Therefore the authoritative report is
`03_RESULT_v2_PROTOCOL_CORRECTED.md`: **inconclusive because assigned
comparison validity failed**. The 9/9 complete event-qualified pairs remain
conditional evidence that local staging is faster, but they do not satisfy the
frozen retain/reject gate.

## Harness defect exposed

The timing experiment raises during persistent-state initialization when the
completed-progress predicate is false, so it does not emit a structured CSV
failure row. The assigned ledger reconstructs these three failures only from
the retained raw TXT logs. Future runners should always emit one terminal row
per assignment before returning nonzero; missing raw rows must not be treated
as dropped data.

## Next experiment boundary

State 5 is now a controller-development state. A max-60 controller may be
tested only under a new preregistration on untouched states 15–24. States
5–14 remain consumed and cannot be relabeled as fresh.
