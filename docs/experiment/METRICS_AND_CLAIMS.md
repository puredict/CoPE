Status: Draft v0.1
Pending canary-run validation

# Metrics and Claim Boundaries

This document defines which metrics may be reported, what claims they support, and what claims they do not support. It must be read together with `EXPERIMENT_PROTOCOL.md`.

No metric in this file is a result. Do not fill values from visual impression alone.

## 1. Measurement Status Legend

- Current code can measure: fields already present in existing JSON or summaries, subject to validation of semantics.
- Computable from current logs: metric can be derived if strict pair keys are present.
- Needs new detector: requires contact, grasp, object pose, stage, observer, or event instrumentation not currently reliable in the audited scripts.
- Proxy only: may be useful for debugging but does not directly measure the intended construct.
- Do not fill subjectively: must not be entered by looking at videos without a predefined annotation protocol and, where needed, detector support.

## 2. Primary Metrics

| Metric | Definition | Measurement status | Supports | Does not support |
| --- | --- | --- | --- | --- |
| Disturbed success rate | Fraction of disturbed episodes that end in verified task success. Report by mode, checkpoint, suite, task, and disturbance grid. | Current code records `success`, but current scripts often use `done` as success, so wrapper semantics must be validated before formal claims. | Whether a condition succeeds under the tested disturbance matrix. | Why it succeeds, whether recovery happened, or whether the model understood the disturbance. |
| Clean-to-disturbed degradation | Paired clean success minus disturbed success for the same pair key. | Computable from current clean/disturbed logs only when pairs are strict and clean success semantics are validated. | Whether displacement reduces performance for matched pairs. | Degradation claims without reproduced clean baseline or without strict pairing. |
| Recovery gain over reactive | Paired success difference between a recovery mode and `reactive_disturbed` under the same disturbed pair key and budget. | Partly computable from current mode summaries if pair keys are complete; current baseline scripts need stricter initial-state and seed recording for formal paired tests. | Whether a recovery intervention improves success over reactive continuation in the same matrix. | That the intervention performs local recovery unless reset, oracle information, and extra budget are controlled. |
| Paired outcome transitions | Counts of clean/disturbed or reactive/recovery transitions: success-to-success, success-to-failure, failure-to-success, failure-to-failure. | Computable from current logs only after pair keys are normalized across modes and missing pairs are handled. | Direction of changes and McNemar-style paired analysis. | Any paired statistical conclusion when pairs are incomplete or mismatched. |

## 3. Auxiliary Metrics

| Metric | Definition | Measurement status | Notes |
| --- | --- | --- | --- |
| Post-disturbance recovery steps | Policy steps from disturbance event to first verified successful recovery state or task success. | Needs new detector unless task success is used as a coarse endpoint. | If measured only as disturbance-to-task-success, label it as task-completion latency, not recovery latency. |
| Object rediscovery steps | Steps from disturbance to first verified observation or localization of the moved object. | Needs new observer/detector. | Cannot be inferred from a prompt string or action change. |
| Re-contact steps | Steps from disturbance to first contact between gripper and target object. | Needs contact detector or simulator contact log. | Video-only annotation requires protocol and should be secondary. |
| Re-grasp steps | Steps from disturbance to first stable grasp after disturbance. | Needs grasp detector using contact, gripper state, object motion, or task-specific logic. | Do not mark by visual impression alone in formal tables. |
| Total action steps | Number of policy decisions executed. | Current code records `num_policy_steps` and action traces. | Must be separated from warmup and reset/rollback refresh steps. |
| Total environment steps | Warmup plus policy actions plus reset/rollback refresh/no-op steps. | Needs more explicit logging in current code. | Required for fair cost reporting. |
| Invalid action count | Count of malformed, NaN/Inf, out-of-range, collision-inducing, or no-progress actions under a predefined rule. | Needs validation and detectors; current action traces can support some numeric checks. | Action vector difference alone is not invalidity. |
| Timeout rate | Fraction of episodes ending because step budget expired. | Needs explicit termination reason. Current code can infer some timeouts when `success=false` and steps hit budget, but this is a proxy. | Must be separated from stop and infrastructure error. |
| Stop rate | Fraction of episodes intentionally stopped by verifier/controller. | Current `second_necessity_intervention.py` records `stopped_by_verifier`; other scripts need explicit termination reason. | Stop is not task recovery. |
| Recovery attempt count | Number of recovery decisions, prompt changes, stage backtracks, resets, rollbacks, or replans per episode. | Partly current via `recovery` or `recovery_state`; needs standardized event log. | Script-created recovery fields are not proof that the model chose the correct recovery. |

## 4. Current Code Measurement Inventory

Current audited scripts can directly record or summarize:

- `task_suite`, `task_id`, `trial_id` in `libero_disturbance_eval.py`.
- `mode` or `condition`.
- `target_joint`.
- `success`, subject to validating `done` semantics.
- `final_reward`.
- `num_policy_steps`.
- `disturbance` record with joint, before qpos, after qpos, and `delta_xy`.
- `video_path`.
- `actions` with policy step, raw action, environment action, reward, and `done`.
- `success_by_mode` in baseline scripts.
- `clean_success_rate` and `disturbed_success_rate` in `libero_disturbance_eval.py`.
- `stopped_by_verifier` in `second_necessity_intervention.py`.
- Script-defined `recovery` or `recovery_state` fields in baseline scripts.

Current code can support only after additional audit:

- Formal success rate, because `done` must be confirmed as task success in the active LIBERO wrapper.
- Timeout rate, if termination reason is added or inferred consistently.
- Paired degradation, if pair keys are complete and missing pairs are reported.
- Budget-normalized comparison, if warmup, reset, rollback, and refresh costs are logged.

Current code does not yet reliably measure:

- Semantic task phase at disturbance.
- Whether the system correctly identified the failed stage.
- Whether the moved object was rediscovered.
- Whether the gripper re-contacted or re-grasped the object.
- Whether an action was semantically valid.
- Whether a recovery prompt caused a structured state update rather than a language-only behavior change.
- Stale observation events unless fresh-observation instrumentation is added.

## 5. Proxy Metrics

The following may be reported only as proxies:

- Action-vector distance after image or prompt changes. Proxy for policy sensitivity, not action correctness.
- `num_policy_steps`. Proxy for efficiency, not recovery quality.
- `delta_xy` and qpos mutation. Proxy for disturbance application, not for perceived displacement.
- Prompt string changes. Proxy for intervention type, not for internal state representation.
- Heuristic target-joint selection. Proxy for target-object choice, not evidence of correct semantic object selection.
- `has_selective_recovery_state` or similar preset booleans. Proxy for a designed state schema, not measured model capability.
- Video-derived labels without a predefined annotation protocol. Qualitative evidence only.

## 6. Metrics That Must Not Be Filled Subjectively

Do not fill the following from unaudited visual inspection:

- Formal task success if the environment success signal is available or should be available.
- Correct affected-object identification.
- Correct failed-stage identification.
- Object rediscovery step.
- Re-contact step.
- Re-grasp step.
- Invalid action count.
- Recovery attempt correctness.
- Whether stale observation occurred.
- Whether a prompt improvement proves structured recovery.

Videos may be used for failure taxonomy annotation only under a written annotation protocol that defines evidence, uncertainty, multi-label rules, and exclusion rules.

## 7. Claim Boundary Matrix

| Observation | Supported claim | Unsupported claim |
| --- | --- | --- |
| `reactive_disturbed` has lower success than paired clean. | The tested disturbance matrix degraded performance for those paired episodes. | All object displacement degrades OpenVLA, or degradation holds without pairing. |
| Recovery prompt has higher success than `reactive_disturbed`. | The prompt intervention improved success under the tested budget and information conditions. | A complete symbolic recovery architecture is proven effective. |
| `verifier_stop` stops after disturbance. | The system can execute a safety-stop policy under the scripted condition. | The system recovered, or all verifier-based systems are ineffective. |
| `full_reset_replan` succeeds after reset. | Restarting from a clean initial state can solve the task under the tested checkpoint. | The method recovered in the disturbed world or performed local replanning. |
| `oracle_rollback` succeeds. | Undoing the disturbance can provide an idealized upper-bound diagnostic. | The real system can recover from object displacement. |
| Scripted booleans show `can_identify_affected_object=true`. | The schema encodes that property by construction. | The model or system measured the property in the environment. |
| Action vector changes after disturbance. | The policy output is sensitive to input/prompt changes. | The action is correct or task recovery is underway. |
| A dashboard episode succeeds after manual intervention. | A human-guided debug trajectory succeeded. | The autonomous method succeeded. |

## 8. Mandatory Claim Boundaries

1. `oracle_rollback` is only an ideal upper bound. It cannot prove realistic recovery capability.

2. `full_reset_replan` removes the post-disturbance world. It is not equivalent to local replanning in the changed scene.

3. `verifier_stop` demonstrates safety stopping, not recovery.

4. Preset boolean fields are not experimental measurements.

5. Prompt-rewriting improvements cannot by themselves prove a complete symbolic recovery architecture.

6. Only 1 to 3 runs cannot support stable generalization claims.

7. Episodes with manual button intervention must not be mixed into autonomous success rates.

8. Without an observer, state machine, or validated detector, the system cannot claim it correctly identified the failed stage.

9. Before reproducing the clean baseline, do not claim that disturbance caused performance degradation.

10. Without strict pairing, do not use paired statistical conclusions.

## 9. Reporting Template

Every result table should include:

- Condition or mode.
- Checkpoint.
- Suite and task set.
- Number of strict pairs.
- Number of missing pairs.
- Successes and success rate.
- Confidence interval.
- Stop count.
- Timeout count.
- Error count.
- Mean and median policy steps.
- Mean and median total environment steps.
- Whether reset/rollback/oracle information was allowed.
- Whether manual episodes were excluded.

Every claim paragraph should name the scope:

`For [checkpoint] on [suite/tasks] with [disturbance grid] under [budget rule], [metric] changed from [baseline] to [comparison].`

If any bracketed field is unknown, the claim is not ready for paper use.
