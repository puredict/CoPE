# P0-1 — pen-in-holder success metric: specification and calibration

Implementation: `rekep_repair/gpu_metrics/pen_in_holder.py`.
Tests: `tests/test_gpu_metrics.py::test_1..test_5, test_12`.

## Why this exists

v1 recorded only `completed: true`, meaning *the program graph finished and a
video was saved*. The audit showed that flag does not imply the task was done:
the two nominal runs end with the pen visibly inserted (pen–holder xy ≈ 0.030 m),
while repaired seeds 0/3/5 end 0.094–0.096 m away with the pen still gripped and
seed 7 ends with the pen **lying flat on the table** (89.5° from vertical, below
the holder rim).

## Measured quantities

Per terminal evaluation the evaluator records: pen pose, pen tip and butt, pen
axis, holder pose, holder axis, holder rim world height, radial distance of the
tip from the holder axis (`xy_error`), `insertion_depth` below the rim, `tilt`
relative to the **holder** axis (not world vertical), `inside_holder`
containment, attachment state, max linear/angular speed over the final K steps,
and the thresholds actually applied.

## Success conditions

```
inside_holder            == True
xy_error                 <= eps_xy
insertion_depth          >= eps_depth
tilt_error_deg           <= max_tilt_deg
stable_for_K_steps       == True
```

`gripper_released` is **deliberately not required**. The official ReKep pen task
may complete while still grasping; adding release would be an artificial
criterion. Attachment is *recorded* and can be required explicitly via
`PenInHolderThresholds(require_release=True)` — tested both ways
(`test_1b_success_does_not_require_release`).

## Thresholds and their physical meaning

| threshold | default | physical meaning |
|---|---|---|
| `eps_xy` | `0.85 × (bore_radius − pen_radius)` | the pen must physically fit in the bore; the 0.85 factor keeps a margin so a pen resting **on** the rim does not pass |
| `eps_depth` | `0.25 × bore_depth` | the tip must be at least a quarter down the bore — excludes leaning on the rim |
| `max_tilt_deg` | 30° | a pen inside a narrow bore is mechanically near-aligned; excludes a pen lying across the rim |
| `stable_steps` | 10 | the pose must persist, not be a transient during release |
| `max_linear_speed` | 0.02 | pen not still moving |
| `max_angular_speed` | 0.35 | pen not still rotating |

Thresholds are **derived from the holder/pen geometry**, not fitted to episodes.
`inner_radius`, `rim_height`, `bore_depth`, pen `length`/`radius` **must be read
from the real USD assets on the GPU host** and passed in; the values in
`run_gpu_pilot_episode.py` are declared defaults to be confirmed.

## Calibration protocol

* **Positives** — the official/wrapped nominal runs that visibly insert the pen
  (`wrapped_result.json` xy = 0.0332; `wrapped_result_run2.json` xy = 0.0295).
* **Negatives** — repaired seeds 0 (0.0959), 3 (0.0943), 5 (0.0957), 7 (0.1129).
* **Unlabeled, deliberately NOT used to set any threshold** — seeds 1 (0.0407),
  2 (0.0368), 4 (0.0349), 6 (0.0478), and single-GPU repair run 2 (0.0295).
  These are the cases the metric must *adjudicate*, so tuning to them would be
  circular.

The positive/negative gap (0.033 vs 0.094) is wide; any threshold in 0.035–0.09
separates them. We do **not** exploit that freedom to place the threshold where
the unlabeled seeds land: `eps_xy` comes from the bore geometry.

### One buried positive worth knowing
`single_gpu/online_repair/repaired_result_run2.json` ends at xy = 0.02945
against a holder relocated to y = 0.0008 — essentially identical to the nominal
0.02947. That episode is the strongest existing evidence that online repair
*can* achieve the task. (Note also that `repaired_result.json` and
`repaired_result_run1.json` are byte-identical duplicates.)

## Retrospective evaluation of v1

`scripts/evaluate_pen_in_holder_retrospective.py` — run on all 13 v1 result
JSONs, it reports `task_success = UNAVAILABLE` for **13/13**, because v1 stored
no bore geometry, no pen dimensions, no velocities and no state history. It
reports what *is* derivable (centre-to-axis xy, tilt vs holder axis, Δz) and
lists the missing fields. This is the required behaviour: **mark UNAVAILABLE,
never guess from pixels.**
