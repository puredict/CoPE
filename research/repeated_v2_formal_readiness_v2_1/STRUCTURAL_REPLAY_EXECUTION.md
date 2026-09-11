# Sealed structural-witness replay

Status: `PASS`.

The audit replayed all 100 hash-admitted clean-calibration action traces in
LIBERO with eight CPU workers and no model inference. Every terminal outcome
matched its sealed source record. The replay produced two independently
verifiable milestones and a preserved-completed-milestone witness for every
multi-goal task. Task 5 has one source BDDL commitment predicate, so it correctly
fails the frozen two-milestone structural criterion.

The executed replay implementation SHA256 was
`a0a560b16a6b86cc610c01f25cea0ac7e74e7aceddd620f76e91a43cb3395bf6`,
identical on the source worktree and execution host. The run used source commit
`53009d1d19f1cae6fd334365733e61771bea2830`, `CUDA_VISIBLE_DEVICES=` and
`MUJOCO_GL=osmesa`. Exit code was 0. Provider calls, VLA calls, and formal
trajectories were all zero.

An earlier single-worker invocation was stopped after the parallel run
reproduced its first three ordered outcomes. Its incomplete output was retained
and was not used by the catalog builder. Only the complete parallel directory
`structural_replay_53009d1_parallel_01` supplies the evidence below.

| Artifact | SHA256 |
| --- | --- |
| `REPLAY_EPISODE_ADMISSION.csv` | `73ceac372173a911400ca0d01235ba951ed201295bb6d90966c3c2eae19d47f5` |
| `REPLAY_MILESTONE_WITNESSES.csv` | `f5efafbe60313e6b0960e38e84f911d231c88db74e8333f7ce71a3cbbd9bfc39` |
| `REPLAY_STRUCTURAL_WITNESS_SUMMARY.csv` | `e02a8c48048a1308fb2fb027123d206e7200f0b511051934ae3fef562cb92ecc` |
