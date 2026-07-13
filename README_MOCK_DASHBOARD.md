# Mock LIBERO Dashboard

This workflow adds a CPU-only mock dashboard for exercising the browser UI,
controller state machine, command queue, worker lifecycle, and output files
without loading OpenVLA, LIBERO, robosuite, MuJoCo, or GPU resources.

## Scope

The mock dashboard is intentionally not a real LIBERO/OpenVLA integration. It
generates synthetic RGB camera frames with visible task text, step, mode,
disturbance state, pause state, and simulated object position. A later real
backend can implement the same controller-facing operations while preserving the
threading boundary.

No existing experiment scripts or `run_*.sh` files are changed by this workflow.

## Files

- `libero_mock_backend.py`: deterministic CPU backend, dynamic frames, mock
  rewards/actions/prompts/disturbances, best-effort video writer.
- `libero_dashboard_controller.py`: explicit state machine, single worker,
  command queue, snapshots, event logging, and output finalization.
- `libero_dashboard.py`: Gradio Blocks UI and `--mock-smoke` CLI.
- `tests/test_dashboard_controller.py`: controller and state-machine coverage.
- `tests/test_mock_backend.py`: backend frame/action/prompt/video checks.
- `tests/test_mock_dashboard.py`: end-to-end mock smoke output checks.
- `tests/test_mock_dashboard_import.py`: import boundary check.

## State Model

Implemented states:

```text
IDLE
LOADING
READY
RUNNING
PAUSED
STOPPING
SUCCEEDED
FAILED
ERROR
```

`COMPLETED` is accepted as a compatibility alias for `SUCCEEDED` inside the
controller enum, but snapshots report `SUCCEEDED`.

Typical transitions:

```text
IDLE -> LOADING -> READY
READY -> RUNNING
RUNNING <-> PAUSED
RUNNING/PAUSED -> STOPPING -> FAILED   # manual stop
RUNNING -> SUCCEEDED                   # mock success
RUNNING -> FAILED                      # mock failure/timeout/verifier stop
RUNNING -> ERROR                       # uncaught worker exception
SUCCEEDED/FAILED/ERROR -> READY        # reset while backend remains loaded
```

Illegal commands return structured `CommandResult(ok=False, message=...)` and do
not silently mutate the backend.

## Thread Boundary

- Gradio callbacks only enqueue commands and read snapshots.
- The controller owns one persistent background worker thread.
- Only that worker calls backend methods such as `load_model`, `start_episode`,
  `step`, `apply_disturbance`, and output finalization.
- Shared snapshot/frame/event state is protected by a lock and copied on read.
- No two episodes can run at once; duplicate start is rejected before enqueue.
- Page refresh uses polling and never advances the episode.
- Client disconnects do not stop the worker or interrupt result saving.

## Mock Behaviors

The mock backend simulates:

- reward growth;
- auto disturbance at a configured policy step;
- manual disturbance from UI command payload;
- prompt switch for `structured_relocalize_prompt` and
  `stage_backtrack_subgoal`;
- success;
- failure;
- timeout;
- manual stop;
- worker exception.

Every dashboard run writes:

```text
run_config.json
events.jsonl
episode_summary.json
raw.mp4
annotated.mp4
```

Manual controls are logged as events such as:

```text
manual_pause
manual_resume
manual_step
manual_disturbance
manual_stop
```

Dashboard runs are marked `interactive=true` and `formal_run=false`. Any pause,
single-step, manual disturbance, or stop also sets `manual_intervention=true`.

## Run The Web UI

From the isolated worktree:

```bash
python libero_dashboard.py \
  --mock \
  --host 127.0.0.1 \
  --port 7861
```

The app launches with:

```python
share=False
server_name="127.0.0.1"
```

For remote access, use SSH port forwarding from your local machine:

```bash
ssh -N -L 7861:127.0.0.1:7861 USER@GPU_SERVER
```

Then open:

```text
http://127.0.0.1:7861
```

## Non-Web Smoke Test

```bash
python libero_dashboard.py \
  --mock-smoke \
  --output-dir /tmp/libero_mock_smoke
```

This validates load, start, pause, strict single-step, manual disturbance,
resume, success, reset, manual stop, JSON parsing, event markers, and output
file creation.

## Test Commands

```bash
python -m py_compile \
  libero_dashboard_controller.py \
  libero_mock_backend.py \
  libero_dashboard.py

pytest -q \
  tests/test_dashboard_controller.py \
  tests/test_mock_backend.py \
  tests/test_mock_dashboard.py \
  tests/test_mock_dashboard_import.py

python libero_dashboard.py \
  --mock-smoke \
  --output-dir /tmp/libero_mock_smoke
```

## Future Real Backend Interface

The real backend should preserve the controller-facing shape:

- `load_model(...)`
- `inspect_task(config)`
- `start_episode(config)`
- `should_auto_disturb(config, policy_step)`
- `apply_disturbance(config, policy_step, source, target_joint, dx, dy)`
- `step(config, policy_step, paused=False)`

The real implementation must keep OpenVLA inference, LIBERO env stepping,
MuJoCo state mutation, observation refresh, and video writing on the controller
worker thread only.
