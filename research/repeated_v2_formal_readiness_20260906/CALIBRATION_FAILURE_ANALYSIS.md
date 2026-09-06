# Clean OpenVLA calibration failure analysis

This is a post-hoc diagnostic of the frozen 40-cell pilot calibration, not a new eligibility rule, threshold change, retry decision or formal result. The raw cohort passed the frozen offline audit. Every failure remains in the denominator. Evidence statements below come from exact progress/action/observation chains; causal language is explicitly labeled as an inference.

## Integrity facts that rule out infrastructure failure

- The cohort is tasks0/1/4/8 × states0–4 × policy seeds101/131: 40/40 terminal records, no `INFRASTRUCTURE_STOP`, no interruption events and no oracle actions.
- The admitted production identity is `openvla_native` / `openvla-7b-finetuned-libero-10`, checkpoint `d36eaa2a334cd52f4a3a94558cf90d82584743ea772fabf76f9e4372e7076076`, protocol `ac3e0ff37bb1c6eea10b1fa827cc9090408055b1bc622e4aaee87afc769f8959`.
- All 10,180 policy actions passed finite-value, 7-D shape, live environment-range and raw-normalize/binarize/invert-gripper checks. The same conversion produced four successful task1 cells and four successful task4 cells. The evidence therefore does not support action-format failure as the shared cause of task0/8 timeouts.
- All terminal failures are `timeout` at exactly 260 policy controls. There are no manual-intervention, environment-done, adapter, model-loading or simulator exceptions.

## Deterministic replication finding

For every one of the 20 task/state pairs, seeds101 and131 produced exactly identical raw actions, converted actions, per-control RGB hashes, public proprioception and progress predicates. The adapter declares deterministic decoding, the environment starts from the same fixed state, and policy seed does not introduce sampled decoding. The 40 cells are a complete implementation-defined grid, but they contain 20 exact trajectory pairs rather than 40 independent stochastic rollouts. The implemented rate gate is unchanged; because each state is duplicated once, its numerical rate equals the five-state rate. Variance or seed-robustness claims are not supported.

## Per-task result and observed failure path

| Task | Audited successes | Distinct successful states | Observed path | Diagnostic assessment |
| --- | ---: | ---: | --- | --- |
| 0 | 0/10 | 0/5 | States0–3 verified alphabet soup in the basket at policy steps140–187; tomato sauce was never verified in the basket. In states1 and3 it was first lifted only at steps214 and248 and remained lifted at timeout. State4 had no verified lift or placement for either target. | Direct evidence shows late or absent transition to the second object plus one no-progress state. A separate exact-prefix diagnostic succeeds for state1 at264, confirming a four-control cutoff for that cell without changing the frozen protocol. |
| 1 | 4/10 | 2/5 | States0 and4 succeeded at policy steps250 and242, exactly when butter first became verified in the basket. States1 and3 timed out while butter remained lifted; state2 never verified a butter lift. Cream cheese remained placed in all five states. | Direct evidence shows a narrow state-dependent second-stage completion margin. The final-action successes and held-at-timeout failures support a horizon/second-stage completion hypothesis; they do not prove that extra steps would succeed. |
| 4 | 4/10 | 2/5 | States0 and2 succeeded at steps230 and208, exactly when the second mug/plate predicate first became true. State1 briefly satisfied then lost the first placement, lifted the second mug, and ended with neither placement. States3/4 retained the first placement but never verified the second. | Direct evidence shows state sensitivity, first-goal instability in state1, and missing second-placement completion elsewhere. Progress regressions are preserved rather than hidden by ever-achieved flags. |
| 8 | 0/10 | 0/5 | States0–3 verified only the left moka pot on the stove, first at steps180–248; the right pot was never verified lifted or on the stove. State4 had no verified pot lift or placement. The stove-on predicate was true from initialization through every sample. | Direct evidence shows consistent one-pot behavior and one no-progress state. A separate exact-prefix diagnostic succeeds for state2 at378 but states0/1 still fail at520, separating a state2 cutoff from state-dependent failures that extra horizon alone does not resolve. |

## Cross-cutting root-cause assessment

1. **Confirmed: deterministic seed collapse.** Both calibration seeds are exact replays for each state. This is a protocol/interpretation limitation, not an execution crash and not a reason to delete either registered cell.
2. **Confirmed: multi-stage completion is the dominant behavioral bottleneck.** Every success occurs on the first sample where the second goal becomes true. Most failures preserve one completed placement while the other is absent or still held near timeout. Task8 never verifies its other pot in any state.
3. **Confirmed: strong initial-state sensitivity.** Task1 succeeds only in states0/4 and task4 only in states0/2; task0/8 state4 show no verified target progress. Exact initial states, instructions and model bytes are fixed, so this is real within-cohort variation.
4. **Confirmed: predicate regression matters for task4.** State1 ends after losing the first placement, and state0 has two first-placement regressions before eventual success. `ever_achieved` alone would overstate retained progress.
5. **Not supported as the common cause: adapter/source/action corruption.** The production action gate passed, every action validated, seed-paired sensor/progress chains are deterministic, and the identical stack succeeds on some cells.
6. **Confirmed cutoff cells, with state-dependent limits.** Preserved standard520-control traces reproduce task1 states1/2/3 through all260 actions and then succeed at273/323/276. Live post-hoc runs likewise reproduce all260 frozen actions before task0/state1 succeeds at264 and task8/state2 succeeds at378. Task8 states0/1 reproduce all260 actions but still fail at520, so longer horizon is a direct explanation for some cells rather than a universal task-level cause. None of these outcomes is imported into frozen eligibility.
7. **Unresolved: why task8 states0/1 still fail at520, why state4 stalls on tasks0/8, and why specific second-object approaches fail.** The retained RGB frames show valid scenes rather than blank/error renders, but the calibration lacks object-pose telemetry in policy-visible evidence and does not record contact/collision diagnostics. Further causal attribution would require a separately declared diagnostic; privileged simulator state must not be fed to the policy.

`CALIBRATION_FAILURE_CELLS.csv` gives the exact task/state classifications, first-true policy steps, lift signals, regressions, gripper counts and both trace hashes. Lift signals are auxiliary progress predicates: absence of a lift flag is not proof that the robot made no contact or attempt. Visual inspection is used only to reject blank/error rendering, not to score goals.

`HORIZON_FAILURE_DIAGNOSTIC.csv` and `HORIZON_FAILURE_DIAGNOSTIC.md` give the historical comparison and the separately audited live520-control diagnostics. `POSTHOC_LONG_HORIZON_DIAGNOSTICS.csv` retains the live cell outcomes and audit hashes. These records preserve their diagnostic-only labels and supply no calibration closure.

These findings leave task1 and task4 rate-eligible under the unchanged `[0.40, 0.95]` check, and task0/task8 rate-ineligible at0.00. No task is catalog-eligible because independent semantic, safety, event-feasibility and production-runtime gates remain open.
