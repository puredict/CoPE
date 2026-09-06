# Cold-rebuild Python runtime result

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**PASS for the pinned Linux x86_64 / Python 3.10 / CUDA 12.1 host class.**

The previously missing Python artifact lock is now backed by a retained
wheelhouse at:

`/home/lijingsu/codex-artifacts/cope-python-wheelhouse-20260803-v1`

and was installed with no package index into a new, previously absent venv:

`/home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1`

The established `/home/lijingsu/vla/.venv` was not modified.

## Artifact closure

- 199 expected distributions;
- 199 retained compatible wheels;
- 4 source distributions additionally retained for bddl, evdev, gym, and
  promise, with locally built wheels also retained;
- 203 binary artifacts in the manifest;
- 199/199 requirements carry exact SHA-256 hashes;
- zero missing, extra, ambiguous, or version-mismatched distributions;
- zero manifest size/hash mismatches;
- wheelhouse size approximately 3.8 GiB;
- clean verification venv size approximately 8.4 GiB;
- free filesystem space after construction approximately 56 GiB.

LIBERO was built from clean commit
`8f1084e3132a39270c3a13ebe37270a43ece2a01`, tree
`99f4ada3f1d62e026fc9ff2390eb4ff8a1760e60`. Setuptools created ignored
`build/` and `libero.egg-info/` directories in that source tree; only those two
regenerable build products were removed. The original 1,116-file LIBERO content
hash was restored before final verification.

GitHub was temporarily unreachable while rebuilding dlimp. The retained dlimp
wheel was therefore recovered from the 25 files enumerated by the installed
distribution RECORD. Its retained `direct_url.json` binds those files to commit
`040105d256bd28866cc6620621a3d5f7b6b91b46`; the source RECORD, direct-url
metadata, and recovered wheel each have independent hashes in
`23_SOURCE_WHEEL_PROVENANCE.txt`. The offline installation and import test
validate that recovered wheel.

## Offline verification

The new venv was installed with:

- `--no-index`;
- the retained wheelhouse only;
- `--require-hashes`;
- the complete 199-line lock.

Verification results:

- offline install exit 0;
- `pip check`: no broken requirements;
- installed distributions: expected 199, actual 199;
- no missing, extra, or version mismatch;
- critical imports pass for torch, torchvision, transformers, robosuite,
  mujoco, numpy, dlimp, and LIBERO;
- critical versions match the established runtime;
- `torch==2.5.1+cu121`, CUDA build 12.1;
- Python executable SHA-256 remains
  `5ea655542025bb2bbf1036b59546f860d1400fda31456a83e22e688ce40a047d`;
- cold freeze SHA-256 is
  `4cf8a2c18914cd631b8ef38e8b8010aa6f86ae5b0e2faca1a30089beb08380e5`;
- secret scan PASS.

## Full runtime preflight

The fail-closed preflight was rebound only to the new venv path and cold freeze
hash. It then passed all 53 checks, including source commits and cleanliness,
LIBERO content address, all checkpoint files, runtime files, configs, package
versions, import resolution, environment variables, and the full locked
reserved-state inventory.

Final line:

`FINAL PASS checks=53;provider_calls=0;simulator_runs=0;reserved_state_packets_read=0;output_created=false`

## Scope

This wheelhouse is platform-specific, not a universal OS image. Reconstruction
requires a compatible Linux x86_64 system with Python 3.10 ABI, glibc/driver
compatibility, and the pinned source/checkpoint assets. Within that declared
host class, the former empty-host Python artifact blocker is closed.

This runtime result does not by itself authorize formal embodied states.
Reserved states 27--49 remain locked and 47--49 remain permanent reserve until
the development-only shared-envelope embodied canary passes.
