# READ THIS FIRST  (v2)

> **This is handoff v2.** It supersedes `rekep_repair_交接/` and is
> self-contained — do not merge from v1. Start with `CHANGELOG_FROM_V1.md`,
> which lists every change, why, and which v1 GPU claims survive.
>
> v2 adds the four GPU fixes (P0-1 task-success evaluator, P0-2 real candidate
> rollout verification with state isolation, P0-3 non-tautological restore
> contract, P0-4 paired baselines) plus live structured logging. The frozen CPU
> architecture is **unchanged**; all 71 original CPU tests still pass, and 23 new
> GPU-metric tests were added (94 total).

**Audience:** my coauthor/collaborator, who is taking over GPU execution on the
8× RTX 3090 server.

## What this project is

A robot executing a **ReKep** relational-keypoint constraint program is
interrupted (a hand intrudes, the object slips, the target moves). Instead of
only re-optimizing a trajectory inside the current stage, or selecting a
recovery branch that was compiled before execution, the system:

1. detects the event and captures a **continuation** of the interrupted stage;
2. builds an event-conditioned **repair goal** from the active world predicates;
3. **synthesizes** a repair program at runtime by searching over atomic typed
   operators (it does not look up a stored sequence);
4. **verifies** each candidate by a sequential rollout against the real geometry;
5. **splices** the winner into the live task graph (interrupted stage becomes
   `SUSPENDED`, never `COMPLETED`);
6. validates a **restore contract** and **resumes** the interrupted stage.

The bounded claim — please keep it bounded:

> Online repair is **not** universally superior to precompiled recovery. When
> the exact recovery branch is precompiled, a strong parameterized offline
> baseline is **exactly equal** (0/0 discordant pairs, p = 1.0). The online
> advantage is compact operator storage, runtime structural adaptability, and
> better coverage under *partial* precompilation.

## What has already been validated (CPU, on my machine)

* 71 automated tests pass.
* Randomized paired benchmark: 3 task families × 6 event conditions × 3
  severities × 50 paired seeds × 6 methods = **16,200 episodes**.
* Ablation study (**8,640 episodes**) identifying which mechanisms are causal.
* Model-mismatch study (**17,280 episodes**) plus per-dimension attribution
  (**16,740 episodes**).
* Six theoretical results drafted with explicit assumptions.

## What has NOT been run — anywhere

* **Everything GPU.** No CUDA, Isaac Sim, OmniGibson, or ReKep code has been
  executed by me. My machine is CPU-only macOS; OmniGibson cannot run on it.
* All GPU scripts here are **dry-run validated or syntax-checked only**.
* Every version pin in `GPU_HANDOFF.md` is **proposed, not confirmed on
  hardware**.

Please do not read any GPU artifact in this folder as tested.

## Where the technical report is

```
report/rekep_repair_technical_report.pdf
```

Start with §1 (executive summary) and §2 (research origin). §7 is the code map,
§10 the results, §13 the GPU plan.

## The first command to run on the GPU server

`REMOTE GPU SERVER ONLY`

```bash
python scripts/check_gpu_environment.py --dry-run
```

Run the **dry-run first** even on the GPU box: it validates the repo and the CPU
stack without importing anything GPU-only, so a failure there is unambiguous.
Then follow `GPU_RUNBOOK.md` in order. Do not skip to a sweep — the launcher
refuses to start one until Milestone 1 passes.

## Reading order

1. `README_FIRST.md` (this file)
2. `PROJECT_STATUS.md` — what is done vs. untested
3. `report/rekep_repair_technical_report.pdf` — the full account
4. `GPU_RUNBOOK.md` — exact commands, in order
5. `KNOWN_RISKS.md` — read **before** installing; R1 alone can cost days
6. `COLLABORATION_NOTES.md` — open questions for us to settle together

## Folder layout

```
report/          technical report (.tex + compiled .pdf + figures/tables)
code/            complete reproducible project (CPU + adapter + GPU scripts)
results_cpu/     frozen CPU result artifacts + regeneration commands
configs_gpu/     GPU config templates (placeholders, no local paths)
scripts/         thin runners for CPU repro and GPU milestones
*.md             handoff documentation
handoff_manifest.json / SHA256SUMS.txt / VALIDATION_REPORT.md
```

## One thing to know before you start

The CPU study found that **observation-side error dominates** damage
(stale observations ΔSD +0.367, object-position noise +0.280), while actuation
gain error is nearly harmless (+0.004). Real ReKep keypoint tracking is exactly
the noisy, latent signal that this predicts will hurt. Expect predicate
stability — not control accuracy — to be the first real problem.
