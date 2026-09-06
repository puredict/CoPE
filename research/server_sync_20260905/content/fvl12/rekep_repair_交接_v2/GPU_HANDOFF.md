# GPU setup guide — ReKep + OmniGibson on 8× RTX 3090

> **Every command in this document is `REMOTE GPU SERVER ONLY`.**
> Nothing here has been executed. The development machine is CPU-only macOS;
> OmniGibson/Isaac Sim cannot run on it at all. Treat every version pin as
> *proposed* until `scripts/check_gpu_environment.py` confirms it on the target.

**Status legend used throughout this repo:**

| status | meaning |
|---|---|
| *locally syntax-checked* | file imports/compiles on the CPU machine |
| *locally dry-run validated* | ran end-to-end on CPU in `--dry-run` mode, no GPU imports |
| *not executed* | never run anywhere |
| *requires remote GPU verification* | correctness can only be established on the 3090 box |

## 0. Hardware / driver preconditions

RTX 3090 is Ampere (sm_86). Isaac Sim needs a recent driver; the 3090's 24 GB is
adequate for one OmniGibson instance per GPU.

| component | proposed pin | note |
|---|---|---|
| NVIDIA driver | **≥ 525.60.13** | Isaac Sim 2023.1.x minimum; newer is fine |
| CUDA runtime | **12.1** (via PyTorch wheel) | no system CUDA toolkit needed for torch |
| Python | **3.10** | OmniGibson/Isaac Sim pin 3.10; do not use 3.12 |
| PyTorch | **2.2.2 + cu121** | install from the PyTorch index, never PyPI |
| Isaac Sim | **2023.1.1** | pulled by the OmniGibson installer |
| OmniGibson | **1.0.0** (or the commit ReKep pins) | ReKep's README is authoritative |
| ReKep | upstream `main` | `huangwl18/ReKep` |
| OS | Ubuntu 20.04 / 22.04 | Isaac Sim is not supported on macOS |

`REMOTE GPU SERVER ONLY` — verify hardware first:

```bash
nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv
```

Expect 8 rows naming RTX 3090.

## 1. Create the environment

`REMOTE GPU SERVER ONLY`

```bash
conda create -n rekep python=3.10 -y
```

```bash
conda activate rekep && pip install torch==2.2.2 torchvision==0.17.2 --index-url https://download.pytorch.org/whl/cu121
```

Torch must be installed **before** anything else so no dependency silently pulls
a CPU build.

## 2. Install OmniGibson (brings Isaac Sim)

`REMOTE GPU SERVER ONLY` — follow the official installer; it downloads Isaac Sim
and the BEHAVIOR asset bundle (tens of GB, and it asks for a licence
acceptance).

```bash
git clone https://github.com/StanfordVL/OmniGibson.git && cd OmniGibson && ./scripts/setup.sh
```

Then download assets:

```bash
python -m omnigibson.utils.asset_utils --download_assets --download_demo_data
```

## 3. Install ReKep

`REMOTE GPU SERVER ONLY`

```bash
git clone https://github.com/huangwl18/ReKep.git && cd ReKep && pip install -r requirements.txt
```

**Do not modify ReKep's solvers.** The contribution is `ReKep + repair layer`,
not a rewritten manipulation stack. The only ReKep files the integration should
touch are the execution-loop hooks listed in §6.

## 4. Install the repair layer

`REMOTE GPU SERVER ONLY`

```bash
cd /path/to/rekep_repair && pip install -e . && pip install -r requirements_gpu.txt
```

## 5. Validate the environment

`REMOTE GPU SERVER ONLY`

```bash
python scripts/check_gpu_environment.py
```

This is *locally dry-run validated* (`--dry-run` works on CPU) but the real check
is *not executed* and **requires remote GPU verification**. It reports a
pass/warn/fail line per requirement and exits non-zero on any hard failure.

## 6. Where the repair layer attaches to ReKep

Keep ReKep's `constraint_generation`, `subgoal_solver`, `path_solver`,
`ik_solver` and its trajectory execution **unchanged**. Attach at exactly three
points in `main.py`'s execution loop:

1. **after the observation/keypoint update** → build `ExecutionContext` and
   `WorldPredicates` (adapter `observe_context` / `active_predicates`);
2. **before ReKep's own backtracking check** → if an event requires repair,
   capture the continuation and splice (this is the one behavioral change);
3. **when asking for the active stage** → read it from `TaskProgram` instead of
   the integer `stage` index.

Everything else — constraint evaluation, optimization, IK, actuation — is ReKep's.

## 7. Milestone 1 (do this before anything else)

See `docs/GPU_MILESTONE_1.md`. Summary: one official ReKep task unchanged → log
stages → wrap in `TaskProgram` → confirm identical nominal behavior → inject one
temporary obstacle → execute one synthesized repair → restore and resume → save
trace + video.

**Do not start sweeps until a single-GPU nominal episode and a single-GPU
repaired episode are both reproducible.**

## 8. Multi-GPU

`scripts/launch_gpu_workers.sh` maps one simulator worker per GPU with isolated
output. See §"Parallelization" there. *Locally syntax-checked only.*

## Known risks

See `docs/GPU_RISKS.md`.
