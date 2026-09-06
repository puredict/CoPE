# Cold-rebuild artifact protocol

Date frozen: 2026-08-03 (Asia/Shanghai), before wheelhouse construction.

## Scope

Close the remaining Python binary-environment blocker without modifying the
established venv or any experiment output. This protocol does not load a model,
allocate a GPU, run LIBERO, or consume a benchmark state.

## New targets

- wheelhouse: `/home/lijingsu/codex-artifacts/cope-python-wheelhouse-20260803-v1`
- verification venv: `/home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1`

Both targets must be absent at start and must never overwrite an existing
directory. Construction aborts if free space on `/home/lijingsu` is below 50
GiB. The established `/home/lijingsu/vla/.venv` is read-only evidence.

## Inputs

- Python 3.10.12 / Linux x86_64 runtime;
- exact package inventory in `02_PYTHON_LOCK.txt`;
- CUDA 12.1 PyTorch build `torch==2.5.1+cu121` and matching
  `torchvision==0.20.1+cu121`;
- clean LIBERO source at commit
  `8f1084e3132a39270c3a13ebe37270a43ece2a01`;
- clean patched OpenVLA source at commit
  `9bf418e79d019d416860990d60379d66f0c06220`;
- pinned dlimp source commit
  `040105d256bd28866cc6620621a3d5f7b6b91b46`.

The editable LIBERO line is replaced by a wheel built from the clean pinned
source. The dlimp VCS entry is replaced by a retained wheel built from the
pinned commit. Every remaining installed distribution must have one retained,
platform-compatible wheel; sdists alone are insufficient for PASS.

## Required evidence

1. an artifact manifest with filename, normalized distribution name, version,
   byte size, and SHA-256;
2. a complete requirements lock with a hash for every installed artifact;
3. an offline install into the new venv using `--no-index`, the retained
   wheelhouse, and `--require-hashes`;
4. `pip check` success;
5. captured Python/interpreter and critical import/version evidence;
6. the existing 53-check current-host preflight rerun with the new interpreter,
   or an explicit list of any preflight assumptions that still bind it to the
   old interpreter;
7. a clean secret scan and no changes to reserved-state inventory.

## Decision

PASS requires all seven evidence items and a retained wheel for every locked
distribution. Missing/unavailable platform wheels, dependency drift, failed
offline install, import failure, or preflight failure yields FAIL with the
partial wheelhouse retained for diagnosis. No result may be upgraded merely
because the existing shared venv continues to work.
