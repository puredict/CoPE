# Server and simulator audit

Audit date: 2026-08-04 (Asia/Shanghai).

## Access and preservation

- Preferred endpoint used: `lijingsu@10.176.53.120:26575` (local SSH alias
  `vla`).
- No sudo, Docker, account creation, or process termination.
- Existing `/home/lijingsu/vla` untracked directories and all prior ReKep/CoPE
  result roots were left untouched.
- New package root: `/home/lijingsu/cope_fsrpc_交接_v2`.
- New experiment parent: `/home/lijingsu/cope_outputs`.
- Each run has a new versioned directory and is never overwritten.

## Hardware and operating system

| field | observed value |
|---|---|
| host | `fvl12` |
| OS | Ubuntu 22.04.5 LTS |
| kernel | 5.19.0-50 |
| GPUs | 8 x NVIDIA GeForce RTX 3090, 24 GiB each |
| driver | 535.54.03 |
| reported CUDA compatibility | 12.2 |
| `nvcc` | not installed |
| renderer used here | OSMesa CPU offscreen |

`nvidia-smi` was run before simulator launches. Every device showed 12 MiB
used and 0% utilization at those checks. The experiment loads no learned
checkpoint and does not use CUDA, so no GPU was reserved.

The root filesystem was already about 94% full and `/share` was full. Outputs
were therefore kept under `/home/lijingsu/cope_outputs` and no large checkpoint
was downloaded.

## Reused software stack

| field | observed value |
|---|---|
| source root | `/home/lijingsu/vla` |
| git commit | `570d78333ee977c8ae6de3d97120b23272c4c660` |
| Python | 3.10.12 |
| runtime | `/home/lijingsu/vla/.venv/bin/python` |
| wrapper | `/home/lijingsu/vla/scripts/run_project_env.sh` |
| LIBERO | installed source under `/home/lijingsu/vla/src/LIBERO` |
| robosuite | 1.4.1 |
| MuJoCo | 2.3.7 |
| PyTorch | 2.5.1+cu121 (installed, not used for inference) |
| robot | OnTheGroundPanda |
| controller | OSC_POSE |
| control interval | 0.05 s (20 Hz) |

The environment wrapper intentionally removes the server's broken system CUDA
library path and configures the existing LIBERO/OpenVLA source roots and OSMesa
renderer. The resulting evidence is a real-simulator mechanism result, not a
learned-policy or GPU-inference result.

## Available platform capabilities

The installed stack provides:

- BDDL task loading and physical object/region assets;
- MuJoCo native state access, `data.ctrl`, mocap state, and controller goals;
- OSC Cartesian control through real `env.step` calls;
- contact pairs and object/region poses;
- offscreen agent-view observations suitable for MP4 evidence;
- deterministic seed-controlled task resets.

The adapter uses these capabilities directly. It does not modify CoPE or
FSR-PC semantics and never substitutes Synthetic2D when the real backend fails.

## Limitations

- The controller is privileged geometry-based, not a learned VLA policy.
- OSMesa rendering is CPU-based even though the host has GPUs.
- MuJoCo contacts are a simulation proxy, not calibrated force or human-safety
  measurements.
- The task uses installed LIBERO assets; abstract yogurt is represented by the
  explicitly documented `cream_cheese_1` object.
- No physical robot was audited or controlled.
