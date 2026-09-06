# Clean-policy horizon failure diagnostic

This diagnostic compares the frozen 260-policy-control cohort with already preserved historical OpenVLA traces. It does not rescore the frozen cohort, change its horizon, authorize a retry, or provide catalog evidence. Historical runs keep their original protocol labels and seed IDs.

## Exact-path comparison

The comparison covers the same checkpoint, task BDDL, initial-state bytes, agent-view RGB preprocessing, language instruction and action conversion. For every compared cell, the initial frame hash and every available raw/environment action pair are byte-for-byte equal across the two runs. The current seeds101/131 are deterministic labels rather than sampled decoding seeds, so a different historical seed label does not alter the action path.

| Task | Historical source | Exact cells | Exact compared controls | Result |
| --- | --- | ---: | ---: | --- |
| 0 | 220-control v1 | 5/5 | 1,100 | The current run reproduces all 220 historical controls, then continues to260 without success. No longer-horizon success record exists in the preserved source. |
| 1 | 520-control v2 | 5/5 | 1,272 | States0/4 succeed at the same controls250/242. Current timeouts in states1/2/3 follow the same first260 actions as historical runs that succeed at273/323/276. |
| 4 | 220-control v1 | 5/5 | 1,088 | State2 succeeds at208 in both runs. State0 reproduces the old220-control timeout and succeeds at230 in the current run. Other states reproduce the old prefix but still time out at260. |
| 8 | 220-control v1 | 5/5 | 1,100 | The current run reproduces all220 historical controls, then continues to260 without success. No longer-horizon success record exists in the preserved source. |

The task1 comparison is a direct same-path cutoff diagnosis. Nothing in its first260 controls distinguishes the current run from the preserved successful run. The three current failures occur because the frozen runner stops 13, 63 and16 controls before the exact same deterministic trajectories reach LIBERO success. This establishes the immediate termination cause for those three task1 cells. It does not justify changing the preregistered 260-control eligibility rule.

Task4 state0 supplies a second cutoff witness in the opposite direction: the older 220-control run times out, while the current identical path reaches success ten controls later. Together these cells explain why raising220 to260 improved task4 and task1 without altering the adapter.

Tasks0/8 remain behavior failures under the frozen horizon. Their exact historical/current prefixes and valid actions rule out a newly introduced adapter, preprocessing, instruction or action-conversion regression through control220. Current traces then show task0 usually completing only the first placement and task8 usually completing only the left-pot placement.

## Predeclared live 520-control diagnostics

Four post-hoc diagnostic cells were run from a clean detached worktree at source commit `c0308c1fc13036ef34983dd07397744f659cb417`. Their protocols were written before launch, use diagnostic seeds excluded from calibration/formal seeds, and explicitly forbid oracle actions, provider calls, manual intervention, threshold changes and rewriting the frozen results. Every cell passed the real OpenVLA smoke gate and every inferred action passed the live 7-D action contract.

| Task | State | Frozen outcome at260 | Diagnostic outcome at520 | Exact first260 | Finding |
| ---: | ---: | --- | --- | --- | --- |
| 0 | 1 | timeout | success at264 | yes | Four additional controls directly resolve this cell. |
| 8 | 0 | timeout | timeout at520 | yes | The260 cutoff alone is insufficient for this state. |
| 8 | 1 | timeout | timeout at520 | yes | The260 cutoff alone is insufficient for this state. |
| 8 | 2 | timeout | success at378 | yes | The same deterministic path succeeds with118 additional controls. |

The task8 result separates two effects. State2 proves that the learned policy can complete the authentic two-pot task and that the frozen cutoff causes this particular failure. States0/1 remain failures even after doubling the horizon, showing strong initial-state sensitivity and a second-object behavior failure that cannot be explained by adapter loading or the260 cutoff alone. The task8 diagnostic cells were selected independently from frozen progress records before each launch: state2 had the earliest first-stage completion and state0 the second earliest; state1 was already paired with the task0 diagnostic. This evidence is diagnostic only and does not alter task8's frozen0/10 calibration rate.

## Evidence boundary

- Current audited cohort: `clean_calibration_audit_01/CALIBRATION_AUDIT.txt`, SHA256 `f3b5ec7c36a334f52ad25e1d5ab7f419577f0da5f244f9ca719a7e0ce622e3dd`.
- Historical 520-control summary: `research/server_sync_20260905/content/fvl12/cope-integration-outputs-20260724/openvla_libero10_calibration_v2/calibration_summary_v2.json`, SHA256 `54393cb6bb629d1eaab20bdeadcced62733e0e5dcdf51c7eafa697ddbf9061f6`.
- Per-cell source paths, seeds, exact prefix lengths and both trace hashes: `HORIZON_FAILURE_DIAGNOSTIC.csv`, SHA256 `d6f5f5660c2226225008196970e27d4ea5c919737567298e6e37494878db89e2`.
- Live post-hoc outcomes, exact-prefix booleans, action-validation results and audit hashes: `POSTHOC_LONG_HORIZON_DIAGNOSTICS.csv`, SHA256 `c14aba3d4ad04a568887ad2edce2e17bfdbcc04b285af30dacca02a934b7cbd1`.
- Live audit artifacts: `horizon_diagnostic_520_task0_task8_state1_01/AUDIT.txt` SHA256 `5269e20a744c8fc9de420cec0d2e918503f5313db2c7563ebc64fe1c580665df`, `horizon_diagnostic_520_task8_state2_01/AUDIT.txt` SHA256 `f1ec241c5c6ed2520e8aa7973d252bcf7072c4d34d4116f582f642d8fd830855`, and `horizon_diagnostic_520_task8_state0_01/AUDIT.txt` SHA256 `e64d45acd5d291d5671c1c59e108405b68d34c9ebdac2db28426cea109a3ef31`.
- The historical report explicitly labels its run as feasibility screening and records the standard520-control protocol. Those outcomes are never relabeled as repeated-v2 calibration.

The engineering conclusion is specific: the production OpenVLA path is working, and a deterministic260-control cutoff causes three task1 failures plus the diagnosed task0/state1 and task8/state2 failures. Task8 states0/1 show that cutoff extension is not a universal repair. The scientific conclusion stays unchanged: task1's frozen rate is4/10, task4's is4/10, task0/task8 are0/10, and no catalog or formal-run gate is satisfied by this diagnostic.
