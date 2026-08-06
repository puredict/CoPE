# Critical experiment launch decision and runbook

Date: 2026-08-04
Current authoritative branch: `codex/shared-commit-envelope`
Current smoke implementation commit: `d5de43d444bbea03699aa116c17d2848ab773825`

## Decision

The most informative experiment is now launch-ready in code. The only external
blocker is secure credential injection. Run in this order:

1. one task-independent provider operational smoke;
2. the 200-call occurrence-sensitive symbolic learned formal gate;
3. analyze both neutral and governed co-primary comparisons;
4. run the 400-call task-0 embodied formal v2 **only if** step 3 passes both
   primary gates.

This ordering minimizes wasted calls and answers the remaining publishable
question before spending on the older, Tang-collided architecture route.

## Why occurrence formal comes first

- It directly tests the residual contribution: a compact minimum delta for a
  recurring grounded commitment with a new temporal occurrence.
- It has no simulator/controller confound and only 200 fixed calls.
- Neutral and governed controls are occurrence-aware and representation
  matched; FSR-PC cannot rescue a primary tie.
- A tie/loss against either primary control is a method-paper NO-GO even if
  CoPE beats FSR-PC.
- A dual-primary PASS is still only a necessary symbolic result, but it makes
  the later embodied spend rational.

## Secure launch commands

Run only from the authoritative worktree with a clean status. The credential
must already exist in the remote process environment; do not put it in a
command line, file, report, shell history, or chat.

```bash
cd /home/lijingsu/codex-worktrees/cope-shared-envelope
git status --porcelain
CUDA_VISIBLE_DEVICES="" ./scripts/run_project_env.sh \
  /home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1/bin/python \
  experiments/provider_operational_smoke.py \
  --output-dir /home/lijingsu/cope-runs/provider-smoke-v1
```

Proceed only if `00_STATUS.txt` says `PASS`. Then:

```bash
CUDA_VISIBLE_DEVICES="" ./scripts/run_project_env.sh \
  /home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1/bin/python \
  experiments/occurrence_formal_runner.py \
  --manifest manifests/occurrence_learned_formal_40x5_v1.csv \
  --output-dir /home/lijingsu/cope-runs/occurrence-formal-v1
```

If the process stops after the output directory is created, use the identical
command with `--resume`; completed or response-persisted cells are never
called again. Do not start a new output directory to bypass an ambiguous cell.

After exactly 200 result cells:

```bash
CUDA_VISIBLE_DEVICES="" ./scripts/run_project_env.sh \
  /home/lijingsu/codex-worktrees/cope-runtime-python-20260803-v1/bin/python \
  tools/analyze_occurrence_formal.py \
  --manifest manifests/occurrence_learned_formal_40x5_v1.csv \
  --event-results /home/lijingsu/cope-runs/occurrence-formal-v1/03_EVENT_RESULTS.csv \
  --output-dir /home/lijingsu/cope-runs/occurrence-formal-v1-analysis
```

## Stop rules

- smoke failure: stop, no retry;
- smoke intent without response: classify as an ambiguous consumed draw; do
  not create a replacement output directory;
- infrastructure-invalid formal run: retain it, do not interpret efficacy;
- neutral or governed NO-GO: stop the method-paper route;
- symbolic dual-primary PASS: report it as necessary but non-embodied, then
  unlock task-0 formal v2;
- never retry task-1 state 33 or index task-1 states 34--49;
- task-7 states 3--49 remain stopped under the current controller.

## Current paper status before outcomes

Architecture novelty: NO-GO after the Tang collision.
Occurrence interface/benchmark: HOLD, experimentally testable.
ICRA method paper: weak reject / not submission-ready.
Immediate blocker: secure credential plus the one-draw smoke—not missing code.
