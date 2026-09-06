# Bounded CPU prefix/preservation evidence plan

Prepared 2026-09-06. Execution has not been performed. The one-off source is
`PREFIX_PRESERVATION_DRIVER.txt` in this directory. It composes existing APIs;
no benchmark architecture, calibration driver, controller, or catalog changes.

## Fixed scientific scope

Twenty cells: tasks 0, 1, 4, 8 × initial states 0–4, environment seed 101.
Each receives one physical prefix attempt using the first original placement
commitment in the unchanged `task_progress` definition. All goal clauses must
match the frozen actual BDDL audit, and actual BDDL bytes and initial-state
bytes must match that audit again at execution.

| Task | Single attempted original placement | Other original clauses monitored |
| --- | --- | --- |
| 0 | In(alphabet_soup_1, basket_1_contain_region) | In(tomato_sauce_1, basket_1_contain_region) |
| 1 | In(cream_cheese_1, basket_1_contain_region) | In(butter_1, basket_1_contain_region) |
| 4 | On(porcelain_mug_1, plate_1) | On(white_yellow_mug_1, plate_2) |
| 8 | On(moka_pot_1, flat_stove_1_cook_region) | On(moka_pot_2, same region); Turnon(flat_stove_1) |

No alternative goal, second prefix choice, retuning, retry, or success-based
task selection is permitted. Task 4's historical first-placement canary failed;
task 8's placement controller is unqualified. These cells can truthfully fail
or remain blocked. There is no stove turn-on actuator in this controller.

## Existing APIs and bounds

The CPU environment uses the existing camera-disabled `ControlEnv` construction
from `tools.audit_repeated_feasibility`. The controller is
`LiberoOracleSkillController` with `OracleSkillConfig(max_move_steps=60,
grasp_attempt_xy_offsets_m=((0.0, 0.0),))`. Its calls are real `env.step`
commands using privileged geometry, never learned-policy calibration.

Prefix sequence: warmup 10; one `pick_and_place(..., predicate='in'/'on')`;
explicit open-gripper release 10; then five separately stepped one-control
zero-motion holds. Each of those five samples must freshly satisfy the exact
chosen goal, show no grasped object, and retain every initially true original
clause. The selected goal must initially be false to establish new completion.

The frozen implementation bounds one placement to 410 controls for `in` and
578 for `on`. Warmup/release/five checks yield 435/603. The guard rejects the
next command before `env.step` at prefix cap 620. Each allowed event branch has
cap 5, and the total per state has cap 630. Only two event families can qualify
for those holds, so the theoretical maxima are 445/613 controls per state.
These are oracle audit budgets, not the learned-VLA 260-control budget.

## Event inputs and isolated branches

The 135 source candidate rows come byte-for-byte from the retained successful
mechanical witness `event_effect_20260906T171946Z_1f2fc64b/EVENT_RESULTS.txt`.
The driver pins that file, its receipt, the static audit, state-hash CSV, and
five imported repository source files. It creates no injection parameters.

Every candidate starts from the authentic released, stable prefix snapshot.
Closing endpoints replay their matching original opening event as separately
counted setup. Therefore the maximum is 135 target calls plus 40 setup calls,
not 175 independent target results. A failed prefix produces explicit skipped
rows for all its candidates. Task 8 stove displacement has no candidate and is
explicitly unsupported by that primitive; no alternate grounding is inferred.

`apply_interruption(LiberoInterruptionContext(...), event, policy_step=0)`
retains policy-step zero because this audit makes no learned-policy calls.
Actual oracle environment controls at the boundary are recorded separately.
Each application verifies expected qpos, unchanged qvel/time, zero controls,
fresh observation flags, and an independent forced observation comparison.

Immediate preservation is evaluated for every executed target, with explicit
true/false fields. A false result is retained; the neutral evaluated status
never implies preservation. No controller is run in a physically displaced,
active no-go, or unavailable state.

Some unchanged source candidates deliberately displace the same first object
just completed by the fixed prefix. A resulting loss means that this candidate
does not preserve that protected-prefix state. It is not evidence that the
whole event family or task is infeasible. Neither the goal nor the candidate
will be retuned or replaced after observing that result.

Only no-go clearance and gentle-preference activation may receive five
zero-motion open-gripper controls. The branch must retain byte-identical
physical prefix state, have no active no-go or unavailability, preserve all
prefix-true clauses, and have no held object. Any loss during a hold stops
further controls in that branch. Availability release is not presumed safe.

## Restoration, artifacts, and interpretation

Before and after each candidate, existing `get_sim_state`/`set_init_state`
restores the flattened MuJoCo state. Every restore records full arrays, dtype,
shape, hashes, and before/after samples; it checks byte identity plus equal
commitments/grasps and equal object/EEF positions within 1e-10. A failed restore
stops the sweep. Arbitrary Python/controller internals are not serialized;
restoration is audit isolation, never robot recovery evidence.

Control intent and result rows are flushed durably. Environment calls attempted,
returned, raised, and denied are distinguished. A call that raises can have an
uncertain physical effect and is not silently counted as an ordinary returned
control. A failed control call or missing durable observation/result evidence
stops the entire sweep, rather than becoming an ordinary prefix/branch failure.
Physical prefix skill attempts/returns, planned prefix cells, candidate
target/setup attempts, and target returns are counted separately.

An execution requires `--execute`, the exact reviewed driver hash, and a new
output directory under project `research/`. The default invocation only checks
the fixed inventory and prints its plan; it imports no simulator, NumPy, Torch,
provider, or model. Published outputs are TXT/CSV/Markdown in the new directory:
source/config/claim receipts, complete control traces, prefix results, individual
event/application records, full restore records, combined results, CSV counts,
and a final receipt/report. Existing evidence is not overwritten.

This can establish bounded released prefix stability and observed preservation
or regression at specific candidate boundaries. Contact counts and force data
are uncalibrated simulator proxies. It establishes no general injection safety,
collision-free path, recovery feasibility, semantic-trigger certificate,
method-specific performance, clean VLA success, or catalog eligibility. Every
output explicitly retains `catalog_certificates = 0`.
