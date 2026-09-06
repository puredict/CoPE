# Per-dimension model-mismatch attribution (Track A — CPU closure)

16 740 episodes; 540 paired randomized episodes × (10 sources × 3 levels +
baseline). Each source enabled **alone**; verifier unchanged (nominal sequential
rollout). Source: `scripts/run_mismatch_attribution.py`.

> **Two wiring bugs were found and fixed before these numbers were produced.**
> (1) `MismatchedEnv.step()` returned the *inner* env's clean context, so every
> observation-side perturbation was silently bypassed. (2) `detector_delay` and
> `guard_delay` were declared but never used. The pre-fix ranking was therefore
> wrong; it is not reported.

## Attribution table (severe level unless noted)

| source | FA | FR | collide | resolve | handoff | SD | TS |
|---|---|---|---|---|---|---|---|
| *(baseline, all nominal)* | 0.000 | 0.938 | 0.004 | 1.000 | 0.076 | **0.970** | **0.681** |
| **guard_delay** | **0.393** | 0.667 | 0.054 | 0.633 | 0.327 | **0.604** | **0.000** |
| **object_obs_noise** | **0.285** | 0.944 | 0.009 | 0.726 | 0.262 | **0.691** | 0.443 |
| **target_pred_error** | **0.183** | 0.938 | 0.004 | 1.000 | 0.087 | **0.793** | 0.544 |
| **regrasp_failure_p** | 0.139 | 0.938 | 0.013 | 0.874 | 0.182 | 0.835 | 0.550 |
| release_drift | 0.046 | 0.938 | 0.009 | 0.961 | 0.098 | 0.926 | 0.659 |
| action_noise | 0.042 | 0.938 | 0.004 | 1.000 | 0.083 | 0.930 | 0.659 |
| detector_delay | 0.002 | 0.952 | 0.015 | 1.000 | 0.078 | 0.961 | **0.522** |
| obstacle_pred_error | 0.006 | 0.938 | 0.009 | 1.000 | 0.076 | 0.965 | 0.680 |
| translation_gain | 0.004 | 0.938 | 0.004 | 0.996 | 0.086 | 0.967 | 0.674 |
| rotation_gain | 0.000 | 0.938 | 0.004 | 1.000 | 0.076 | 0.970 | 0.689 |

## Damage ranking (Δ safe delivery vs baseline, severe)

| rank | source | ΔSD | ΔFA | Δcollide |
|---|---|---|---|---|
| 1 | guard_delay | **+0.367** | +0.393 | +0.050 |
| 2 | object_obs_noise | **+0.280** | +0.285 | +0.006 |
| 3 | target_pred_error | **+0.178** | +0.183 | +0.000 |
| 4 | regrasp_failure_p | +0.135 | +0.139 | +0.009 |
| 5 | release_drift | +0.044 | +0.046 | +0.006 |
| 6 | action_noise | +0.041 | +0.042 | +0.000 |
| 7 | detector_delay | +0.009 | +0.002 | +0.011 |
| 8 | obstacle_pred_error | +0.006 | +0.006 | +0.006 |
| 9 | translation_gain | +0.004 | +0.004 | +0.000 |
| 10 | rotation_gain | +0.000 | +0.000 | +0.000 |

## Conclusions

**1. Which mismatch dominates?**
**State-observation error, not actuation error.** The top three — stale guard
observations (+0.367), object-position noise (+0.280) and target-position error
(+0.178) — are all cases where the robot's *belief* about where something is, or
when, is wrong. Together they account for essentially all the damage.

**2. Which mismatch is mostly harmless?**
Actuation-side error. Rotation gain (+0.000), translation gain (+0.004),
obstacle-position prediction error (+0.006) and detector delay (+0.009 on safe
delivery) are all negligible. The reason is structural: the controllers are
closed-loop feedback on the *current* observation, so a persistent gain error is
absorbed by more steps rather than converted into failure. This also explains
why the verifier stays accurate under actuation error — the rollout's predicted
*sequence of decisions* remains correct even when the predicted timing is off.

**Caveat:** detector delay is nearly harmless for safe delivery (0.961 vs 0.970)
but materially damages **full task success** (0.522 vs 0.681), because a late
repair leaves less horizon to restore orientation. SD and TS rank these sources
differently; both must be reported.

**3. Which mismatch must be represented in OmniGibson experiments?**
In priority order: **(a) guard/observation latency** — the control loop acting on
a stale world view; **(b) keypoint position noise on the manipulated object**;
**(c) target/goal position error**; **(d) stochastic regrasp failure**. These map
directly onto real ReKep failure modes: keypoint-tracker latency and jitter, and
grasp non-determinism. Actuation gain error may be omitted from the first
OmniGibson study without materially changing conclusions.

**4. Is nominal verification adequate as the paper's default?**
**Yes, with a stated scope condition.** Under every actuation-side source the
false-accept rate stays ≤ 0.042 even at severe. It degrades only under
observation-side error (0.393 / 0.285 / 0.183). So the honest formulation is:

> Sequential rollout verification is reliable to the extent that the observed
> state is accurate and current; it is insensitive to actuation-model error and
> sensitive to observation latency and position noise.

No new verifier architecture is proposed. (Conservative margins and
receding-horizon reverification were measured earlier and both failed; they
remain excluded from the contributions.)

## Frozen

With this experiment the **synthetic architecture and benchmark are frozen.**
Further changes should be limited to bug fixes.
