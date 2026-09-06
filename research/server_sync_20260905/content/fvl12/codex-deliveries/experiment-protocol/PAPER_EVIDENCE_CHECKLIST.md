# Paper Evidence Checklist

Use this checklist before writing or submitting any paper, report, poster, or demo page that makes claims about LIBERO / OpenVLA disturbance recovery.

Check every applicable item. If an item is not applicable, write `N/A` and explain why.

## 1. Environment and Version Freeze

- [ ] Hard Rule: Code source is identified by git commit hash or source snapshot checksum.
- [ ] Hard Rule: Working tree diff or source snapshot manifest is archived.
- [ ] Hard Rule: Python version is recorded.
- [ ] Hard Rule: LIBERO version or commit is recorded.
- [ ] Hard Rule: robosuite version is recorded.
- [ ] Hard Rule: MuJoCo version is recorded.
- [ ] Hard Rule: OpenVLA source version or checkpoint package version is recorded.
- [ ] Hard Rule: PyTorch, Transformers, CUDA, and driver versions are recorded when GPU runs are used.
- [ ] Hard Rule: Checkpoint path and checksum or manifest are archived.
- [ ] Hard Rule: Action normalization key is recorded.
- [ ] Recommended Target: Container, conda, venv, or full `pip freeze` is archived.

## 2. Pairing Completeness

- [ ] Hard Rule: Pair key fields are defined before analysis.
- [ ] Hard Rule: Clean and disturbed episodes share checkpoint, suite, task id, initial state id, seed, and budget rule.
- [ ] Hard Rule: Recovery modes and `reactive_disturbed` share the same disturbed pair key.
- [ ] Hard Rule: Missing pairs are counted and reported.
- [ ] Hard Rule: Paired statistics are used only on complete strict pairs.
- [ ] Recommended Target: Pairing audit table is saved as CSV or JSON.

## 3. Seeds and Sample Size

- [ ] Hard Rule: Number of seeds is reported for every table.
- [ ] Hard Rule: Number of tasks and initial states is reported for every table.
- [ ] Hard Rule: 1 to 3 total episodes are labeled smoke or pilot, not formal evidence.
- [ ] Hard Rule: Any claim about generalization is scoped to the tested suite, tasks, checkpoints, and disturbance grid.
- [ ] Recommended Target: Formal runs include at least 5 tasks, 5 initial states per task, and 3 seeds, subject to compute.
- [ ] Recommended Target: Extended runs cover the full selected suite or a preregistered sample.

## 4. Confidence Intervals

- [ ] Hard Rule: Success rates include confidence intervals.
- [ ] Hard Rule: Paired degradation includes paired confidence intervals or a paired test.
- [ ] Hard Rule: Recovery gain over reactive includes uncertainty.
- [ ] Hard Rule: Error bars state the resampling or interval method.
- [ ] Recommended Target: Bootstrap groups respect task and initial-state structure.

## 5. Statistical Methods

- [ ] Hard Rule: Primary comparisons are defined before viewing formal results.
- [ ] Hard Rule: Paired binary comparisons use paired methods when strict pairs exist.
- [ ] Hard Rule: Unpaired descriptive rates are labeled unpaired.
- [ ] Hard Rule: Multiple comparisons are either controlled or labeled exploratory.
- [ ] Hard Rule: Missing, excluded, timeout, stop, and error counts are reported separately.
- [ ] Recommended Target: Extended analysis uses hierarchical bootstrap or mixed-effects logistic regression.

## 6. Failure Videos and Taxonomy

- [ ] Hard Rule: Raw videos exist for all paper example episodes.
- [ ] Hard Rule: Failure labels follow `FAILURE_TAXONOMY.md`.
- [ ] Hard Rule: Failure examples are sampled by a documented rule.
- [ ] Hard Rule: Failure videos are linked to JSONL episode rows.
- [ ] Hard Rule: Annotated videos do not replace raw videos.
- [ ] Recommended Target: Include examples of both recovery success and recovery failure.
- [ ] Recommended Target: Include examples of clean-success/disturbed-failure pairs.

## 7. Manual Run Exclusion

- [ ] Hard Rule: Dashboard, manual button, manual pause, manual step, or hand-disturbed episodes are excluded from autonomous success rates.
- [ ] Hard Rule: Manual episodes are retained in raw archive with `manual_intervention=true` or equivalent.
- [ ] Hard Rule: No failed episode is deleted to improve metrics.
- [ ] Hard Rule: Exclusion reasons are reported by condition.

## 8. Oracle and Reset Labels

- [ ] Hard Rule: `oracle_rollback` is labeled ideal upper bound, not deployable recovery.
- [ ] Hard Rule: `full_reset_replan` is labeled reset baseline, not local replanning.
- [ ] Hard Rule: Tables mark whether each method receives oracle state, reset privilege, rollback privilege, extra prompt information, or extra budget.
- [ ] Hard Rule: Reset/rollback cost is reported separately from policy action count.
- [ ] Recommended Target: Main realistic-method table excludes oracle and full-reset baselines, with a separate diagnostic table for them.

## 9. Ablations

- [ ] Hard Rule: Timing ablation is reported or explicitly marked not run.
- [ ] Hard Rule: Magnitude ablation is reported or explicitly marked not run.
- [ ] Hard Rule: Checkpoint ablation is reported or explicitly marked not run.
- [ ] Hard Rule: Mode ablation includes `reactive_disturbed` as the baseline.
- [ ] Recommended Target: Direction ablation covers cardinal planar directions.
- [ ] Recommended Target: Target-object ablation separates task-relevant object and distractor object.
- [ ] Recommended Target: Prompt-information ablation separates object-only, relocalize, and stage-backtrack prompts.

## 10. Unsuccessful Cases

- [ ] Hard Rule: The paper reports failures, not only successful videos.
- [ ] Hard Rule: Timeout, stop, and infrastructure-error rates are visible.
- [ ] Hard Rule: At least one non-successful case is discussed for each major claimed method, if such cases exist.
- [ ] Hard Rule: Unknown failures are not silently reclassified.
- [ ] Recommended Target: Include a failure taxonomy distribution plot.

## 11. Code and Output Traceability

- [ ] Hard Rule: Every table row can be traced to run directory, config, summary, JSONL, and videos.
- [ ] Hard Rule: Every figure script or notebook records input paths.
- [ ] Hard Rule: Output directories are immutable or copied into an archive before analysis.
- [ ] Hard Rule: Commands and exit codes are archived.
- [ ] Hard Rule: `episodes.jsonl` and `summary.json` are preserved.
- [ ] Hard Rule: If source is not a git repository, a source snapshot checksum is used and commit-level reproducibility is not claimed.
- [ ] Recommended Target: Analysis outputs include a machine-readable manifest.

## 12. Success Semantics

- [ ] Hard Rule: The meaning of LIBERO `done` is audited for the active wrapper.
- [ ] Hard Rule: Success is not assigned by subjective video inspection.
- [ ] Hard Rule: If `done` includes non-success terminations, success and termination must be separated before paper analysis.
- [ ] Recommended Target: Store explicit `success`, `termination_reason`, `timeout`, `stop`, and `error` fields.

## 13. Observation Freshness

- [ ] Hard Rule: State mutation after disturbance is followed by a documented fresh observation rule before policy inference.
- [ ] Hard Rule: Any stale-observation bug is either fixed before formal comparison or analyzed in a separate correctness-audit block.
- [ ] Recommended Target: Log observation timestamps or frame hashes around disturbance, reset, rollback, and prompt-change events.

## 14. Claim Boundary Review

- [ ] Hard Rule: No claim says oracle rollback proves real recovery.
- [ ] Hard Rule: No claim equates full reset with local replanning.
- [ ] Hard Rule: No claim says verifier stop is recovery.
- [ ] Hard Rule: No claim treats preset booleans as measurements.
- [ ] Hard Rule: No claim says prompt rewriting proves a full symbolic recovery architecture.
- [ ] Hard Rule: No stable generalization claim is made from 1 to 3 runs.
- [ ] Hard Rule: No manual episode is included in autonomous success rate.
- [ ] Hard Rule: No failed-stage identification claim is made without an observer or detector.
- [ ] Hard Rule: No degradation claim is made without a reproduced clean baseline.
- [ ] Hard Rule: No paired statistical conclusion is made without strict pairing.

## 15. Final Paper Readiness Sign-Off

- [ ] All hard-rule checklist items are complete or explicitly waived with rationale.
- [ ] Recommended targets not met are listed as limitations.
- [ ] All result numbers match archived outputs.
- [ ] All videos used in paper figures are traceable to formal or explicitly labeled qualitative runs.
- [ ] All limitations include reset/oracle, prompt-only recovery, sample size, detector availability, and success-semantics caveats where applicable.
