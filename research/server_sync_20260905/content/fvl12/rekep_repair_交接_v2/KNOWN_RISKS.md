# Risks that could block ReKep–OmniGibson integration

Ordered by (probability × blast radius). Each has a detection signal and a
fallback. Nothing here has been tested on GPU.

## R1 — Installation / version hell (HIGH probability, HIGH impact)

Isaac Sim + OmniGibson + ReKep + torch is a brittle stack: Isaac Sim ships its
own Python, OmniGibson pins Isaac Sim versions, ReKep pins OmniGibson, and torch
must match CUDA. A single mismatch produces import errors deep in Omniverse.

*Signal:* `check_gpu_environment.py` FAILs, or `omni` imports but crashes on
scene creation.
*Fallback:* use ReKep's own documented OmniGibson revision rather than latest;
install torch first from the cu121 index; never let pip resolve torch.
*Cost if it bites:* days, not hours. **Budget for this explicitly.**

## R2 — Asset download and licensing (HIGH probability, MEDIUM impact)

BEHAVIOR/OmniGibson assets are tens of GB and gated behind a licence prompt;
partial downloads fail late and confusingly.

*Signal:* scene creation raises missing-asset errors.
*Fallback:* download assets in a separate step, verify checksums, cache on fast
local disk shared read-only by all 8 workers.

## R3 — Physics non-determinism (MEDIUM probability, HIGH impact on claims)

ReKep's own README warns OmniGibson can produce different results at the same
seed. This directly threatens the paired-seed protocol that the entire CPU
statistical design rests on.

*Signal:* Step 7 of Milestone 1 produces divergent traces.
*Fallback:* define the tolerance in advance — require the **stage sequence** to
match exactly and treat continuous quantities with a tolerance; increase seeds
per condition; report paired differences rather than absolute rates.
*This is the risk most likely to change the paper's statistics section.*

## R4 — Keypoint noise breaks predicate stability (MEDIUM, HIGH)

Our CPU attribution ranks **observation error as the dominant damage source**
(object-position noise ΔSD +0.280; stale observations +0.367). Real ReKep
keypoint tracking is exactly this kind of noisy, latent signal. Flickering
predicates would cause repeated spurious repairs.

*Signal:* `active_predicates()` toggles between adjacent steps.
*Fallback:* hysteresis / debouncing on predicate transitions (already partly
handled by the latch); ground-truth predicates for the first study, noise added
deliberately afterwards.
*Mitigation is designed-in, but untested against real keypoints.*

## R5 — `simulate_candidate` too slow (MEDIUM, MEDIUM)

Verification calls ReKep's subgoal/path solvers once per operator per candidate.
With ~3 candidates × ~6 operators that is ~18 solver calls per repair. If each
takes seconds, verification dominates episode time.

*Signal:* repair latency ≫ nominal step time.
*Fallback:* reduce `sim_budget_steps`; cache subgoal solutions across candidates
sharing a prefix; verify only the top-k scored candidates.
*Do not* respond by removing verification — it is a principal claim.

## R6 — Adapter keypoint-index wiring is scene-specific (HIGH, LOW)

`ReKepAdapterConfig` indices are placeholders and certainly wrong for any real
scene.

*Signal:* nonsensical clearances or goals in the first trace.
*Fallback:* derive indices from ReKep's per-task metadata rather than hardcoding;
assert plausible ranges at adapter construction.

## R7 — ReKep's stage semantics don't map cleanly onto `StageSpec` (MEDIUM, HIGH)

Our IR assumes a stage carries subgoal + path constraints and a guard. If
ReKep's actual structure diverges (e.g. grasp/release encoded outside the stage
list), the parity check in Milestone 1 Step 4 will fail.

*Signal:* wrapped-mode stage sequence differs from nominal.
*Fallback:* keep ReKep's stage advance logic authoritative and let `TaskProgram`
*mirror* it, only taking control during repair.

## R8 — Headless rendering / video capture on a shared box (MEDIUM, LOW)

8 concurrent Omniverse instances contend for GPU memory and the renderer;
video capture multiplies memory use.

*Signal:* OOM or renderer init failures beyond ~4 workers.
*Fallback:* headless (`gm.HEADLESS=True`), video only for a small subset of
seeds, per-worker `OMNI_KIT_CACHE_DIR` (already in the launcher).

## R9 — Scope creep back into the manipulation stack (LOW probability, FATAL to the claim)

The temptation, when ReKep's solver struggles, is to "improve" it. That destroys
the isolation the paper depends on.

*Signal:* any diff inside ReKep's `subgoal_solver`, `path_solver`, `ik_solver`,
or `constraint_generation`.
*Fallback:* treat those files as read-only; record any unavoidable change as a
named limitation.

## Summary

The two risks most likely to change the *paper* rather than just the schedule
are **R3 (non-determinism → statistics)** and **R4 (keypoint noise → predicate
stability)**. Both should be probed during Milestone 1 rather than discovered
during the sweep.

---

## Priority statement (added for the handoff)

**R3 (physics nondeterminism) and R4 (keypoint noise) are the two risks most
likely to affect the paper rather than only the schedule.**

* **R3** threatens the paired-seed protocol that the entire CPU statistics
  section rests on. If OmniGibson diverges at a fixed seed, paired McNemar /
  bootstrap comparisons weaken. Agree a tolerance policy *before* the runs:
  require the **stage sequence** to match exactly and treat continuous
  quantities with a stated tolerance.
* **R4** is predicted directly by our own measurement: observation-side error is
  the dominant damage source (stale observations ΔSD +0.367, object-position
  noise +0.280), and real ReKep keypoint tracking is exactly that kind of noisy,
  latent signal. Expect predicate flicker to be the first real problem.

All other risks (R1, R2, R5–R9) cost time or require mitigation but do not
change what may be claimed.
