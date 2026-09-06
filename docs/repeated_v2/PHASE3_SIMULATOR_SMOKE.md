# Phase 3 simulator smoke

Date: 2026-09-06. Status: `PASS_CPU_LIBERO_PHYSICS_SMOKE`.

The installed, real LIBERO simulator completed reset, one environment step,
exact simulator-state restoration, and fresh observation acquisition without
an intervening policy step. This is simulator integration evidence only. It is
not a learned-policy rollout, task-success result, task-catalog calibration, or
repeated-interruption benchmark result.

## Executed configuration

- Interpreter: `/Users/lijingsu/miniforge3/envs/lerobot312/bin/python`.
- Installed simulator: `libero` under that interpreter's `site-packages`,
  `robosuite==1.4.0`, `mujoco==3.6.0`, `numpy==2.2.6`, `torch==2.10.0`.
  LIBERO has no installed distribution version metadata.
- Suite: `libero_10`; task index 1;
  `LIVING_ROOM_SCENE2_put_both_the_cream_cheese_box_and_the_butter_in_the_basket`.
- Seed 17; initial state index 0 of the task's 50 existing initial states.
- Cameras/renderers disabled. `CUDA_VISIBLE_DEVICES` is empty and Hub access is
  forced offline. No GPU, model checkpoint, network download, or training used.
- An isolated temporary `LIBERO_CONFIG_PATH` points to existing installed
  assets. The test does not change `~/.libero` or installed library files.

The test is opt-in:

```sh
COPE_RUN_LIBERO_SMOKE=1 PYTHONDONTWRITEBYTECODE=1 \
  /Users/lijingsu/miniforge3/envs/lerobot312/bin/python -m pytest \
  -q -s tests/repeated_v2/test_phase3_simulator_smoke.py
```

Observed simulator output:

```text
[info] using task orders [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
task=LIVING_ROOM_SCENE2_put_both_the_cream_cheese_box_and_the_butter_in_the_basket
reset_ok initial_states=50
step_ok reward=0.0 done=False
restore_exact=True
fresh_observation_without_step=True
PASS_CPU_LIBERO_PHYSICS_SMOKE
```

## Scope of the checks

The smoke copies the actual simulator state before stepping, restores that
state through LIBERO's native setter, and compares the restored state exactly.
It then forces observable refresh and obtains a new observation without
calling `env.step`. The end-effector observation agrees with the restored
state's observation. The one fixed zero-motion/open-gripper action is a physics
smoke action, not a substitute VLA controller.

The accompanying continuation and VLA protocol tests use synthetic perception,
verification, and inference clients and therefore cannot establish learned
policy feasibility. The continuation search and splice machinery in those
tests is the actual archived package. An additional compatibility test uses
the actual strict phase-2 `ExecutionPlan`, including its serialization/hash and
restore behavior.

While upstream phases were pending merge, the combined test process extended
the `cope_benchmark.repeated_v2` package search path read-only to the existing
phase-2 and phase-1 worktrees. No upstream source files were copied or edited.
The normal test imports work after those phases are integrated.

The final combined run passed **32 tests and 58 subtests in 2.76 seconds**,
including the opt-in simulator smoke.

## Remaining dependency gates

Local simulator availability does not clear `BLOCKED_VLA_ADAPTER_UNAVAILABLE`:
the local machine has no discovered OpenVLA checkpoint, no NVIDIA runtime, and
is missing production model dependencies described in `PHASE3_ADAPTER_AUDIT.md`.
The initial direct SSH route on port 26575 timed out, but the existing
`fudan-26575` alias subsequently reached the remote host. The remote OpenVLA
source and LIBERO10 checkpoint exist, but the parent's `nvidia-smi` probe found
all eight GPUs allocated. No remote model was loaded. This smoke establishes
only the local CPU result.
