# Clean-room reconstruction and verification

These commands construct sources and configs only. They do not start an
experiment, instantiate LIBERO, load OpenVLA, call a provider, or create the
formal output directory.

## 1. Source recovery from pinned commits

If the established remote worktrees still exist, use them directly:

```bash
COPE_ROOT=/home/lijingsu/codex-worktrees/cope-true-clean-runtime
OPENVLA_ROOT=/home/lijingsu/codex-worktrees/openvla-cope-cleanroom
LIBERO_ROOT=/home/lijingsu/codex-worktrees/libero-cope-cleanroom
```

On an empty host, reconstruct OpenVLA without touching any dirty checkout:

```bash
git clone --filter=blob:none https://github.com/openvla/openvla.git /home/lijingsu/repro-repos/openvla.git
git -C /home/lijingsu/repro-repos/openvla.git worktree add -b codex/openvla-cope-sdpa /home/lijingsu/codex-worktrees/openvla-cope-cleanroom c8f03f48af692657d3060c19588038c7220e9af9
git -C /home/lijingsu/codex-worktrees/openvla-cope-cleanroom apply /path/to/03_OPENVLA_REQUIRED_SDPA_PATCH.txt
git -C /home/lijingsu/codex-worktrees/openvla-cope-cleanroom diff --check
```

Reconstruct official LIBERO using a detached worktree rather than copying the
ignored original tree:

```bash
git init --bare /home/lijingsu/repro-repos/LIBERO.git
git --git-dir=/home/lijingsu/repro-repos/LIBERO.git remote add origin https://github.com/Lifelong-Robot-Learning/LIBERO.git
git --git-dir=/home/lijingsu/repro-repos/LIBERO.git fetch --depth=1 origin 8f1084e3132a39270c3a13ebe37270a43ece2a01
git --git-dir=/home/lijingsu/repro-repos/LIBERO.git worktree add --detach /home/lijingsu/codex-worktrees/libero-cope-cleanroom 8f1084e3132a39270c3a13ebe37270a43ece2a01
```

Reconstruct CoPE from its parent commit and retained patch:

```bash
git -C /home/lijingsu/vla worktree add -b codex/cope-true-clean-runtime /home/lijingsu/codex-worktrees/cope-true-clean-runtime fba9f32b502c8301687559a62101293105f17254
git -C /home/lijingsu/codex-worktrees/cope-true-clean-runtime apply /path/to/07_COPE_RUNTIME_PIN_PATCH.txt
git -C /home/lijingsu/codex-worktrees/cope-true-clean-runtime diff --check
```

The already-established commits are `9bf418e...` and `21b90ae...`; when they
are available in the local object databases, prefer adding detached worktrees
directly at those commits.

## 2. Isolated LIBERO and reservation configuration

```bash
mkdir -p /home/lijingsu/codex-worktrees/cope-runtime-config-20260803
scp 06_LIBERO_CONFIG_CLEANROOM.txt fvl12:/home/lijingsu/codex-worktrees/cope-runtime-config-20260803/config.yaml
scp 05_RESERVED_STATE_LOCK.csv fvl12:/home/lijingsu/codex-worktrees/cope-runtime-config-20260803/reserved_state_lock.csv
scp 09_PREFLIGHT_CHECK.txt fvl12:/home/lijingsu/codex-worktrees/cope-runtime-config-20260803/preflight_check.txt
```

Expected SHA-256 values are respectively `aa8aa28d...`, `3e66003b...`, and
`20fc15d1...`.

## 3. Checkpoint recovery

The checkpoint repository and revision are:

```text
openvla/openvla-7b-finetuned-libero-10
80970322773f81baa2e22fe495d0487b93a05cfa
```

If the local checkpoint is lost, an explicitly authorized download may use the
pinned revision and a new, absent target directory. Do not overwrite the
current checkpoint. The preflight must then reproduce all 15 file hashes and
aggregate `2990c991...` before use.

## 4. Python environment

The current host uses `/home/lijingsu/vla/.venv/bin/python` and passes freeze
hash `d238fb71...` plus `pip check`. For a genuinely cold rebuild, first create
an immutable wheelhouse and a requirements lock with SHA-256 for every wheel,
including the CUDA-enabled PyTorch artifacts. Then install with:

```bash
python3.10 -m venv /home/lijingsu/codex-worktrees/cope-runtime-python
/home/lijingsu/codex-worktrees/cope-runtime-python/bin/python -m pip install --no-index --find-links /path/to/pinned-wheelhouse --require-hashes -r /path/to/requirements-with-hashes.txt
```

`02_PYTHON_LOCK.txt` is an exact version inventory, not a substitute for that
missing artifact lock. Until the wheelhouse is retained and verified, cold
rebuild status remains FAIL.

## 5. Mandatory preflight

Choose a new absolute output path that does not exist. The script checks but
does not create it:

```bash
cd /home/lijingsu/codex-worktrees/cope-true-clean-runtime
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python \
  /home/lijingsu/codex-worktrees/cope-runtime-config-20260803/preflight_check.txt \
  --output-dir /home/lijingsu/codex-deliveries/cope_formal_UNIQUE_RUN_ID
```

Any nonzero exit blocks execution. The script fails on commit mismatch,
tracked or untracked source changes, checkpoint file/set/hash changes,
runner/config hash changes, output collision, Python/environment drift, and any
reserved-state lock mismatch.

Even a runtime PASS does not authorize formal states. The learned-to-live X15
gate and the complete readiness decision must separately pass first.

