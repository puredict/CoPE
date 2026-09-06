# Window 4 statistical preregistration

This document fixes the analysis and claim rules before any v2 formal result is available. It supplements the frozen scientific protocol without replacing its research hypothesis. The analysis-code commit and this document must be included in the pre-call freeze. Changing these rules after observing formal results requires a new, explicitly exploratory analysis label; it cannot replace the registered decision.

## Units, populations, and integrity

The experimental unit is a master session: task, initial state, policy seed, and master event schedule. Arms and all checkpoints from one session remain together in every paired comparison and bootstrap draw. An event or checkpoint is never treated as an independent sample. Master sessions receive equal weight; this estimates performance over the frozen session grid, not an unobserved population of tasks. Task-level summaries are descriptive.

Analyze controlled and learned-VLA protocols separately. The primary condition is `evidence_matched`. `token_matched` is a secondary descriptive condition and must not substitute for the primary condition. The primary learned-VLA comparison is at K=4; controlled terminal comparison is K=8. Intermediate checkpoints are from the same continuous arm trajectory, without oracle reset. All frozen sessions remain in the denominator, including method failures, timeouts, rejected transactions, and unreachable later events.

Audit the exact expected cell inventory, unique ownership, pairing, journal lineage, complete-protocol status, protocol identities, evidence/call parity, and frozen hashes before reporting statistics. Missing, duplicated, or unexpected submitted result cells and protocol/hash drift invalidate an attempted completed run. A run that has not been launched or has been explicitly stopped for missing infrastructure is blocked, not a completed negative experiment. A partial run cannot support a claim. Never delete an unfavorable cell, create a synthetic formal cell, silently pool v1, or interpret a missing value as zero failure or success.

The primary comparator must be selected on a disjoint development split, choosing highest K=4 success, then lowest history corruption, then lexicographic method name. Eligible comparators are `full_state_regeneration`, `full_history_replan`, `rag_replan`, `summary_memory_replan`, `skill_local_replan`, and `classical_execution_monitor`. Comparator identity and development provenance must be frozen before formal calls.

## Estimation and fixed inference

For binary final active-task success, report the mean paired difference `Y_CoPE - Y_comparator`, all four paired outcome counts, the discordant counts, and the two-sided exact McNemar binomial p-value. With no discordant pairs, the exact p-value is 1; this is not proof of equivalence. Report Wilson 95% intervals for each arm's session success rate; separate marginal Wilson intervals do not replace paired inference.

The confirmatory paired 95% interval is the percentile master-session cluster bootstrap with 10,000 replicates. Sample complete sessions with replacement and carry every arm and every checkpoint from each sampled session together. Preserve repeated selections as distinct draws. The default seed is 20260906; any configuration override must be frozen before formal calls. Use lexicographically sorted session IDs, Python `random.Random(seed).randrange(n)` for n draws per replicate, and linear empirical quantiles (Hyndman–Fan type 7). Freeze replicate count, seed, implementation, and interpolation rule before formal calls. Do not choose seeds or intervals according to significance. A zero-session denominator is undefined and blocks inference; it is never assigned a favorable estimate. Degenerate bootstrap intervals must be flagged, not described as proof of population equivalence.

The generic persistent control uses the same paired session bootstrap, with the 5th percentile as a one-sided 95% lower confidence bound for CoPE minus generic success. Non-inferiority is established only when this bound is strictly greater than -0.05. Equality to -0.05 fails the gate. Non-inferiority is not equivalence; failure to establish non-inferiority does not establish inferiority. Cost, invalid-transaction rate, and latency remain separately measured outcomes.

## Fixed degradation fallback

The protocol permits a preregistered cluster-bootstrap fallback to a mixed-effects logistic interaction. This implementation selects that fallback in advance because a production, convergence-qualified mixed-effects fitting backend is not part of the frozen dependency contract. Record `preregistered_paired_master_session_bootstrap_ols_log2_k_plus_1` as the scaling method in the report. No mixed model has been attempted, and no convergence failure is asserted. Do not select the estimator after inspecting fitted effects, p-values, or formal data.

For each complete session and arm, fit an ordinary least-squares slope of binary success against `log2(K+1)` on K=0,1,2,4 for learned-VLA and K=0,1,2,4,8 for controlled. Average the paired within-session CoPE-minus-comparator slope differences. Bootstrap complete paired sessions as above. All checkpoints are required, including failures, so a session is not fitted using only successful or reached checkpoints. A positive difference indicates a flatter CoPE degradation curve. The binding scaling gate requires both a positive point estimate and a strictly positive two-sided 95% lower bootstrap bound. A point estimate alone is insufficient. This probability-scale fallback must not be described as a fitted logistic odds interaction.

## Mechanism denominators and timing

History corruption and completed-step regression are each reported as session incidence: at least one audited occurrence through the terminal checkpoint, divided by all complete paired master sessions. Additional event-level rates may be descriptive with explicit denominators. Unreached events after prior failure remain recorded as such; they are not fabricated mutation measurements. Report early-failure and event-unreached incidence alongside these mechanism rates so low corruption caused by early termination is visible.

The halving gate requires both `CoPE corruption <= 0.5 * comparator corruption` and `CoPE regression <= 0.5 * comparator regression`. If the comparator incidence is zero, CoPE must also be zero. This satisfies the literal non-increase threshold but is not evidence of a measured twofold reduction; the report must say both were zero and leave the ratio undefined. If any incidence denominator or necessary measurement is missing, the gate is unknown and cannot pass.

Planning-problem fidelity is scored on the normalized compiled problem before the corresponding execution segment. Its gate uses an opportunity score: for each session, the fraction of scheduled post-event checkpoints that were reached and had an exactly matching planning problem before execution; then average over all sessions. An unreached opportunity contributes zero to this composite score, explicitly because it was not reached, not as a fabricated measured mismatch. Also report reached-only exact fidelity, field-level macro F1, and the unreached fraction descriptively. If existing runtime artifacts do not allow the opportunity score or temporal audit, this gate remains unknown. Never infer temporal precedence from higher final-state correctness, wall-clock correlation, or execution success.

The temporal audit must link the post-event planning-problem record to its event/occurrence and subsequent action trace, and show that scoring used the accepted state prior to execution. The gate requires the CoPE opportunity score to exceed the frozen comparator score and the audit to confirm this order. Higher fidelity observed only after execution cannot pass.

## Prespecified Holm family

The secondary family has exactly 13 two-sided terminal-success exact McNemar tests, all in `evidence_matched`:

- Controlled K=8: CoPE versus each of the seven other non-oracle methods (seven tests).
- Learned-VLA K=4: CoPE versus each of the seven other non-oracle methods, excluding the single frozen primary nonpersistent comparator (six tests).

The generic persistent method is included in these two-sided secondary comparisons. Oracle comparisons are descriptive upper bounds and are excluded. The single primary learned-VLA comparison is unadjusted. The prespecified one-sided generic non-inferiority test is a separate binding gate, not an extra exploratory member of this two-sided family. No intermediate-checkpoint significance tests, token-matched tests, or field-level significance tests are silently added. Mechanism, taxonomy, and efficiency estimates are descriptive unless separately frozen before formal calls.

Apply Holm at familywise alpha=0.05: sort raw p-values ascending, multiply the ith by `m-i+1`, take the cumulative maximum, and clip at 1, with m=13. Preserve the full family even if some comparisons are unavailable. A missing slot may receive internal p=1 only for conservative multiplicity bookkeeping; it must never appear as an observed p-value or a fabricated result row. If either protocol or any member is incomplete, label the family incomplete and make no complete-family adjusted-significance claim. Do not shrink the family to the available or favorable comparisons.

## Binding decision precedence

The decision code accepts separate completeness/integrity attestations for controlled evidence and learned-VLA evidence. Unknown values never pass a gate.

1. **INVALID_RUN:** Any failed integrity check, explicit invalid reason, invalid numeric estimate, protocol/checkpoint mismatch, or evidence/call-parity breach takes precedence over blockers and apparently positive results. No confirmatory inference is admissible.
2. **PARTIAL_SUPPORT, controlled only:** If learned-VLA is blocked, separately complete and validated controlled evidence may support this status only when controlled execution has a positive paired 95% lower bound, degradation is flatter by the registered interval, both mechanism incidence thresholds pass, pre-execution fidelity is higher with verified order, and parity passes. Retain all VLA blockers and explicitly prohibit learned-VLA claims. Incomplete controlled cells cannot satisfy this exception.
3. **BLOCKED_*:** Otherwise any missing formal readiness, frozen comparator, complete VLA evidence, required gate measurement, or integrity attestation blocks the runtime decision. A zero denominator or unknown gate is a blocker, not a passed gate or a negative observed effect.
4. **GO:** Complete, valid learned-VLA evidence passes all seven runtime gates below.
5. **PARTIAL_SUPPORT:** Complete, valid evidence fails at least one runtime gate but has a positive paired execution lower bound plus higher temporally preceding fidelity, or separately meets the complete controlled mechanism criteria. State exactly which conclusion is supported. This does not license the full registered runtime claim.
6. **NO_GO:** Complete, valid evidence meets neither GO nor the fixed partial-support rule. Token savings by themselves never satisfy either runtime-support rule.

The seven learned-VLA gates are: K=4 risk difference at least 0.10; paired two-sided 95% lower bound strictly above zero; positive slope difference with positive lower 95% bound; both corruption and regression at most half the comparator incidence; higher pre-execution planning fidelity with verified temporal order; one-sided 95% generic lower bound strictly above -0.05; and verified evidence/hidden-information and event-level reasoner-call parity. All are conjunctive; neither a small p-value nor cost savings overrides a failed gate.

## Claims and limits

A GO supports the fixed hypothesis only within the tested tasks, schedules, methods, and frozen execution stack: persistent local editing preserves the planning problem and improves downstream execution as interruptions accumulate. It does not establish universal safety, perception competence, open-world specification induction, or generalization to untested distributions.

If CoPE and the information-equivalent generic persistent control are not distinguished in execution accuracy, any shared reliability benefit supports persistent responsibility structure. The typed carrier provides compact representation, direct validation, and atomic transactions; measured efficiency advantages require separate evidence. A confidence interval including zero is not a proof of equivalence, and non-inferiority alone never proves typed semantic superiority.

Controlled evidence is mechanism evidence only. Semantic-state correctness is not physical success; rejected patches are not recovery successes; unavailable adapters are not observed result cells; a custom repair backend is not original published ReKep. `REPORT.md` and `CLAIM_DECISION.md` must retain all failed and unknown gates, blockers, denominator limits, paper-safe claims, and forbidden claims.
