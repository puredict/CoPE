# FINAL_REPORT: G_EXPERIMENT_PROTOCOL

## 1. Completion Summary

Created formal research-design documentation for the LIBERO / OpenVLA disturbance recovery study. The work defines experiment protocol, metric boundaries, paper evidence requirements, failure taxonomy, and an example configuration matrix.

No Python or shell source code was modified. No GPU was used. No OpenVLA checkpoint was loaded. No LIBERO rollout or experiment was run. No dependencies were installed.

Important infrastructure note: `/home/lijingsu/vla` exists on the remote host, but it is not a git repository. Therefore a standard `git worktree add` could not be used. I created an isolated copy at `/home/lijingsu/codex-worktrees/experiment-protocol`, initialized git there, checked out branch `codex/experiment-protocol`, and committed only the new documentation/config files.

## 2. New Files

Committed files:

- `EXPERIMENT_PROTOCOL.md`
- `METRICS_AND_CLAIMS.md`
- `PAPER_EVIDENCE_CHECKLIST.md`
- `FAILURE_TAXONOMY.md`
- `experiment_matrix.example.yaml`
- `EXPERIMENT_CONFIG_MATRIX.example.yaml`

The last file is an identical compatibility copy of `experiment_matrix.example.yaml` because the user request named the lowercase file while the task package named `EXPERIMENT_CONFIG_MATRIX.example.yaml`.

## 3. Main Experiment Design

The protocol defines a paired design over checkpoint, suite, task id, initial state id, seed, disturbance timing, magnitude, direction, target object, and task phase.

Formal modes:

- `clean`
- `reactive_disturbed`
- `verifier_stop`
- `structured_relocalize_prompt`
- `stage_backtrack_subgoal`
- `full_reset_replan`
- `oracle_rollback`

The design separates realistic current-world methods from safety stop, reset baseline, and oracle upper bound. It requires headless formal runs, no manual intervention, strict pair keys for paired claims, explicit warmup/reset/rollback cost accounting, run manifests, raw videos, JSONL logs, and confidence intervals.

## 4. Main Metrics

Primary metrics:

- Disturbed success rate.
- Clean-to-disturbed degradation.
- Recovery gain over `reactive_disturbed`.
- Paired outcome transitions.

Auxiliary metrics:

- Post-disturbance recovery steps.
- Object rediscovery steps.
- Re-contact steps.
- Re-grasp steps.
- Total policy and environment steps.
- Invalid action count.
- Timeout rate.
- Stop rate.
- Recovery attempt count.

The metrics document states which are currently measurable from existing logs, which require new detectors, which are only proxies, and which must not be filled from subjective video viewing.

## 5. Paper Claims Not Allowed

The documents explicitly prohibit these claims without additional evidence:

- `oracle_rollback` proving real recovery.
- `full_reset_replan` being local replanning.
- `verifier_stop` being recovery.
- Preset booleans being experimental measurements.
- Prompt rewriting proving a full symbolic recovery architecture.
- Stable generalization from only 1 to 3 runs.
- Mixing manual dashboard/button episodes into autonomous success rates.
- Claiming failed-stage identification without an observer/detector.
- Claiming degradation without reproducing clean baseline.
- Using paired statistics without strict pairing.

## 6. Static Validation and Tests

Static checks passed:

- `git diff --cached --check`: exit 0.
- Post-commit tracked status check: exit 0.
- Commit file list verified: exit 0.
- YAML lowercase and uppercase copies identical: exit 0.
- Required-section and required-term `rg` checks: exit 0.

No runtime tests were run by design. See `TESTS.log` for details.

## 7. Issues Found and Not Verified

Needs code audit or real experiment confirmation:

- Whether LIBERO wrapper `done` exactly means task success.
- Whether all post-disturbance policy steps use fresh observations after qpos mutation.
- Whether target-joint auto selection chooses the correct task object.
- Whether reset and rollback costs are logged consistently in future code.
- Whether pair keys include initial state id and seed across all mode scripts.
- Whether semantic task phase can be detected or must remain a trigger label.
- Whether contact, grasp, rediscovery, re-contact, and re-grasp detectors exist or need to be implemented.
- Whether `/home/lijingsu/vla` should be put under git before future parallel worktree sessions.

## 8. File Boundary Compliance

Committed changes are limited to research documents and configuration examples. No Python files, shell scripts, model files, outputs, or existing documents were changed in the commit.

The isolated directory contains copied source files from `/home/lijingsu/vla` as untracked files because the original source was not a git repository. They were not staged or committed.

## 9. Commit

- Branch: `codex/experiment-protocol`
- Commit: `bc6fc0d3d0da1c40cb7fd2af3aa87a24410bba95`
- Message: `docs: define disturbance recovery experiment protocol`
- Worktree path: `/home/lijingsu/codex-worktrees/experiment-protocol`
- Delivery path: `/home/lijingsu/codex-deliveries/experiment-protocol`

## 10. Integration Notes

Future integration should cherry-pick or manually copy the docs commit into the real project repository once `/home/lijingsu/vla` is under git. If only one config filename is desired, keep `experiment_matrix.example.yaml` for the user-facing name or `EXPERIMENT_CONFIG_MATRIX.example.yaml` for package compatibility, then delete the duplicate in an integration commit.
