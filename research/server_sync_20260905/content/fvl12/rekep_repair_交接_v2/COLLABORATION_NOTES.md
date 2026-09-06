# Collaboration notes

Internal document for the two coauthors. Not for external distribution.

## Project objective

Enable a robot to **modify the structure of an actively executing ReKep
constraint program online** in response to an interruption, verify the
modification before committing to it, and then safely restore and resume the
interrupted task.

Working positioning:

> Verified online structural repair of an actively executing ReKep constraint
> program.

## Intellectual history

* **The abstract idea of online repair originated from the collaborator.** The
  starting insight — that a disturbance may require changing the *structure* of
  the task program rather than only re-optimizing a trajectory inside a fixed
  stage — is hers.
* From that starting point the project has been **jointly developed** into:
  a formal problem statement; an implemented method (program IR, stage state
  machine, continuation capture, operator synthesis, rollout verification,
  splice/restore/resume); theoretical results (conflict lower bound, search
  soundness, termination, conditional completeness, coverage–complexity,
  conditional restoration); and an experimental program (randomized paired
  benchmark, strong precompiled baselines, ablations, model-mismatch study).
* **Authorship, author order, and CRediT statements are not decided.** They will
  be agreed jointly before submission. Nothing in this folder should be read as
  fixing them. No percentages or ordering are recorded anywhere in this handoff
  by design.

## Current division of work (descriptive, not a contribution claim)

| Area | Status |
|---|---|
| Abstract online-repair idea | originated by the collaborator |
| Formalization, CPU implementation, theory drafts, CPU experiments | jointly developed in this repository |
| GPU / ReKep–OmniGibson execution | **not started**; this handoff prepares it |

## Decisions still requiring joint agreement

1. **Paper framing.** Current frozen framing is a *coverage–storage–adaptability
   trade-off*, **not** superiority over precompiled recovery. The strong
   parameterized offline baseline is **exactly equal** to online when the exact
   branch is precompiled (0/0 discordant pairs, p = 1.0). Do we keep this
   bounded framing, or foreground a different axis?
2. **Which mechanisms are claimed as contributions.** Measurement supports four
   primary claims; three further mechanisms are internally active but
   outcome-neutral (see `PROJECT_STATUS.md`). Do we present those three as
   secondary properties, or remove them from the method to simplify?
3. **Venue and scope.** ICRA-length paper with simulator evidence only, or wait
   for real-robot results?
4. **How much theory to include.** Six results are drafted; a robotics venue may
   want two plus an appendix.
5. **Whether to keep event composition and state-dependent scoring at all.**
   Both can be removed with no measured loss on the current benchmark.

## Open questions for the coauthors

* The **restore gate never rejects** — 0 rejections in 706 validations, including
  under severe model mismatch. It is a safety invariant that always holds in this
  architecture. Is that a result worth stating, or a component to drop?
* **Task success saturates at 0.637** for both online and offline-exact. The
  remaining failures come from the nominal controller and the strict terminal
  criteria, not from recovery. Should the benchmark's terminal criteria be
  relaxed, or is the low ceiling itself informative?
* **Physics nondeterminism in OmniGibson** may weaken the paired-seed protocol
  the entire CPU statistics section relies on (risk R3). Agreeing on a tolerance
  policy *before* the GPU runs would save a re-run.
* Do we report the **negative results** (conservative margins and
  receding-horizon reverification both fail) in the paper, or only in an
  appendix? They are currently excluded from the contributions.

## CRediT roles — to be completed jointly

<!-- Fill in together before submission. Deliberately left blank. -->

| CRediT role | Person |
|---|---|
| Conceptualization | |
| Methodology | |
| Software | |
| Validation | |
| Formal analysis | |
| Investigation | |
| Data curation | |
| Writing — original draft | |
| Writing — review & editing | |
| Visualization | |
| Supervision | |
| Project administration | |

Author order: **to be agreed.**
