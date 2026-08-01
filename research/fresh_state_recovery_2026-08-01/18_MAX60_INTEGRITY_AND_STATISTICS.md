# Max-60 fresh-state integrity and statistical audit

Date: 2026-08-01 (Asia/Shanghai)

## Bottom line

The states 15–24 run is consistent with an actual paired, deterministic MuJoCo
mechanism experiment; it is not a synthetic table or a learned-policy result.
All 30 assigned cells completed after the preregistration commit. The evidence
supports retaining local staging as an **oracle efficiency ablation**. It does
not establish safety and cannot substitute for CoPE versus a real FSR-PC
baseline.

## Provenance and anti-fabrication checks

- Preregistration commit: `7e7b6ce9cc87e6c880886bcbbd731177544c3099`,
  committed at 2026-08-01 16:33:13 +08:00.
- Raw CSV write interval: 2026-08-01 16:35:52–16:36:51 +08:00.
- Assigned cells present: 30/30, exactly one row for each state × arm.
- Fixed settings: `pre_release`, oracle execution and operation selection,
  learned policy disabled, and `oracle_max_move_steps=60` in 30/30 rows.
- Within every state, all three arms share one action-prefix hash, one pre-patch
  simulator-state hash, and one event step.
- Across the ten states, there are ten distinct action-prefix hashes and ten
  distinct pre-patch simulator-state hashes.
- The patch preserves simulator state in 30/30 rows, while every state has three
  distinct post-event action hashes, as expected for the three interventions.
- All 30 CSV files have distinct SHA-256 digests. Each CSV's prefix and
  post-event hashes also appear in its retained stdout/stderr log.
- The launching shell exited successfully after all 30 child processes
  completed. CUDA was explicitly hidden; this experiment used the simulator and
  oracle controller, not a GPU policy checkpoint.

These checks do not prove that the simulator is a faithful model of the real
world. They do rule out several common false-experiment failure modes: copied
rows, missing assigned cells, post-hoc state substitution, unequal prefixes,
learned-policy relabeling, and summary-only numbers without raw traces.

## Post-hoc uncertainty analysis

This section is descriptive and was not part of the frozen decision rule.

- Updated-goal success was 10/10 for exact return and 10/10 for local staging.
  A 95% Wilson interval for either marginal rate is approximately 72.2%–100%,
  showing that ten states are still too few for a strong absolute-success claim.
- Local staging was faster in 10/10 paired states. Under a symmetric paired sign
  null, the one-sided exact probability is 1/1024 (0.00098).
- Exact-minus-local savings were `[34, 35, 35, 36, 37, 36, 37, 44, 34, 34]`
  actions: mean 36.2, median 35.5, and a conventional paired t 95% confidence
  interval for the mean of approximately 34.1–38.3 actions.
- The force-impulse proxy favored local staging in 10/10 pairs, but peak force
  favored it in only 4/10. Therefore the run supports lower recovery effort, not
  a general lower-peak-force or safety conclusion.
- Zero preregistered hazard-proxy episodes in 10 trials per recovery arm still
  permits a Wilson 95% upper bound near 27.8%. Moreover the logged force is a
  contact-force proxy, not calibrated collision safety.

## Scientific decision

1. Keep local staging in the paper only as a controlled recovery-efficiency
   ablation against exact return.
2. Do not present the force/contact fields as safety evidence.
3. Do not spend further fresh states tuning this controller. Preserve states
   25–49 for a later locked validation after the learned-policy and real FSR-PC
   paths are ready.
4. Keep the formal FSR-PC comparison at NO-GO until the provider, neutral
   compiler, semantic runner, and validator gates pass.
