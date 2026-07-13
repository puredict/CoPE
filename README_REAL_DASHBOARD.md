# Real LIBERO/OpenVLA Dashboard

This branch wires the dashboard to the validated LIBERO/OpenVLA experiment helpers without adding a second rollout implementation inside Gradio callbacks.

## Architecture

```text
Dashboard
    -> commands / snapshots only
Controller single worker
    -> backend methods only on one worker thread
RealExperimentBackend
    -> validated experiment helpers in libero_experiment_core.py
```

Gradio callbacks enqueue commands and read copied snapshots. They never call OpenVLA, LIBERO, MuJoCo, `env.step()`, qpos mutation, or observation refresh directly.

## Backend Contract

`libero_real_backend.py` implements:

```python
load(config)
reset(task, initial_state, seed)
step_once()
apply_disturbance()
get_snapshot()
stop()
close()
```

The controller also supports legacy mock methods so CPU tests can run with fake backends and without loading OpenVLA.

## Reused Validated Logic

The real backend delegates to `libero_experiment_core.py` for:

- `extract_episode_status()` success, timeout, stopped, and simulator-error semantics;
- `refresh_observation_after_sim_change()` fresh-observation refresh after qpos mutation;
- `select_target_joint()`, explicit target-joint override, and free-joint validation;
- `move_free_joint_xy()` audited target qpos mutation;
- `build_recovery_prompt()` recovery prompt semantics;
- `execute_policy_step()` OpenVLA action generation and LIBERO `env.step()`;
- `make_budget_report()` policy budget and environment-control accounting;
- `EpisodeRecorder`-compatible event and episode logging fields.

## Interactive Marking

Dashboard runs are always written as:

```json
{
  "interactive": true,
  "formal_run": false,
  "eligible_for_official_metrics": false,
  "exclude_from_formal_success_summaries": true
}
```

Manual controls additionally set `manual_intervention=true` and write one of:

```text
manual_pause
manual_resume
manual_step
manual_disturbance
manual_stop
```

`summarize_disturbance_results.py` excludes these records by default.

## Thread Boundary

- One persistent controller worker owns the backend.
- No two real episodes can run concurrently; duplicate start is rejected before enqueue.
- Pause, strict single-step, manual disturbance, and stop are processed at policy-step boundaries.
- Worker exceptions transition to `ERROR` and write `worker_error.log` plus `episode_summary.json`.
- `Safe stop` calls backend `stop()`, which closes the environment, drops model references, and clears CUDA cache.

## UI Fields

The real UI displays policy camera, task, current prompt, mode, policy step, environment step, policy budget remaining, reward, episode status, target joint, target position, disturbance state, fresh observation metadata, latest action, event tail, error text, and full snapshot JSON.

Buttons:

```text
Load model
Load task
Start
Pause / resume
Strict single-step
Manual disturbance
Safe stop
Reset
```

## Launch

Use only loopback binding and SSH forwarding:

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python \
  libero_dashboard.py \
  --real \
  --host 127.0.0.1 \
  --port 7861
```

The app refuses `--host 0.0.0.0` and always launches with `share=False`.

## Testing

CPU tests use mock or fake backends only:

```bash
/home/lijingsu/vla/.venv/bin/python -m pytest -q
```

Do not run a real smoke unless the stage 2.1 Pilot is not using the GPU and the user explicitly authorizes it. Any smoke must be one task, a small policy budget, interactive, non-formal, and written outside formal experiment output directories.
