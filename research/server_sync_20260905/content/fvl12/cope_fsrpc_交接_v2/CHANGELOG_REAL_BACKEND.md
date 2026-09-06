# Changelog — real simulator backend qualification

This update adds the real platform layer requested after
`cope_fsrpc_交接_v2` was delivered. It does not replace the fixed CoPE research
hypothesis, alter the CoPE/FSR-PC semantic distinction, or rewrite the frozen
repair core.

## Added

- `cope/backends/base.py`: backend-neutral simulator contract.
- `cope/backends/synthetic2d.py`: explicit adapter preserving the prior CPU
  substrate.
- `cope/backends/libero_mujoco.py`: LIBERO/robosuite/MuJoCo implementation.
- `cope/backends/libero_oracle.py`: privileged geometry execution substrate.
- `cope/backends/rollout_verifier.py`: checkpoint-isolated real candidate
  rollouts with hard rejection.
- `cope/benchmark/backend_episode.py`: backend-neutral episode harness with
  physical world events and seven evidence artifacts per episode.
- `scripts/run_backend_preflight.py`: native restore, candidate isolation,
  collision, handoff, attachment, task-predicate, and video gate.
- `scripts/run_single_backend_episode.py`: explicit debug runner.
- `configs_gpu/cope_basket_sorting.bddl` and `task_assets.yaml`: audited real
  task and exact abstract-to-installed asset mapping.
- `tests/test_backend_contract.py`: backend selection/contract regression tests.
- `BACKEND_INTERFACE.md`, revised server runbook/status, and `research/`
  evidence reports.

## Changed additively

- `SharedRepairEngine` accepts a verifier factory; the original Synthetic2D
  verifier remains the default.
- `run_cope_pilot.py` now has an explicit real-backend path with separate
  `gate` and `pilot` stages, refusal to overwrite, gate-report verification,
  fixed 60-episode scope, and attempted/valid denominators.
- The task harness maps I2/I4 to physical basket removal/return/motion, rather
  than changing only a symbolic availability field.
- Documentation now separates Synthetic2D CPU claims from LIBERO/MuJoCo
  mechanism claims.

## Preserved

- the supplied ZIP and immutable CPU snapshot;
- old ReKep worktrees and experiment outputs;
- CoPE patch operators, lifecycle semantics, persistent identifiers, and audit
  trace;
- FSR-PC's internally defined full-state-regeneration semantics;
- the frozen synthesis/splice/restore core;
- all failed diagnostic outputs, with exclusion reasons recorded.

## Deliberate claim limitation

The selected server substrate is an OnTheGroundPanda/OSC_POSE privileged
geometry oracle rendered through OSMesa. It qualifies the repair mechanism in
a real robotics simulator. It is not evidence for a learned policy, physical
robot, GPU inference, calibrated safety, or force control.
