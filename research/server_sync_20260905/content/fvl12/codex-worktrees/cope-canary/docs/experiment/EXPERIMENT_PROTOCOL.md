Status: Draft v0.1
Pending canary-run validation

# Experiment Protocol: LIBERO / OpenVLA Disturbance Recovery

This document defines the formal experiment protocol for object-displacement recovery in LIBERO with OpenVLA-family policies. It is a protocol, not a result report. It must not be used to imply that any experiment has already succeeded.

## 0. Scope and Rule Levels

Hard Rule means the condition is required before a run can be included in a formal paper metric.

Recommended Target means the condition is the preferred design goal, but deviations may be used for debugging or pilot analysis if explicitly labeled.

This protocol covers headless scripted rollouts only. Dashboard, manual button, pause, step, or hand-disturbed episodes are debugging artifacts unless a later protocol creates a separate human-in-the-loop study.

## 1. Research Questions

RQ1. Does an object displacement during execution reduce the success rate of OpenVLA policies on LIBERO tasks relative to clean paired episodes?

RQ2. How does degradation vary with disturbance timing, displacement magnitude, displacement direction, target object, and task phase?

RQ3. Do recovery prompts or stage-backtracking prompts improve disturbed performance over a purely reactive disturbed policy under matched budgets?

RQ4. Are observed improvements explained by extra information, reset/rollback privileges, or extra action budget rather than true local recovery in the current disturbed world?

RQ5. Do base and LIBERO-finetuned checkpoints differ in robustness and recovery behavior under the same paired disturbance matrix?

## 2. Hypotheses and Endpoints

### Primary Hypotheses

H1. Object displacement reduces success rate relative to clean paired episodes for the same task, initial state, and seed.

H2. The degradation increases with larger displacement magnitudes and with disturbances applied during object-contact or transport phases.

H3. A current-world recovery prompt or stage-backtracking prompt improves disturbed success over `reactive_disturbed` when the action budget and information budget are matched.

### Secondary Hypotheses

H4. `verifier_stop` increases safe stopping behavior but does not by itself demonstrate task recovery.

H5. `full_reset_replan` and `oracle_rollback` can improve success but should be interpreted as diagnostic baselines, not current-world recovery methods.

H6. The LIBERO-finetuned checkpoint has higher clean success and may have different disturbance degradation than the base checkpoint, but this must be tested with paired runs.

### Endpoints

Primary endpoint: paired disturbed success rate and paired clean-to-disturbed degradation for formal conditions.

Secondary endpoints: recovery gain over `reactive_disturbed`, paired outcome transitions, timeout rate, stop rate, and total policy-action cost.

Exploratory endpoints: recovery latency, relocalization latency, re-contact latency, re-grasp latency, invalid action count, recovery attempt count, and failure taxonomy frequencies. These require detectors or annotation rules before they can become primary endpoints.

## 3. Model Checkpoints

Hard Rule: Every formal run must record checkpoint path, checkpoint name, model family, action normalization key, model commit or local manifest if available, and whether the checkpoint is base or LIBERO-finetuned.

Minimum checkpoint set:

- `openvla-7b` or the locally available base OpenVLA checkpoint, labeled `base`.
- `openvla-7b-finetuned-libero-spatial` or the locally available LIBERO-Spatial checkpoint, labeled `libero_spatial_finetuned`.

Recommended Target: Include both checkpoints in the same task and disturbance matrix. Do not compare checkpoints unless suite, task, initial state, seed, action budget, warmup rule, and success semantics match.

## 4. LIBERO Suite and Task Selection

Primary suite: `libero_spatial`, because the current disturbance code and checkpoint defaults focus on spatial object rearrangement.

Recommended extension suites:

- `libero_object` for object identity and selection stress.
- `libero_goal` for goal-region ambiguity.
- `libero_10` only for smoke or continuity checks unless a formal suite mapping is specified.

Hard Rule: Formal tables must list suite name, task id, task description, initial state id, and target object or joint used for disturbance.

Task selection tiers:

- Smoke: one known task, one initial state, one seed. This only verifies pipeline integrity.
- Pilot: at least 3 tasks, at least 3 initial states per task, at least 1 seed. This is for debugging and variance estimation.
- Formal minimum: at least 5 tasks, at least 5 initial states per task, and at least 3 seeds when computationally feasible.
- Extended target: full suite coverage, 50 initial states per task where available, 3 seeds, and all prespecified disturbance timings and magnitudes.

Do not claim suite-level generalization from 1 to 3 total episodes.

## 5. Experimental Units and Pairing

Definitions:

- Run: one execution of a configured matrix or subset, producing a manifest, logs, videos, and JSONL records.
- Episode: one rollout for one condition, task id, initial state id, seed, checkpoint, and disturbance configuration.
- Task: a LIBERO task id and task description within a named suite.
- Initial state: the index and simulator state returned by the LIBERO suite for a task.
- Trial: one selected initial-state index for a task under a seed and condition. In current scripts, `trial_id` is effectively the LIBERO initial-state index; formal logs should rename or duplicate it as `initial_state_id`.
- Seed: the random seed passed to policy, simulator, and relevant libraries. If code cannot control all random sources, this limitation must be logged.
- Condition: one formal mode such as `clean`, `reactive_disturbed`, or `stage_backtrack_subgoal`.
- Pair key: `(checkpoint_id, suite, task_id, initial_state_id, seed, disturbance_time, disturbance_magnitude, disturbance_direction, target_object, task_phase)`.

Hard Rule: Any paired comparison must use identical pair keys except for the condition being compared. Missing pairs must be reported and excluded from paired statistics, not silently treated as failures or successes.

Recommended Target: Use clean-conditioned analysis: first verify that the clean episode for a pair succeeds, then separately report recovery on all pairs and on clean-successful pairs.

## 6. Clean and Disturbed Pairing Principles

`clean` and disturbed conditions must share task, initial state, checkpoint, seed, max policy-action budget, warmup rule, and observation preprocessing.

For each formal disturbed episode, there should be a corresponding clean episode with the same pair key and no object displacement.

Hard Rule: Do not claim "disturbance causes degradation" until the clean baseline is reproduced for the same task, initial state, seed, checkpoint, and success definition.

Hard Rule: Do not use paired statistics if pair keys are not strictly matched.

## 7. Disturbance Variables

Each disturbance must be specified before running:

- Time: policy step index after warmup, or semantic phase if a validated phase detector exists.
- Magnitude: displacement size in simulator coordinates, e.g. `(dx, dy, dz)` or planar distance.
- Direction: signed vector and named direction family such as `+x`, `-x`, `+y`, `-y`, diagonal, or radial away from gripper.
- Target object: object name, simulator body, free joint, and whether target selection is manual, heuristic, or detector-based.
- Task phase: pre-contact, approach, grasp/contact, lift, transport, placement, post-placement, or unknown.

Hard Rule: A fixed policy-step trigger, such as step 70, must be described as a step trigger, not as a semantic phase trigger. Semantic phase claims require an observer, state machine, or validated detector.

Recommended disturbance grid:

- Timing: early, mid, late policy steps, plus phase-aligned timings once detectors exist.
- Magnitude: small, medium, large, where thresholds are fixed in config before running.
- Direction: at least four cardinal planar directions for formal robustness claims.
- Target: task-relevant target object first; distractor object only in a separate negative-control block.
- Phase: initially labeled by trigger plan; later confirmed by detector or annotation.

## 8. Formal Modes

The seven formal modes are:

- `clean`: no displacement. This is the baseline success condition.
- `reactive_disturbed`: object is displaced and the same policy continues with the original task prompt. This is the primary disturbed baseline.
- `verifier_stop`: the system detects or is told continuation is invalid and stops or requests full replanning. This is a safety-stop baseline, not a recovery method.
- `structured_relocalize_prompt`: after disturbance, the prompt asks the policy to relocalize the affected object at its current position and complete the original task. This is a prompt intervention, not proof of a full symbolic recovery architecture.
- `stage_backtrack_subgoal`: after disturbance, the system issues a prompt that restarts the affected manipulation stage in the current world. This is a current-world recovery prompt baseline if no reset or rollback occurs.
- `full_reset_replan`: the environment is reset to the initial state and the policy replans from the beginning. This is a reset baseline that removes the post-disturbance world.
- `oracle_rollback`: the simulator state is restored to a pre-disturbance state. This is an ideal upper bound and diagnostic sanity check only.

Mode classes:

- Realistic current-world methods: `reactive_disturbed`, `structured_relocalize_prompt`, `stage_backtrack_subgoal` if implemented without reset/rollback and without oracle state.
- Safety baseline: `verifier_stop`.
- Reset baseline: `full_reset_replan`.
- Ideal upper bound: `oracle_rollback`.
- Baseline control: `clean`.

## 9. Fair Action Budget

Default formal budget:

- `max_policy_steps_after_warmup`: 220 unless changed before all runs.
- `num_warmup_steps`: 10 unless changed before all runs.
- `max_total_env_steps`: warmup steps plus policy steps plus any reset or rollback refresh steps.

Hard Rule: Report both success and cost. At minimum, report policy steps, total environment steps, warmup steps, reset steps, rollback refresh steps, and whether any mode received a fresh budget.

Budget per mode:

- `clean`: 220 policy steps after warmup.
- `reactive_disturbed`: 220 policy steps after warmup, including all steps before and after disturbance.
- `verifier_stop`: same maximum, but stop event terminates the episode and counts as a stop, not a task success unless the LIBERO task was already completed before stop.
- `structured_relocalize_prompt`: same maximum as `reactive_disturbed`. Prompt change does not grant extra policy steps.
- `stage_backtrack_subgoal`: same maximum as `reactive_disturbed`. Stage restart does not grant extra policy steps.
- `full_reset_replan`: must be reported in two ways: raw success with reset, and budget-normalized success or cost-normalized comparison. Reset warmup and any restarted policy steps count in total environment-step cost.
- `oracle_rollback`: rollback and refresh steps count in total environment-step cost. It must not be compared as a realistic method.

Recommended Target: Include a matched-budget analysis where all modes have the same total number of policy decisions after the original episode start, and a cost-aware analysis that allows reset/rollback but reports the extra cost.

## 10. Warmup Step Rule

Hard Rule: Warmup steps must be logged separately as `warmup_env_steps`.

Default interpretation:

- Warmup steps are not policy actions and are not included in `num_policy_steps`.
- Warmup steps are included in `total_env_steps` and in wall-clock cost.
- If a reset performs a second warmup, those steps must be logged as `reset_warmup_env_steps` and included in reset cost.

Do not mix runs where warmup is counted differently in the same formal table.

## 11. Reset and Rollback Timing

Hard Rule: A reset or rollback event must have an event log with policy step, environment step, pre-event state reference, post-event state reference, and refresh action count.

`full_reset_replan` timing:

- The disturbance event occurs at the prespecified trigger.
- The environment reset returns to the initial state and removes the disturbed world.
- Reset time and any post-reset stabilization steps must be counted as cost.
- Success after full reset cannot be interpreted as recovery from the displaced world.

`oracle_rollback` timing:

- The pre-disturbance simulator state is saved before the displacement.
- The disturbance is applied and then the simulator state is restored.
- Any dummy action or no-op used to refresh observations counts as rollback refresh cost.
- Success after rollback is an upper bound on what might be possible if the disturbance had been undone, not evidence that the policy recovered in the changed world.

## 12. Manual Intervention Exclusion

Hard Rule: Any episode with manual dashboard buttons, manual pause/resume decisions, manual step decisions, manual object motion, human-selected recovery action during the episode, or post-hoc removal of a failure must be excluded from autonomous success-rate metrics.

Manual episodes may be retained as:

- Debug traces.
- Failure case illustrations, if labeled manual.
- Qualitative UI demonstrations.

Every excluded episode must remain in the raw archive with an exclusion reason. Do not delete failed or inconvenient episodes.

## 13. Success, Failure, Stop, Timeout, and Error Definitions

Success:

- Formal success is the environment's task-success signal, after verifying the wrapper semantics.
- Current code often treats `done` as success. This must be audited before paper claims.

Failure:

- An episode is a task failure when it terminates without success, reaches timeout without success, stops before success, or enters an unrecoverable policy failure state.

Stop:

- A stop is an intentional verifier or controller termination before success.
- A stop is not a task success unless task success was already true before the stop.

Timeout:

- A timeout occurs when the maximum policy or environment step budget is exhausted without success.
- Timeout must be separated from policy stop and simulator error.

Error:

- An infrastructure error includes simulator crash, model inference exception, missing checkpoint, missing video, corrupted JSON, invalid joint, unavailable GPU, dependency error, or file-system failure.
- Formal analysis must report error rate separately. Errors are not silently dropped.

## 14. Video and Log Saving Specification

Hard Rule: Every formal episode must save:

- Raw video at policy-decision resolution or documented frame rate.
- Episode JSONL record.
- Action trace with policy step, raw action, environment action, reward, `done`, and termination reason.
- Disturbance record with target joint or body, before and after qpos or pose, requested delta, and applied delta.
- Run manifest with command, git commit, config hash, checkpoint id, suite, task ids, seeds, and environment versions.

Recommended Target:

- Save event-level JSONL with `warmup`, `disturbance`, `prompt_change`, `stop`, `reset`, `rollback`, `success`, `timeout`, and `error` events.
- Save annotated videos separately from raw videos. Annotated overlays must not replace raw videos.
- Store all outputs under immutable timestamped run directories.

## 15. Sample Size Plan

Smoke:

- Purpose: verify imports, observation/action path, video writing, qpos mutation, and JSON output.
- Size: 1 task, 1 initial state, 1 seed, minimal modes.
- Claim allowed: pipeline reached or failed a smoke objective.

Pilot:

- Purpose: find stale-observation bugs, target-selection failures, budget mismatches, and estimate variance.
- Size: recommended at least 3 tasks x 3 initial states x primary modes x 1 seed.
- Claim allowed: pilot patterns and debugging findings only.

Formal minimum:

- Purpose: support primary paired comparisons.
- Size: recommended at least 5 tasks x 5 initial states x 3 seeds for each primary checkpoint and condition, subject to compute.
- Claim allowed: bounded to the tested suite, tasks, checkpoints, and disturbance grid.

Extended target:

- Purpose: suite-level and checkpoint-level robustness analysis.
- Size: full selected suite, all available initial states or a preregistered random sample, 3 seeds, multiple timings, magnitudes, and directions.
- Claim allowed: only after confidence intervals and missing-pair handling are complete.

Power:

- Do not state that a sample size has adequate statistical power without specifying baseline rate, expected effect size, alpha, test, and power target.

## 16. Debug and Formal Experiment Isolation

Hard Rule: Debug runs and formal runs must use separate output roots, separate run manifests, and separate labels.

Debug runs may use:

- Dashboard UI.
- Manual stepping.
- Hand-picked tasks.
- Reduced budgets.
- Unvalidated detectors.

Formal runs must use:

- Headless CLI.
- No human intervention during episodes.
- Frozen config.
- Full logging.
- Predefined inclusion and exclusion criteria.

Do not merge debug episodes into formal JSONL or summary tables.

## 17. Environment and Code Version Freeze

Hard Rule: Before formal runs, freeze and record:

- Git commit hash or explicit source snapshot checksum.
- Diff status.
- Python version.
- LIBERO, robosuite, MuJoCo, OpenVLA, PyTorch, Transformers, CUDA, and driver versions.
- Checkpoint path and checksum or manifest.
- Exact command and config file.
- Hostname, date, and output directory.

Recommended Target: Run a static manifest command before and after each formal batch and store it with outputs.

Known issue: The provided `/home/lijingsu/vla` directory may not be a git repository. If no git commit exists, use a source snapshot checksum and do not claim commit-level reproducibility until the code is under version control.

## 18. Statistical Analysis Plan

Primary binary outcomes:

- Use paired binary analysis when strict pairs exist. Recommended tests include McNemar-style tests for paired success/failure transitions and bootstrap confidence intervals over pair keys.
- Report success rates with binomial confidence intervals for each condition.
- Report clean-to-disturbed degradation as paired difference where possible.
- Report recovery gain over `reactive_disturbed` as paired difference for the same disturbed matrix.

Hierarchical structure:

- Treat task, initial state, seed, checkpoint, and disturbance condition as structured factors.
- Recommended model for extended analysis: mixed-effects logistic regression or hierarchical bootstrap with task and initial state grouping.

Multiple comparisons:

- Predefine primary comparisons: `clean` vs `reactive_disturbed`; `reactive_disturbed` vs each current-world recovery method.
- Mark timing, magnitude, direction, and target-object analyses as secondary or exploratory unless powered and preregistered.

Missing data:

- Report missing, excluded, timeout, stop, and error counts by condition.
- Paired analysis excludes incomplete pairs and reports the exclusion count.
- Unpaired descriptive rates may be reported separately with clear labeling.

## 19. Ablation Plan

Required ablations:

- Timing: early vs mid vs late disturbance.
- Magnitude: small vs medium vs large displacement.
- Direction: at least cardinal directions once target-object geometry supports it.
- Checkpoint: base vs LIBERO-finetuned.
- Mode: `reactive_disturbed`, `structured_relocalize_prompt`, `stage_backtrack_subgoal`, `verifier_stop`, `full_reset_replan`, `oracle_rollback`.
- Budget: equal policy budget vs cost-aware reset/rollback budget.

Recommended ablations:

- Target object: task-relevant object vs distractor object.
- Prompt information: object-only prompt vs object plus current-position phrasing vs stage-backtrack subgoal.
- Detector source: oracle affected object vs heuristic affected object vs learned or state-based observer.
- Observation refresh: immediate stale-observation implementation vs fixed fresh-observation implementation, only as a correctness audit and not mixed into final method comparison.

## 20. Failure Case Sampling Rules

Hard Rule: Failure videos used in the paper must be sampled from the formal run archive with pair keys, not from ad hoc dashboard runs unless clearly labeled qualitative.

Sampling plan:

- Include at least one representative failure per major failure taxonomy class when available.
- Include both successful and failed disturbed episodes for each claimed recovery method.
- Include clean-success/disturbed-failure pairs for degradation examples.
- Include current-world recovery failures, reset successes, and oracle rollback successes only with correct labels.
- Sample failures before watching all videos for cherry-picking, or report the selection rule used.

Recommended Target: Maintain a `failure_case_index.csv` with run id, episode id, pair key, mode, failure labels, video path, annotator, and annotation timestamp.
