# Experiment 1 v2.1 repository state

- Audit date: 2026-09-10 (America/Chicago)
- Worktree: `/Users/lijingsu/Documents/cope_repeated_v2_formal_readiness_v2_1`
- Branch: `codex/repeated-v2-formal-readiness-v2_1`
- Required base commit: `1f9372b2703a41fdd881fdc5fab692eb131edf3d`
- Verified local base commit: `1f9372b2703a41fdd881fdc5fab692eb131edf3d`
- Verified remote source branch: `refs/heads/codex/repeated-v2-phase4`
- Verified remote source SHA: `1f9372b2703a41fdd881fdc5fab692eb131edf3d`
- Origin: `https://github.com/puredict/CoPE.git`
- Initial v2.1 worktree status: clean

The v2.1 branch was created with `git worktree add -b` from the exact verified
base commit. Existing experiment files, manifests, calibration outputs, frozen
prompts, reports, claim decisions, and result directories are read-only inputs
to this work. New artifacts use the `repeated_v2_formal_readiness_v2_1`
namespace or an explicitly versioned v2.1 path.

At the base commit, the production learned-policy gate was already satisfied by
`openvla_native` with checkpoint `openvla-7b-finetuned-libero-10`, checkpoint
SHA256 `d36eaa2a334cd52f4a3a94558cf90d82584743ea772fabf76f9e4372e7076076`.
No formal provider call or formal trajectory had been executed.

The final branch HEAD, clean status, commits, tags, and independently queried
remote SHA are recorded after the last completed phase and reported to the
user. A commit cannot contain its own SHA, so this file records the immutable
base and the final response records the self-referential repository state.
