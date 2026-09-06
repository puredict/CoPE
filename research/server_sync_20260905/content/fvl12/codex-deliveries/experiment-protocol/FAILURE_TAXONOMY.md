# Failure Taxonomy for Disturbance Recovery Episodes

This taxonomy defines failure labels for LIBERO / OpenVLA disturbance recovery episodes. It is intended for video and log annotation after formal runs. Labels describe observed failure modes; they do not by themselves explain model internals.

## 1. Annotation Rules

Hard Rule: Preserve raw videos and raw logs. Annotated labels are metadata, not replacements for source evidence.

Hard Rule: A task failure can have multiple labels. Use all labels supported by evidence.

Hard Rule: Do not assign a semantic label from video alone if the label requires simulator state, contact, grasp, pose, stage, or observer evidence.

Recommended fields per annotation:

- `episode_id`
- `run_id`
- `pair_key`
- `mode`
- `checkpoint`
- `task_id`
- `initial_state_id`
- `seed`
- `disturbance_step`
- `failure_labels`
- `primary_failure_label`
- `evidence_paths`
- `annotator`
- `annotation_timestamp`
- `uncertainty`

## 2. Label Summary

| Label | Strategy failure? | Exclude from policy metric? | Multi-label allowed? |
| --- | --- | --- | --- |
| `perception_failure` | Usually yes | No | Yes |
| `wrong_object_selection` | Usually yes | No | Yes |
| `localization_failure` | Usually yes | No | Yes |
| `approach_failure` | Usually yes | No | Yes |
| `grasp_failure` | Usually yes | No | Yes |
| `dropped_object` | Usually yes | No | Yes |
| `transport_failure` | Usually yes | No | Yes |
| `placement_failure` | Usually yes | No | Yes |
| `stale_observation` | Implementation failure or confound | Report separately; may exclude from method comparison if predeclared | Yes |
| `prompt_recovery_selection_failure` | Yes for recovery method | No | Yes |
| `timeout` | Yes or consequence | No | Yes |
| `simulator_infrastructure_error` | No | Yes for autonomous policy metrics, report error rate | Yes |
| `unknown` | Unknown | No unless paired with infrastructure exclusion | Yes |

## 3. Failure Labels

### 3.1 `perception_failure`

Operational definition: The policy or recovery system behaves as if the relevant object, gripper state, or scene change was not perceived after disturbance.

Observable evidence:

- Object is visibly displaced in raw video and qpos or pose log confirms displacement.
- Policy continues executing pre-disturbance trajectory without observable correction.
- Observer or detection log, if present, reports missing or stale object detection.
- Action trace shows no meaningful redirection after the first fresh observation, under a predefined action-change or progress rule.

Cannot judge solely from:

- A single action vector change or lack of change.
- A prompt string that mentions the object.
- Human intuition that the robot "should have seen it."
- A video without knowing whether the observation was fresh or stale.

### 3.2 `wrong_object_selection`

Operational definition: The system selects or manipulates an object different from the task-relevant target or the object actually displaced.

Observable evidence:

- Logged `target_joint`, selected object name, or recovery state names an object inconsistent with the task description and simulator object list.
- Video shows the end effector approaching or manipulating a different object while the required object remains unaddressed.
- State or contact log confirms interaction with the wrong object.

Cannot judge solely from:

- Heuristic token overlap between task text and joint name.
- Object names that are ambiguous without simulator mapping.
- A cropped video frame where objects cannot be distinguished.

### 3.3 `localization_failure`

Operational definition: The system acts on an outdated or incorrect pose estimate of the relevant object after disturbance.

Observable evidence:

- End effector moves to the pre-disturbance object location rather than the logged post-disturbance pose.
- Detector or observer output localizes the target at an incorrect position.
- Repeated approach commands converge to empty space or a wrong pose after the disturbance.
- Simulator pose logs show a mismatch between expected target pose and acted-on pose.

Cannot judge solely from:

- Failure to complete the task.
- Longer path length.
- A natural-language relocalization prompt.
- Video without pose reference or camera calibration when the distinction is ambiguous.

### 3.4 `approach_failure`

Operational definition: The policy identifies the target but fails to move the end effector into a feasible pre-grasp or interaction pose.

Observable evidence:

- Target object is known and localized, but gripper path stalls, oscillates, collides, or approaches from an infeasible direction.
- End-effector pose remains outside a predefined distance threshold from the target for the allotted approach window.
- Contact logs show no target contact after approach attempts.

Cannot judge solely from:

- The object not being grasped, because that may be localization or grasp failure.
- Low final reward alone.
- One non-contact frame before the approach window ends.

### 3.5 `grasp_failure`

Operational definition: The policy reaches the object but fails to establish a stable grasp or task-relevant contact.

Observable evidence:

- Gripper contacts the target but closes too early, too late, with poor alignment, or without lifting the object.
- Contact logs show brief contact but no sustained grasp.
- Object pose does not follow gripper motion after closure under a predefined grasp criterion.
- Gripper state indicates closure while object remains stationary or slips immediately.

Cannot judge solely from:

- The task timing out.
- A visual frame where gripper appears near the object.
- Lack of final success, because failure may occur later during transport or placement.

### 3.6 `dropped_object`

Operational definition: The object was grasped or transported and then unintentionally released, slipped, collided away, or fell outside the intended manipulation path.

Observable evidence:

- Object follows the gripper for a period and then separates unexpectedly.
- Contact or grasp detector changes from grasped to not grasped before planned release.
- Object falls, slides, or moves due to collision while transport is incomplete.

Cannot judge solely from:

- Final object not at goal, because placement may have failed without a drop.
- Gripper opening near the goal if release was intended.
- A single frame without temporal context.

### 3.7 `transport_failure`

Operational definition: After a successful grasp or contact, the policy fails to carry the object to the goal region or moves it along an invalid path.

Observable evidence:

- Stable grasp is established, but the object does not approach the goal region.
- Object collides with obstacles or scene geometry during movement and cannot continue.
- End-effector path oscillates, reverses repeatedly, or leaves the workspace before placement.
- Pose logs show object-to-goal distance not decreasing over a defined window after grasp.

Cannot judge solely from:

- Long episode duration.
- A failed final placement.
- Any collision without determining whether it caused failure.

### 3.8 `placement_failure`

Operational definition: The object reaches the goal vicinity but is not placed in the required pose, container, receptacle, or spatial relation.

Observable evidence:

- Object is carried to goal area but released outside the success region.
- Task success predicate remains false after object placement attempt.
- Object ends in wrong receptacle, wrong side, wrong orientation, or unstable pose as defined by task.
- Pose logs show final object-goal relation outside threshold.

Cannot judge solely from:

- The object being visually close to the target.
- The robot opening the gripper.
- A video angle that hides the goal relation.

### 3.9 `stale_observation`

Operational definition: The policy computes at least one action from an observation captured before the simulator state mutation or recovery state update that should have changed the scene.

Observable evidence:

- Code path or event log shows qpos mutation followed by policy inference using pre-mutation `obs`.
- Observation timestamp or frame hash predates disturbance event while action is labeled post-disturbance.
- Audit instrumentation records `fresh_obs=false` for the first post-disturbance policy step.

Cannot judge solely from:

- The robot taking one bad step after disturbance.
- Human visual interpretation of latency.
- The existence of a disturbance record without observation timestamps.

### 3.10 `prompt_recovery_selection_failure`

Operational definition: The recovery system chooses an inappropriate prompt, subgoal, stop/reset decision, affected object, or recovery mode for the disturbed state.

Observable evidence:

- Logged recovery prompt references the wrong object, wrong stage, wrong goal, or an impossible action.
- Recovery mode resets or stops despite a protocol requiring current-world continuation.
- Observer or oracle label, if allowed for analysis, disagrees with selected recovery target or stage.
- The prompt omits necessary recovery information that the configured method claims to provide.

Cannot judge solely from:

- The final episode failing.
- A prompt that sounds unnatural to a human.
- A scripted `has_selective_recovery_state` boolean.
- A recovery prompt improvement in another episode.

### 3.11 `timeout`

Operational definition: The episode exhausts the configured step budget without task success and without a separate stop or infrastructure error.

Observable evidence:

- `termination_reason=timeout`, or `success=false` with `num_policy_steps` equal to the configured max budget under a validated inference rule.
- Logs show no crash or manual stop.
- Video reaches final saved step without success predicate.

Cannot judge solely from:

- Missing video tail.
- A long video.
- `success=false` if the script crashed or stopped early.

### 3.12 `simulator_infrastructure_error`

Operational definition: The episode fails because of simulator, environment, model, dependency, filesystem, or logging infrastructure rather than the policy's manipulation behavior.

Observable evidence:

- Exception trace, simulator crash, missing checkpoint, missing dependency, invalid joint error, corrupted JSON, failed video writer, GPU/driver error, disk-full error, or process termination.
- Output record is incomplete or absent for reasons captured in logs.
- State mutation fails to apply or applies to an unintended joint due to simulator/model mismatch.

Cannot judge solely from:

- An unusual robot motion.
- A failed task.
- A missing success record without stdout/stderr.

### 3.13 `unknown`

Operational definition: The episode fails, but available evidence is insufficient to assign a more specific label.

Observable evidence:

- Failure is verified, raw video/logs exist, and other labels were considered but not supported.
- Annotation record states what evidence is missing.

Cannot judge solely from:

- Annotator uncertainty without reviewing logs.
- A desire to avoid multi-label assignment.
- Lack of time to inspect available evidence.

## 4. Primary Failure Label Selection

When multiple labels apply, choose one primary label for summary plots using this priority order:

1. `simulator_infrastructure_error`
2. `stale_observation`
3. `wrong_object_selection`
4. `prompt_recovery_selection_failure`
5. `perception_failure`
6. `localization_failure`
7. `approach_failure`
8. `grasp_failure`
9. `dropped_object`
10. `transport_failure`
11. `placement_failure`
12. `timeout`
13. `unknown`

The priority order is for visualization only. Preserve all secondary labels.

## 5. Exclusion Policy

Exclude from autonomous policy success-rate metrics:

- Manual intervention episodes.
- Simulator or infrastructure errors, reported separately.
- Corrupted or missing records where success cannot be verified.
- Episodes from debug configs mixed into formal output directories.

Do not exclude:

- Ordinary policy failures.
- Timeouts.
- Stops by `verifier_stop`, unless the analysis table explicitly studies non-stop recovery only.
- Stale-observation episodes unless the protocol predefines a correctness-audit exclusion. If excluded, report both with-stale and without-stale analyses when possible.

## 6. Evidence Package Per Failure Case

Each paper failure example should link:

- Raw video.
- Episode JSONL row.
- Event log if available.
- Run manifest and config.
- Pair key.
- Annotated failure labels.
- Reason it was sampled.

Do not present a failure as representative unless the sampling rule is documented.
