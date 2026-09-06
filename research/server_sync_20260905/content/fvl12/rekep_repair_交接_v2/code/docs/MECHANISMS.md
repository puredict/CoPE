# Mechanism verdicts (B1 resolution)

Every mechanism was subjected to **activation tracing** (does the ablation move
the intended internal variable?) and **targeted counterfactuals** (does that
change propagate to an outcome?). A class name or a disabled flag was never
accepted as evidence.

Sources: `scripts/ablation_activation.py`, `scripts/mechanism_identification.py`,
`scripts/run_ablations.py`.

## Verdict table

| Mechanism | Ablation active? | Outcome effect | **Verdict** | Basis |
|---|---|---|---|---|
| **Runtime operator synthesis** | yes (goal/plans/selection all differ) | **−0.535 SD** [−0.565, −0.506]; compound SD 0.209 vs 0.952 | **RETAIN — primary claim** | `abl_no_synthesis` |
| **Sequential rollout verification** | yes (survived/selected/trajectory differ) | collisions **0.034 vs 0.004** (≈8×), −0.008 SD (p=0.02) | **RETAIN — primary claim** | `abl_no_rollout` |
| **Continuation handoff (realign target)** | yes (handoff + trajectory differ) | −0.070 SD [−0.086, −0.056]; handoff err 0.132 vs 0.074 | **RETAIN** | `abl_no_cont_contract` |
| **Explicit Realign stage** | yes (generated/survived/selected differ) | changes plan structure; outcome effect scene-dependent | **RETAIN (structural)** | `abl_no_realign` |
| **Event composition (goal union)** | **yes — goal differs in 163/216 compound episodes** | **0/216** plan, selection, or outcome differences | **REFRAME → representation/efficiency, not success** | M2 |
| **Restore gate (contract validation)** | yes (validation call bypassed) | **0 rejections in 706 validations** across none/moderate/severe mismatch | **REFRAME → safety invariant, not success** | M3 |
| **State-dependent scoring** | yes (79.2% of decisions contested; selection changed in 25/432 episodes) | **0 outcome differences** | **REFRAME → plan-quality preference, not success** | M1 |
| **Provenance logging** | no behavioral path | none by construction | **RETAIN as instrumentation** (never claimed causal) | activation trace all `.` |

## Why the three nulls are null — mechanism, not noise

**Event composition is redundant *given the operator precondition structure*.**
The reduced (single-predicate) goal differs from the union in 163/216 compound
episodes — the ablation is genuinely active — yet plans, selections and outcomes
are identical in **0/216**. The reason is architectural: `Realign` requires
`safe_clearance ∧ ¬obstacle_present ∧ object_grasped ∧ object_stable`, and
`Resume` requires `ee_at_handoff ∧ orientation_restored ∧ object_grasped`. So
even a slip-only goal *cannot* be reached without first clearing the obstacle.
The preconditions already encode the composition. Search expansions and candidate
rejections were also identical (7441/7441, 11/11), so it is not even an
efficiency win in this benchmark.

**The restore gate never fires because `Realign` already establishes the
contract.** Across 706 validations at *none*, *moderate* and *severe* mismatch,
the gate rejected **zero** times, and bypassing it changed no outcome. The
`Resume` stage's exit guard is the contract itself, so the program only attempts
the transition once the contract already holds. The gate is a genuine safety
invariant — it is simply never violated in this architecture. Notably this holds
**even under severe mismatch**, which was the hypothesis we set out to test; it
is refuted.

**Scoring is contested but outcome-neutral.** 79.2% of repair decisions have >1
surviving candidate and structural-only scoring changes the selection in 25/432
episodes — so scoring is doing real work. But it produces **zero** outcome
differences, because every candidate that survives rollout verification is
outcome-equivalent. Selection therefore affects plan *quality* (duration,
clearance, handoff error), not success.

## Consequence for the paper

Claim exactly two mechanisms as causal contributions:

1. **runtime operator synthesis** (structural coverage under partial precompilation);
2. **sequential rollout verification** (collision avoidance / physical feasibility);

plus **continuation-carrying restoration** (handoff quality, −0.070 SD).

Event composition, the restore gate, and state-dependent scoring must be
presented as *representation, safety-invariant, and plan-quality* mechanisms
respectively — **not** as success-rate contributions. Per the instruction: the
benchmark was not redesigned to force them significant.

**Candidate simplification.** If a leaner method is preferred, event composition
and state-dependent scoring can both be removed with no measured loss on this
benchmark. The restore gate should be kept despite being null, because it is a
cheap invariant whose violation would be unsafe — but it must not be claimed as
a source of measured gain.
