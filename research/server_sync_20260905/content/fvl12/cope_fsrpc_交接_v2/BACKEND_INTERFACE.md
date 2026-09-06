# Simulator backend interface

The method layer does not import LIBERO, robosuite, MuJoCo, a robot model, or
an asset class. All platform-dependent operations are behind
`cope.backends.base.SimulatorRepairBackend`.

## Required operations

`initialize`, `reset`, `begin_leg`, `observe`, `step`, `checkpoint`, `restore`,
`state_hash`, `retarget`, `cancel_goal`, `set_target_availability`,
`move_target`, `collision_status`, `attachment_status`, `task_success`,
`write_video`, and `finish_episode` are abstract methods. An unknown backend or
an unavailable simulator raises `BackendUnavailable`; there is no implicit
Synthetic2D fallback.

Two implementations ship:

- `Synthetic2DBackend` preserves the previous CPU substrate.
- `LiberoMujocoBackend` drives the installed LIBERO/robosuite/MuJoCo world.

The runner selects them explicitly:

```bash
python scripts/run_cope_pilot.py --backend synthetic2d ...

python scripts/run_cope_pilot.py \
  --backend libero_mujoco \
  --backend-config configs_gpu/task_assets.yaml ...
```

`observe()` is the concrete spelling of `observe_repair_context()` in this
package. Its `ExecutionContext` contains the frozen engine fields and an
`extra` record with robot/eef state, active leg and goal, every object pose,
every target pose, attachment, linear/angular stability, collision telemetry,
the current task goal, continuation-handoff fields, restore-contract fields,
and the canonical simulator-state hash.

## Candidate isolation contract

The real backend checkpoint includes MuJoCo state, `data.ctrl`, mocap state,
OSC controller goals, oracle step/action history, attachment checkpoint,
active object/target, availability state, collision bookkeeping, and artifact
cursors. Every candidate follows:

1. capture checkpoint and canonical state hash;
2. restore that checkpoint before the candidate;
3. run real `env.step` controls;
4. hard-reject collision, controller/guard timeout, horizon exhaustion,
   attachment loss, event residual, or invalid continuation handoff;
5. restore the checkpoint and assert the same hash.

MuJoCo `sim.forward()` can renormalize a quaternion by roughly `1e-16` without
changing the physical state. The hash encoding therefore rounds continuous
arrays to 12 decimal places and normalizes signed zero. A raw restore audit
measured maximum error `1.11e-16`; controller, ctrl, and mocap errors were
exactly zero. This canonicalization is part of the logged checkpoint metadata;
task, handoff, collision, and attachment thresholds are not relaxed.

## Execution substrate and claim boundary

The real backend uses an OnTheGroundPanda robot, robosuite `OSC_POSE`, and
privileged simulator-geometry pick/place skills. This is a mechanism
qualification substrate, not a learned-policy result. OSMesa performs
offscreen rendering on CPU; no learned checkpoint or CUDA inference is used.

Contact telemetry is a simulation proxy, not calibrated force or human-safety
evidence. Intended gripper/current-object and object/target contacts are
allowed. Robot contacts with protected task objects and the explicit
adversarial preflight collision are hard failures.

Final task evaluation is independent of program termination. It records every
object--region predicate, cancelled-object occupancy, stale nominal-target
occupancy, redirected-goal success, per-object linear/angular velocity and
stability, unsafe contact, environment steps, and task time. Revised task
success additionally requires all expected predicates, no cancellation
violation, no unsafe contact, and stable objects.
