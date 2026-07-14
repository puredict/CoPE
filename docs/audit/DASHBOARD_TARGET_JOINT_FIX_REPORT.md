# Dashboard Target Joint Fix Report

Date: 2026-07-14

## Summary

Root cause: the real Dashboard called strict `select_target_joint(..., "auto")`
during `Load task`. LIBERO-Spatial task 0 has two tied black-bowl candidates
(`akita_black_bowl_1_joint0` and `akita_black_bowl_2_joint0`), so the stage 1.6
protection correctly rejected automatic target selection. The Dashboard was
wrong to require final target selection during task inspection.

Fix commit: final branch `HEAD`, reported after commit creation.
Base main commit: `fd7f6e53178e5820816dfead2076835bd7910f6d`
Branch: `fix/dashboard-target-joint-selection`

## Files Changed

- `libero_experiment_core.py`
- `libero_real_backend.py`
- `libero_dashboard_controller.py`
- `libero_dashboard.py`
- `tests/test_experiment_helpers.py`
- `tests/test_dashboard_interactive_marking.py`
- `docs/audit/DASHBOARD_TARGET_JOINT_FIX_REPORT.md`

## Behavior Changes

Clean mode:

- `mode=clean` with `auto_disturbance=false` allows empty target joint.
- `Load task` creates the real environment, captures the policy camera frame,
  and lists target candidates without final target selection.
- `Start` is allowed without a target joint.

Disturbed modes:

- `reactive_disturbed`, `structured_relocalize_prompt`,
  `stage_backtrack_subgoal`, or `auto_disturbance=true` still require a target
  joint before starting.
- `Load task` only inspects candidates and does not enter `ERROR` on tied
  candidates.
- `Start` rejects missing/ambiguous target selection with:
  `Please select a target joint before starting a disturbed run.`
- The controller remains `READY` after that validation error.
- Explicit valid target selection is accepted.
- Explicit invalid target selection is rejected before enqueueing a run.
- Strict `select_target_joint(..., "auto")` remains unchanged and still raises
  on tied candidates.

Target candidate UI:

- Target joint is now an editable dropdown when Gradio supports
  `allow_custom_value`; otherwise the Textbox fallback is kept.
- `Load task` updates dropdown choices, selected recommendation, candidate
  score/reason text, and ambiguous status.
- The Dashboard callback now waits for the current worker `Load task` result
  instead of reusing stale candidate state from a previous load.

## Validation

CPU tests:

- Command: `scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python -m pytest -q`
- Result: `43 passed in 4.01s`

Compile check:

- Command: `scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python -m py_compile libero_real_backend.py libero_dashboard.py libero_dashboard_controller.py`
- Result: passed

Whitespace check:

- Command: `git diff --check`
- Result: passed

Hardcode check:

- Searched the changed source for the temporary smoke output path, timestamp,
  and task-specific smoke constants.
- Result: no hardcoded task/state/seed/output path in source. Task-specific
  joint names appear only in tests and existing audit documentation.

## Real Load-Task Smoke

Dashboard command:

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python -u \
  libero_dashboard.py \
  --real \
  --host 127.0.0.1 \
  --port 7861
```

Model/checkpoint:

- `/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial`
- Device: `cuda:0`

Clean validation:

- Mode: `clean`
- Auto disturbance: `false`
- Task/trial/seed: `0 / 0 / 7`
- `Load model`: passed
- `Load task`: passed
- Policy camera: frame returned by Dashboard refresh
- Candidates included both:
  - `akita_black_bowl_1_joint0`
  - `akita_black_bowl_2_joint0`
- Ambiguous candidate state: `true`
- No `ERROR` state

Disturbed validation:

- Mode: `reactive_disturbed`
- Auto disturbance: `false`
- `Load task`: passed, state stayed `READY`
- Missing target `Start`: rejected with the expected validation message and
  state stayed `READY`
- Explicit target `akita_black_bowl_1_joint0`: accepted
- Immediately issued Safe Stop
- Policy steps consumed before stop: `0`
- Run directory from the immediate-stop check:
  `/home/lijingsu/vla/interactive_outputs/dashboard_target_joint_fix/20260714T075127Z_task0_trial0_reactive_disturbed_f9bd4cf5`

This was not a rollout, not a formal episode, not a recovery experiment, and
not used for official success metrics.

## Resource Release

Before Dashboard launch:

- GPU memory: all 8 GPUs at approximately `12 MiB`
- No Dashboard process
- Port `7861` not listening

After Dashboard shutdown:

- `ps -eo pid,stat,etime,cmd | grep '[l]ibero_dashboard.py'`: no output
- `ss -ltnp | grep 7861`: no output
- GPU memory: all 8 GPUs at approximately `12 MiB`

## Unverified

- No new full episode rollout was run.
- No manual disturbance was run.
- No recovery comparison was run.
- Browser visual interaction was validated through Gradio HTTP callbacks rather
  than by manual clicking in a browser.

## Recommendation

Recommend merging after review. The fix preserves the existing strict target
selection guard and moves Dashboard validation to the correct point in the
workflow.
