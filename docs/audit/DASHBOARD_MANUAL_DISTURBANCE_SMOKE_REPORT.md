# Dashboard Manual Disturbance Smoke Report

Date: 2026-07-14

Branch: `validation/dashboard-manual-disturbance`

Worktree: `/home/lijingsu/codex-worktrees/dashboard-disturbance-smoke`

Base commit: `bf35c7c Merge dashboard target joint selection fix`

## Scope

This smoke validates the real Gradio Dashboard Manual Disturbance path against LIBERO/OpenVLA. It verifies that the web button path moves the selected target object, refreshes the policy observation without consuming a noop environment step, records the event with audit fields, and marks the run as excluded from formal metrics.

No changes were made in the formal `/home/lijingsu/vla` main worktree.

## Pre-checks

Commands:

```bash
CUDA_VISIBLE_DEVICES=1 scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python -m pytest -q

CUDA_VISIBLE_DEVICES=1 scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python -m py_compile \
  libero_real_backend.py \
  libero_dashboard.py \
  libero_dashboard_controller.py
```

Results after fixes:

- `45 passed in 4.04s`
- `py_compile` passed for `libero_real_backend.py`, `libero_dashboard.py`, and `libero_dashboard_controller.py`

## Dashboard Runtime

Launch command:

```bash
CUDA_VISIBLE_DEVICES=1 scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python \
  libero_dashboard.py \
  --real \
  --host 127.0.0.1 \
  --port 7862 \
  --default-checkpoint /home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial \
  --default-task-suite libero_spatial \
  --default-out-dir interactive_outputs/dashboard_manual_disturbance_smoke
```

Checks:

- GPU isolation: `CUDA_VISIBLE_DEVICES=1`
- Remote port: `7862`
- Bound address: `127.0.0.1:7862`
- `7861`: not listening
- `0.0.0.0`: not used
- Gradio launch code uses `share=False`

## Configuration

- checkpoint: `/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial`
- suite: `libero_spatial`
- task: `0`
- trial/state: `0`
- seed: `7`
- mode: `reactive_disturbed`
- target joint: `akita_black_bowl_1_joint0`
- dx: `0.10`
- dy: `0.05`
- auto disturbance: disabled
- allow multiple disturbances: disabled
- output dir: `interactive_outputs/dashboard_manual_disturbance_smoke`

## Accepted Smoke Run

Run directory:

```text
interactive_outputs/dashboard_manual_disturbance_smoke/20260714T112420Z_task0_trial0_reactive_disturbed_7698f8dd
```

Evidence file:

```text
interactive_outputs/dashboard_manual_disturbance_smoke/smoke_evidence.json
```

The smoke driver invoked the Gradio button-bound endpoints from `/config`:

- `on_load`: Load model
- `on_load_task`: Load task
- `on_start`: Start
- `on_pause_resume`: Pause
- `on_disturb`: Manual disturbance button, component target `Manual disturbance`
- `on_step`: Strict single-step
- `on_stop`: Safe stop

## Manual Flow Result

- Load model: passed
- Load task: passed
- Policy camera after task load: rendered, `256x256`
- Target candidates visible: yes
  - `akita_black_bowl_1_joint0`
  - `akita_black_bowl_2_joint0`
  - `glazed_rim_porcelain_ramekin_1_joint0`
  - `plate_1_joint0`
  - `cookies_1_joint0`
- Explicit selected target: `akita_black_bowl_1_joint0`
- Start: passed
- Pause: passed at policy step `2`
- Manual Disturbance: clicked exactly once in the accepted run
- Strict single-step: passed, policy step advanced from `2` to `3`
- Safe Stop: passed, termination reason `manual_stop`

## Disturbance Evidence

Before disturbance:

```json
[-0.06347436696231851, 0.20202566460700613, 0.8984041304892996]
```

After disturbance:

```json
[0.0365256330376815, 0.25202566460700615, 0.8984041304892996]
```

Actual delta:

```json
[0.1, 0.05000000000000002, 0.0]
```

Policy step before/after disturbance:

```json
2 -> 2
```

Observation refresh:

- `fresh_observation=true`
- `observation_refresh_method=env.env._get_observations(force_update=True)`
- `consumed_noop_env_step=false`
- policy camera hash changed immediately after disturbance:
  - before: `078baa4ae2a987c425945f25148afa4b320343c9e3250ea5d71da101ab12f819`
  - after: `1ffca83b56af568a6aa7f597b1896eca687e6b632d3c78bb49118c5fb02d938a`

## Required Events

`events.jsonl` contains:

- `manual_pause`
- `manual_disturbance`
- `manual_step`
- `manual_stop`

The single `manual_disturbance` event records:

- `target_joint=akita_black_bowl_1_joint0`
- `before_position`
- `after_position`
- `actual_delta`
- `fresh_observation=true`
- `observation_refresh_method=env.env._get_observations(force_update=True)`
- `consumed_noop_env_step=false`
- `policy_step_before_disturbance=2`
- `policy_step_after_disturbance=2`
- `policy_step_unchanged_by_disturbance=true`

## Non-formal Metrics Guard

The accepted run is marked:

- `interactive=true`
- `formal_run=false`
- `eligible_for_official_metrics=false`
- `exclude_from_formal_success_summaries=true`

Default summary behavior was verified:

```json
[
  {
    "label": "interactive-smoke",
    "run_dir": "interactive_outputs/dashboard_manual_disturbance_smoke/20260714T112420Z_task0_trial0_reactive_disturbed_7698f8dd",
    "condition": "diagnostic_skipped",
    "n": 0,
    "successes": 0,
    "success_rate": "",
    "disturbance_applied": 0
  }
]
```

The summarizer printed:

```text
WARNING: excluding 1 interactive/non-formal record(s) from formal summary
```

## Output Artifacts

All required artifacts were produced and non-empty:

- `run_config.json` - 865 bytes
- `events.jsonl` - 12299 bytes
- `actions.jsonl` - 3138 bytes
- `episode_summary.json` - 15670 bytes
- `raw.mp4` - 6588 bytes
- `annotated.mp4` - 8294 bytes

These artifacts remain under `interactive_outputs/` and are not committed.

## Fixes Made

Two dashboard correctness issues were found and fixed before the accepted smoke run:

1. `RealExperimentBackend.apply_disturbance()` now records `applied=true` plus explicit audit fields:
   - `target_joint`
   - `before_position`
   - `after_position`
   - `actual_delta`
   - `fresh_observation`
   - `observation_refresh_method`
   - `consumed_noop_env_step`
   - policy step before/after disturbance

2. `ExperimentController` now snapshots backend state before `backend.stop()` releases runtime resources, so `episode_summary.json` preserves `disturbance_count`, `last_disturbance`, `fresh_observation`, and target position after Safe Stop.

Regression tests were added for both issues.

## Resource Release

After closing the Dashboard:

- No `openvla`, `libero`, or `dashboard` processes remained.
- `7862` was not listening.
- GPU 1 memory returned to baseline: `12 MiB`, only Xorg shown in `nvidia-smi`.

## Notes

The independent git worktree did not include ignored external resource directories (`src`, `.venv`, `models`, `cache`, `libero_data`). For runtime only, ignored symlinks to `/home/lijingsu/vla` resources were created in the validation worktree. They are not committed.
