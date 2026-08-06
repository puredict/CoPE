# Bounded regrasp independent validation result

- Runtime commit: `cafb18fa9c484544c70733b1b1a413adcf474fa9`
- Successes by arm: `{"natural_candidate":10,"natural_legacy":10,"stress_candidate_80mm":10,"stress_single_80mm":0}`
- Gate results: `{"natural_candidate_all_success":true,"natural_candidate_no_losses":true,"natural_shared_trajectory_exact":true,"stress_candidate_all_success":true,"stress_candidate_strictly_better":true,"stress_regrasp_activated_all":true}`
- Failure classes: `{"stress_single_80mm:grasp_not_acquired":10}`
- Stress discordance (candidate wins, single wins): **10, 0**
- Exact two-sided paired sign-test p-value: **0.001953125**
- Provider calls: **0**
- States 25--49 indexed: **no**

This validates a shared prefix-construction substrate; it is not a CoPE method comparison.
