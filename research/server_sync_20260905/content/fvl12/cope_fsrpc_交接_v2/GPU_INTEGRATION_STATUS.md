# Real simulator integration status

Last updated: 2026-08-04 (Asia/Shanghai).

## Audited platform

- Host: `fvl12`, Ubuntu 22.04.5 LTS, kernel 5.19.0-50.
- Account/path: `lijingsu`, `/home/lijingsu/cope_fsrpc_交接_v2`.
- GPU inventory: 8 × RTX 3090 24 GiB, driver 535.54.03, CUDA compatibility
  12.2. All were idle at the audited launches (12 MiB, 0%).
- CUDA compiler: `nvcc` not installed. Docker is not usable by this account.
- Runtime: `/home/lijingsu/vla/.venv/bin/python`, Python 3.10.12.
- Environment wrapper: `/home/lijingsu/vla/scripts/run_project_env.sh`.
- Source root: `/home/lijingsu/vla`, commit
  `570d78333ee977c8ae6de3d97120b23272c4c660`.
- Simulator: LIBERO source, robosuite 1.4.1, MuJoCo 2.3.7.
- Robot/controller: OnTheGroundPanda, OSC_POSE, 20 Hz (`dt=0.05 s`).
- Rendering: 128×128 agentview, OSMesa CPU offscreen. The server GPUs are not
  used by this oracle mechanism experiment.

The existing source repository and prior ReKep worktrees/results were only
read. No old output was modified or deleted.

## Task and assets

`configs_gpu/cope_basket_sorting.bddl` creates three physical objects and three
physical basket targets. Abstract yogurt maps to the installed
`cream_cheese_1` asset; all other labels map directly. Exact names and regions
are in `configs_gpu/task_assets.yaml`.

The first real nominal probe completed all three predicates in 599 simulator
steps:

- `milk_1 → basket_1_contain_region`;
- `cream_cheese_1 → basket_1_contain_region`;
- `butter_1 → basket_2_contain_region`.

## Gates completed so far

- Source ZIP integrity and CPU snapshot: pass.
- CPU tests before integration: `135 passed`.
- CPU I1–I4 ten-marker trace: pass.
- CPU tests after backend integration: `138 passed`.
- Custom BDDL load: pass (6 objects, 3 contain regions).
- Native MuJoCo save/change/restore hash: pass.
- Real preflight v5 (final strengthened-hash schema): pass.
  - candidate 0 rejected after a real protected-object contact;
  - candidate 1 rejected at 0.142 m continuation handoff error;
  - candidate 2 accepted with attachment retained and about 0.0013 m handoff
    error;
  - all three branches restored the same checkpoint hash, which includes
    simulator/controller state, held-object checkpoint, target-return poses,
    collision state, and artifact cursors;
  - pick, place, task predicate, and MP4 writing passed.
- Full nominal debug seed 0: pass, 3/3 predicates, collision false, 599 steps,
  seven required per-episode artifacts present.

The final 10-seed nominal gate uses per-object stability, task time, the required
`method/condition/seed` directory layout, and explicit candidate-isolation
denominators. A completed earlier gate-shaped diagnostic did not contain this
final schema and is preserved but excluded. The 60-episode pilot is recorded
only after its command finishes. An earlier I1 debug discovered a raw floating hash issue; it
was diagnosed as `1.11e-16` MuJoCo normalization and fixed with the documented
canonical hash. An SSH broken pipe then invalidated one attempted debug after
the complete pipeline; that output remains preserved and is not counted as a
valid episode.

## Current claim boundary

This work establishes an actual LIBERO/MuJoCo integration and real simulator
rollout evidence. It does not establish learned-policy robustness, calibrated
safety, physical-robot performance, or GPU inference performance.
