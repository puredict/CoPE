# Force-proxy correction and failed mitigation diagnostic

Date: 2026-07-31

Evidence class: privileged deterministic LIBERO oracle diagnostic. This is
mechanism evidence, not a calibrated force measurement or safety certificate.

## Why the first force analysis was invalid

The initial telemetry read MuJoCo `cfrc_ext[:, :3]` as force. MuJoCo stores
this array in `rotation:translation` order, so those components are torque;
the force components are `cfrc_ext[:, 3:]`. The implementation and regression
test were corrected, and all ten exact-return/local-stage pairs were rerun.

Force and impulse numbers in `raw_v1`, `raw_v2`, `diagnostic_v3`,
`diagnostic_v4`, and `contact_diagnostic_v5` are invalid and must not be cited.
Success predicates, step counts, action/state hashes, contact pairs, and object
displacements from those runs do not depend on the component split. The
authoritative paired force run is `raw_v3_corrected_spatial_order`.

Primary API references:

- [MuJoCo mjData API](https://mujoco.readthedocs.io/en/stable/APIreference/APItypes.html)
- [MuJoCo mju_transformSpatial](https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mju-transformspatial)

## Corrected state-2 diagnostic

All three arms share the same event prefix and reach the physical updated
goal. The slow arm is a post-hoc diagnostic, not held-out evidence.

| Arm | Post-event steps | Peak relevant net-body force proxy (N) | Relevant force-impulse proxy (N·s) | Peak post-event step | Peak phase |
|---|---:|---:|---:|---:|---|
| Exact return | 269 | 42.03 | 158.08 | 58 | Return/release of obsolete held object |
| Fast local stage, limit 1.0 | 234 | 59.87 | 150.64 | 47 | Local-stage descent |
| Slow local stage, limit 0.25 | 273 | 106.62 | 234.85 | 117 | Later replacement-object grasp descent |

Relative to exact return, fast local staging saves 35 actions and lowers the
integrated proxy by 7.44 N·s, but raises the peak by 17.84 N. Relative to fast
local staging, slowing only the staging descent adds 39 actions, raises the
peak by 46.74 N, and raises the integrated proxy by 84.22 N·s. It is therefore
strictly dominated on this diagnostic state.

The contact snapshot at the corrected fast-local peak includes gripper contact
with the held alphabet-soup object and the tomato-sauce object. At the
slow-local peak it includes gripper contact with tomato sauce during the later
grasp approach. This shows that the filtered `cfrc_ext` peak is a net-body
contact/load proxy; it is not a clean collision-severity measure.

## What survives the adversarial audit

- Held-out states 1–4: physical updated goal is 4/4 for both exact return and
  local staging.
- Local staging saves 30–38 post-event steps (mean 34.8).
- Corrected peak proxy is higher for local staging in 4/4 held-out pairs
  (paired mean +11.77 N).
- Corrected integrated proxy is lower for local staging in 4/4 pairs
  (paired mean -8.41 N·s).
- Robot/protected-object and robot/environment contact-step proxies are zero
  in both arms; the preserved cream-cheese displacement is at most 0.10 mm
  for exact and 0.02 mm for local, while idle butter remains unchanged.
- Task-object/protected-object contact persists for 37 steps in both arms
  because tomato sauce and cream cheese are co-placed in the basket. It must
  not be mislabeled as an accidental collision.

## Decision and next falsifiable test

Keep the existing local-stage rule only as an efficiency ablation. Do not call
it safer. Reject staging-descent slowdown as a mitigation.

A future safety-oriented variant should choose a staging pose by an explicit
geometric-clearance constraint over the replacement object, protected
objects, receptacle, and robot path. That rule and its force/contact thresholds
must be fixed before evaluation, then tested on fresh initial states. No such
rule is tuned here because state 2 has already been inspected.
