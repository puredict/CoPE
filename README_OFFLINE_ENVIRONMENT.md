# Offline Project Environment

This server should use the project-local launcher for LIBERO / OpenVLA work:

```bash
scripts/run_project_env.sh python check_vla_env.py
```

The launcher only changes the environment of the child process it starts. It does not edit `.bashrc`, system CUDA files, shell startup files, or global library paths.

## Why This Wrapper Exists

The current login environment sets `LD_LIBRARY_PATH=/share/apps/cuda/12.2/lib64:`. On this machine, `/share/apps/cuda/12.2/lib64/libnvJitLink.so.12` is readable as a symlink but fails when opened with an `Input/output error`. PyTorch 2.5.1 in the project virtual environment already provides compatible CUDA 12.1 runtime libraries, so the project wrapper unsets `LD_LIBRARY_PATH` for the child process.

This is a project-level workaround, not a system CUDA repair.

Do not replace, delete, chmod, or add system-level symlinks for files under `/share/apps/cuda/12.2/lib64`.

## Offline Model Path

The server cannot reach Hugging Face from the experiment environment, so commands that use the default repo id `openvla/openvla-7b` will fail if the files are not already cached.

Use the local model path as the standard path on this server:

```text
/home/lijingsu/vla/models/openvla-7b
```

For the OpenVLA smoke test, use:

```bash
scripts/run_project_env.sh \
  python openvla_smoke.py \
  --model /home/lijingsu/vla/models/openvla-7b \
  --device cuda:0 \
  --unnorm-key bridge_orig
```

Keeping `openvla_smoke.py`'s default Hugging Face repo id is intentional for now. Support for an `OPENVLA_MODEL_PATH` environment variable should wait for static audit and a unified configuration pass.

## Run One Command

```bash
cd /home/lijingsu/vla
scripts/run_project_env.sh python check_vla_env.py
```

The wrapper sets project defaults:

```text
MUJOCO_GL=osmesa
PYOPENGL_PLATFORM=osmesa
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
TOKENIZERS_PARALLELISM=false
```

It also sets project-local `PYTHONPATH`, `HF_HOME`, and `TRANSFORMERS_CACHE`.

## Run All Smoke Tests

```bash
cd /home/lijingsu/vla
scripts/run_smokes_offline.sh
```

The smoke launcher runs, in order:

1. `check_vla_env.py`
2. `openvla_smoke.py` with the local model path
3. `libero_base_closed_loop_smoke.py`
4. `libero_disturbance_smoke.py`

It writes logs, stdout, stderr, exit codes, generated files, and GPU snapshots to a new timestamped directory under:

```text
/home/lijingsu/vla/audit_outputs/
```

The launcher uses `bwrap` to bind a fresh audit subdirectory over `/home/lijingsu/vla/smoke_outputs` inside the child process. This prevents the original hard-coded smoke scripts from overwriting existing smoke outputs.
