# Dirty-state audit

## Existing directories: preserved and not clean

### `/home/lijingsu/vla/src/openvla`

- HEAD: `c8f03f48af692657d3060c19588038c7220e9af9`
- tracked modifications:
  - `experiments/robot/libero/run_libero_eval.py`: adds optional
    `max_tasks`/`max_steps_override` smoke limits; working SHA-256
    `f4c1d741489980aa51a409d7a03ec4a08a4dc5710d32d559427b92e339c6a6f3`;
    tracked SHA-256
    `369d9fc3d59067998ebfadafbd516872c7ff6f9f06a0a48cda8b6ca48051de77`.
  - `experiments/robot/openvla_utils.py`: changes Flash-Attention 2 to
    SDPA; SHA-256
    `539687fa13e8fc69b79289cbb2be1b7e1076dcaae4dc0cbfb5e76c6739a38e61`;
    tracked SHA-256
    `72a1a382172c67068c96f47d1c2d8f16925d2e0deda9c745829a7f2ee6b1c865`.
- untracked files: two evaluation logs and
  `experiments/robot/openvla_utils.py.bak_before_sdpa`.
- disposition: unchanged and still dirty. It is not used by the new runtime.

The SDPA change is necessary on the audited environment because
`flash-attn` is absent while PyTorch 2.5.1+cu121 supports SDPA. The smoke-limit
change is convenient but not required for the formal runtime and was
deliberately not carried into the clean branch.

### `/home/lijingsu/vla`

- HEAD: `570d78333ee977c8ae6de3d97120b23272c4c660`
- tracked diff: empty.
- untracked entries: 40 files, comprising `libero_config/config.yaml` and three
  retained recovery-canary output trees.
- disposition: unchanged and still dirty. No output was moved or deleted.

### `/home/lijingsu/vla/src/LIBERO`

This directory had no `.git`; it was ignored by the parent repository's
`src/` rule. The earlier claim that parent commit `570d...` was the LIBERO
commit was therefore invalid provenance.

After excluding six generated `libero.egg-info` files, all 1116 paths, modes,
and Git blob IDs matched official LIBERO commit
`8f1084e3132a39270c3a13ebe37270a43ece2a01` exactly. This allowed a new clean,
content-addressed runtime tree to be established without altering the original.

## New isolated runtime state

| component | path | commit | porcelain |
|---|---|---|---|
| CoPE | `/home/lijingsu/codex-worktrees/cope-true-clean-runtime` | `21b90aed9e2e64152a7bfe0c85553f2ffbc5e730` | empty |
| OpenVLA | `/home/lijingsu/codex-worktrees/openvla-cope-cleanroom` | `9bf418e79d019d416860990d60379d66f0c06220` | empty |
| LIBERO | `/home/lijingsu/codex-worktrees/libero-cope-cleanroom` | `8f1084e3132a39270c3a13ebe37270a43ece2a01` | empty |

LIBERO uses external Git metadata at
`/home/lijingsu/codex-worktrees/libero-cope-cleanroom-metadata.git`. The failed
network clone's original `.git/index.lock` was not deleted. The new metadata is
explicitly shallow at the pinned commit and passes `git fsck --full`; the sole
diagnostic is an unreachable dangling commit, not a missing object or worktree
change.

