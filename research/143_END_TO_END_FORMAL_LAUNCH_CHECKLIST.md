# End-to-end formal launch checklist

Date: 2026-08-04

## Frozen decision order

1. provider operational smoke: one task-independent draw;
2. occurrence learned formal: at most 200 zero-retry calls;
3. occurrence analysis: both neutral and governed gates must pass;
4. task-0 embodied v2: at most 400 zero-retry calls, unlocked only by step 3;
5. embodied v2 analysis: a single-task PASS remains a necessary gate, not a
   complete paper claim.

All commands run under personal account `lijingsu`, from branch
`codex/shared-commit-envelope`, with an initially clean committed worktree.
The credential must be injected into the process environment without appearing
in argv, logs, files, Git, or chat.

## 0. Pre-launch identity and cleanliness

```bash
cd /home/lijingsu/codex-worktrees/cope-shared-envelope
git branch --show-current
git status --porcelain
git rev-parse HEAD
```

Required: branch is `codex/shared-commit-envelope`; status output is empty.
Record the commit hash outside the result interpretation, never the credential.

## 1. Operational smoke

```bash
CUDA_VISIBLE_DEVICES="" scripts/run_project_env.sh \
  /home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1/bin/python \
  experiments/provider_operational_smoke.py \
  --output-dir /home/lijingsu/cope-runs/provider-smoke-v1
```

Proceed only if `00_STATUS.txt` says `PASS`. Any FAIL or an intent without a
response consumes the one draw; do not create a replacement directory.

## 2. Occurrence symbolic formal

```bash
CUDA_VISIBLE_DEVICES="" scripts/run_project_env.sh \
  /home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1/bin/python \
  experiments/occurrence_formal_runner.py \
  --manifest manifests/occurrence_learned_formal_40x5_v1.csv \
  --output-dir /home/lijingsu/cope-runs/occurrence-formal-v1
```

For an ordinary interruption, rerun the identical command with `--resume`.
Never replace an ambiguous intent with a new output directory.

```bash
CUDA_VISIBLE_DEVICES="" scripts/run_project_env.sh \
  /home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1/bin/python \
  tools/analyze_occurrence_formal.py \
  --manifest manifests/occurrence_learned_formal_40x5_v1.csv \
  --event-results /home/lijingsu/cope-runs/occurrence-formal-v1/03_EVENT_RESULTS.csv \
  --output-dir /home/lijingsu/cope-runs/occurrence-formal-v1-analysis
```

Unlock step 3 only when the claim status is
`NECESSARY_SYMBOLIC_GATE_PASS_REQUIRES_EMBODIED_AND_MODEL_REPLICATION` and
`04_DECISION.txt` has `joint_primary_gate=true`. Analyzer exit code 0 alone
means only that analysis completed and is not an unlock signal.

## 3. Task-0 embodied formal v2

Before running, execute `nvidia-smi` as required by repository policy. This
runner uses the scripted controller and must still be launched with
`CUDA_VISIBLE_DEVICES=""`; do not reserve or terminate another user's GPU
process.

```bash
nvidia-smi
CUDA_VISIBLE_DEVICES="" scripts/run_project_env.sh \
  /home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1/bin/python \
  experiments/sequential_formal_runner_v2.py \
  --manifest manifests/sequential_formal_40x5x2_v2.csv \
  --output-dir /home/lijingsu/cope-runs/sequential-formal-v2
```

For an ordinary interruption, use the identical command plus `--resume`. The
runner authorizes only task-0 states 10--29. It does not authorize task-1 state
33 or task-1 states 34--49.

```bash
CUDA_VISIBLE_DEVICES="" scripts/run_project_env.sh \
  /home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1/bin/python \
  tools/analyze_sequential_formal_v2.py \
  --manifest manifests/sequential_formal_40x5x2_v2.csv \
  --event-results /home/lijingsu/cope-runs/sequential-formal-v2/03_EVENT_RESULTS.csv \
  --output-dir /home/lijingsu/cope-runs/sequential-formal-v2-analysis
```

Read `04_DECISION.txt`; do not interpret analyzer exit code 0 as a scientific
PASS. Even `joint_primary_gate=true` remains single-task evidence when the
claim status is `NECESSARY_GATE_PASS_SINGLE_TASK_ONLY`.

## Hard stops

- smoke FAIL or ambiguous smoke intent;
- occurrence infrastructure invalidity;
- occurrence neutral or governed gate failure;
- any nonzero retry;
- embodied shared-substrate incompleteness;
- embodied infrastructure invalidity;
- any attempt to bypass a persisted ambiguous intent;
- any task-1 state-33 retry or task-1 state-34--49 indexing.

## Interpretation ceiling

Occurrence PASS alone supports only a symbolic learned-interface claim.
Embodied v2 PASS is still task-0 single-task evidence. Neither outcome revives
the architecture-first novelty claim or establishes cross-model generality.
