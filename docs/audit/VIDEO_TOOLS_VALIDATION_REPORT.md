# Video Tools Validation Report

## Scope

Added rollout video tooling:

- `tools/annotate_rollout_video.py`
- `tools/compose_rollout_comparison.py`
- `tools/video_io.py`
- `tests/test_video_tools.py`
- `README_VIDEO_TOOLS.md`

## Input Format

Single-episode annotation expects an episode directory or explicit paths for:

- `raw.mp4`
- `run_config.json`
- `events.jsonl`
- `actions.jsonl`
- `episode_summary.json`

The implementation reads known Stage 2.1 fields such as `task_description`, `mode`, `initial_state_id`, `seed`, `target_joint`, `policy_start_target_qpos`, `disturbance_step`, `policy_step_budget`, `warmup_simulator_steps`, `manual_intervention`, `status`, action `t`, action `video_frame_index`, action `reward`, and `uses_post_disturbance_fresh_observation`.

## Overlay Fields

The annotation overlay includes:

- task description
- mode
- camera label, explicitly `policy` or `observer`
- initial state
- seed
- policy step
- environment step
- disturbance step
- target joint
- target position
- fresh observation marker
- policy budget remaining
- reward
- episode status
- interactive/formal marker

When a disturbance occurs, the frame receives an orange border and top-right disturbance marker. Later frames receive a smaller post-disturbance marker.

Video FPS is recorded as render FPS only. The tools do not describe 30 FPS as the true policy frequency.

## Alignment Rules

Comparison inputs are passed as `mode=episode_dir` or `mode=video.mp4`.

- `policy-step`: the shared timeline is the policy step, using `actions.jsonl` `t`/`policy_step` to `video_frame_index` mapping when available.
- `disturbance-step`: each column is shifted by its disturbance anchor, so shared step `0` is the disturbance step. Clean runs use the configured disturbance step or paired metadata anchor when present.

When a source lacks a requested step:

- `freeze-last` holds the first/last available frame.
- `black` emits a black padded cell.

All columns preserve source aspect ratio through letterbox resizing.

## Real Pilot Outputs

Stage 2.1 run directory:

```text
/home/lijingsu/vla/audit_outputs/stage2_1_three_state_pilot/2026_07_13-23_33_36
```

Output directory:

```text
/home/lijingsu/codex-deliveries/video_outputs/pilot_comparisons/
```

Generated comparison videos:

- `/home/lijingsu/codex-deliveries/video_outputs/pilot_comparisons/state0_clean_vs_reactive.mp4`
- `/home/lijingsu/codex-deliveries/video_outputs/pilot_comparisons/state1_clean_vs_reactive.mp4`
- `/home/lijingsu/codex-deliveries/video_outputs/pilot_comparisons/state2_clean_vs_reactive.mp4`

Generated sidecar JSON:

- `/home/lijingsu/codex-deliveries/video_outputs/pilot_comparisons/state0_clean_vs_reactive.json`
- `/home/lijingsu/codex-deliveries/video_outputs/pilot_comparisons/state1_clean_vs_reactive.json`
- `/home/lijingsu/codex-deliveries/video_outputs/pilot_comparisons/state2_clean_vs_reactive.json`

All three sidecars record:

- `alignment=policy_step`
- `padding=freeze-last`
- `output_frames=220`
- `output_fps_render_only=30.0`
- camera label `policy`

File sizes verified:

- `state0_clean_vs_reactive.mp4`: 118866 bytes
- `state1_clean_vs_reactive.mp4`: 136225 bytes
- `state2_clean_vs_reactive.mp4`: 126022 bytes

The MP4 outputs are outside the Git worktree and were not added to Git.

## Tests

Remote project-environment tests:

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python -m pytest -q
```

Result:

```text
46 passed in 5.13s
```

Remote compile check:

```bash
/home/lijingsu/vla/.venv/bin/python -m py_compile tools/annotate_rollout_video.py \
  tools/compose_rollout_comparison.py \
  tools/video_io.py
```

Result: exit code `0`.

Local synthetic smoke with the same tests also passed in the `lerobot312` environment:

```text
3 passed in 0.89s
```

## Missing Field Handling

Missing JSON files or fields do not crash the tools. The overlay displays `unknown` where required information cannot be inferred, and warnings are emitted to stderr and recorded in sidecar JSON.

## Unverified Parts

- Observer-camera footage was not available; the implementation supports the label but does not infer observer view from policy-camera input.
- Disturbance-step alignment was verified with synthetic videos and sidecar checks, not with an additional real Stage 2.1 rendered MP4.
