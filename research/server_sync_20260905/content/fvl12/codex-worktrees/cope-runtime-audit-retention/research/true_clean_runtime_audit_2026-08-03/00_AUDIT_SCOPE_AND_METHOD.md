# CoPE OpenVLA + LIBERO true-clean runtime audit

Date: 2026-08-03 (Asia/Shanghai)

## Scope and safety boundary

This audit covers the local CoPE research directory and the remote runtime on
`lijingsu@10.176.53.120:26575` (`fvl12`). It was performed to close the
`external_runtime_provenance` failure in readiness v3 without cleaning,
resetting, deleting, moving, or overwriting the user's existing source trees or
experiment outputs.

The first local command and the first successfully authenticated remote command
were both `nvidia-smi`. The local macOS host has no `nvidia-smi`. The remote
host reported eight RTX 3090 GPUs, driver 535.54.03 and CUDA capability 12.2;
all GPUs were at 12 MiB and 0% utilization. No GPU was allocated.

No model provider was called, no checkpoint was loaded, no simulator or robot
experiment was run, no individual reserved-state packet was read, and no
formal output directory was created. States 27--49 remain locked; 47--49 remain
permanent reserve.

## Identity algorithm

File identity is SHA-256 over raw bytes. A directory content identity is
SHA-256 over sorted records:

```text
relative_path NUL decimal_size NUL file_sha256 LF
```

The checkpoint aggregate and LIBERO content identity use this exact algorithm.
Transient `__pycache__`, `.pyc`, `.pyo`, `.DS_Store`, and the failed clone's
internal `.git/` metadata are excluded from the LIBERO content identity. No
runtime source file is excluded.

## Result classes

- `PASS_CURRENT_HOST`: the currently established host runtime passes every
  fail-closed preflight check.
- `FAIL_COLD_REBUILD`: reconstruction on an empty host is not yet fully
  content-addressed because the Python package wheel artifacts are not retained
  with hashes.
- `NO_GO_FORMAL`: readiness v3's learned-to-live bridge gate remains outside
  this runtime audit and still blocks reserved-state formal experiments.

