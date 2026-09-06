# Go / no-go gate for ReKep–OmniGibson integration

**DECISION: CONDITIONAL GO.**

Both prior blockers are **resolved as investigations** — B1 and B2 are now
measured rather than open. But B2 produced a *negative* result that changes what
may be claimed, and one gate criterion is not met. Integration may proceed on a
reduced, honest claim; it may not proceed on the original claim.

---

## Gate criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Every retained mechanism has a measurable causal effect **or** a clear efficiency/representation justification | **MET** (after reframing 3 of 8) | [MECHANISMS.md](MECHANISMS.md) |
| 2 | Moderate model mismatch does not cause an unacceptable verifier false-accept rate | **NOT MET at severe; borderline at moderate** | FA 0.063 (moderate), **0.228 (severe)** |
| 3 | Strong offline exact recovery maintains parity on covered events | **MET** | 0.994 vs 0.994, 0/0 discordant, p = 1.0 |
| 4 | Online synthesis retains an advantage under limited structural coverage | **MET** | +0.156 [+0.143, +0.170] vs offline_atomic |
| 5 | CPU architecture and benchmark APIs frozen | **MET** | `adapter.py` frozen; no core API change this iteration except the ablation hooks |
| 6 | All tests and statistical scripts reproduce from a clean checkout | **MET** | 68 tests; 12 scripts |

Criterion 2 is the reason this is CONDITIONAL rather than GO.

---

## B1 resolved: three mechanisms reframed, none forced significant

All three nulls were shown to be **internally active but outcome-neutral**, with
an identified mechanism for each — not noise, and not a broken ablation.

* **Event composition.** The reduced goal genuinely differs in **163/216**
  compound episodes, yet plans, selections, outcomes, rejections and search
  expansions are identical in **0/216**. Cause: operator preconditions already
  encode the composition (`Realign` requires `safe_clearance ∧ ¬obstacle_present
  ∧ object_grasped ∧ object_stable`), so a single-predicate goal cannot be
  reached without resolving the others. → **representation mechanism.**
* **Restore gate.** **0 rejections in 706 validations**, including at *severe*
  mismatch. `Realign` already establishes the contract before the transition is
  attempted. → **safety invariant**, retained but not claimed as gain.
* **State-dependent scoring.** Selection is genuinely contested (>1 surviving
  candidate in **79.2%** of decisions; selection changed in 25/432 episodes) yet
  **0** outcome differences — every rollout-verified candidate is
  outcome-equivalent. → **plan-quality preference.**

Per instruction, the benchmark was **not** redesigned to force significance.
Two of these (composition, scoring) can be removed with no measured loss.

## B2 resolved: verification degrades, and neither mitigation works

17 280 episodes, 4 mismatch levels × 4 verifier variants, paired seeds.

**False-accept rate (accepted by verifier, failed physically):**

| verifier | none | mild | moderate | severe |
|---|---|---|---|---|
| none | 0.034 | 0.067 | 0.094 | 0.253 |
| **nominal** | **0.000** | **0.028** | **0.063** | **0.228** |
| conservative | 0.000 | 0.027 | 0.054 | 0.214 |
| receding | 0.000 | 0.028 | 0.064 | 0.226 |

**False-reject rate:** nominal 0.080 flat; **conservative 0.667 / 0.623 / 0.507 / 0.304**.

Answers to the robustness questions:

1. **Where does nominal verification stop being reliable?** Precision is 1.000 at
   zero mismatch and degrades monotonically: 0.972 (mild), 0.937 (moderate),
   **0.772 (severe)**. It is dependable through *mild*, marginal at *moderate*,
   and **unreliable at severe** — nearly one in four accepted plans fails.
2. **Do conservative margins reduce false accepts without excessive false
   rejects?** **No.** FA falls only 0.063→0.054 (moderate) while FR explodes to
   0.507, and net safe delivery gets *worse* (0.887 vs 0.918). The margin design
   is not selective.
3. **Does receding-horizon reverification recover performance?** **Essentially
   no.** 0.917 vs 0.918 (moderate), 0.758 vs 0.756 (severe), despite ~2.9
   replans/episode. Within noise.
4. **Which mismatch source is most damaging?** **NOT ISOLATED.** Levels vary all
   ten dimensions jointly. A per-dimension ablation is still owed.
5. **Does continuation-based restoration remain useful under model error?** The
   *gate* does not fire even at severe. The *handoff target* does matter
   (−0.070 SD, handoff error 0.132 vs 0.074) but that was measured at zero
   mismatch; its mismatch interaction is not yet isolated.

Verification is still worth keeping — nominal beats no-verifier at every level
(0.979/0.951/0.918/0.756 vs 0.966/0.933/0.906/0.747) — but it must be described
as *reducing* false accepts, never as providing a guarantee.

---

## Conditions attached to the GO

1. **Claim only two causal mechanisms** — runtime operator synthesis and
   sequential rollout verification — plus continuation-carrying restoration for
   handoff quality. Composition, the restore gate, and state-dependent scoring
   are representation / invariant / quality mechanisms.
2. **State the L1/L2/L3 separation explicitly** in the paper
   ([PROPOSITIONS.md](PROPOSITIONS.md)); no claim may collapse abstract soundness
   into physical success.
3. **Report the false-accept curve** wherever verification is claimed. Do not
   describe rollout verification as a guarantee.
4. **Do not claim conservative margins or receding-horizon reverification as
   contributions.** Both are measured and both fail here. Either redesign them
   (a selective, per-dimension margin rather than a flat clearance band) or drop
   them from the method.
5. **Owe one more CPU experiment:** per-dimension mismatch attribution
   (question 4). It is cheap and directly informs which OmniGibson noise sources
   will matter.

## If integration proceeds

Order is unchanged from the previous gate: implement `ReKepOmniGibsonAdapter`
against the frozen interface; **do not rewrite ReKep's trajectory optimizer**
(`simulate_candidate` must call ReKep's own subgoal/path solvers at reduced
budget); reproduce the stock demo; verify parity on undisturbed episodes; then
upright transport → pen insertion with relocation → placement with slip and
compound interruption. Parallelize as 8 persistent simulator workers, one per
3090.

Expect OmniGibson mismatch to sit between *moderate* and *severe*. On this
evidence that implies a verifier false-accept rate in the **0.06–0.23** range —
plan the experiments so that this is measured, not assumed away.

## Scope discipline (unchanged)

**Verified online structural repair of an actively executing ReKep constraint
program.** Not arbitrary open-set recovery, not world-model reconstruction, not
universal superiority over precompiled recovery — the strong precompiled
baseline is *exactly equal* on covered combinations.
