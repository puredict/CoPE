# LIBERO / OpenVLA Dashboard

This dashboard adds a single-user Gradio control panel for LIBERO / OpenVLA disturbance experiments. It is intended for SSH-forwarded research debugging on the remote GPU host, not for public serving.

## Files

- `libero_experiment_core.py`: Gradio-independent config, prompt, joint, disturbance, observation refresh, policy-step, JSON, overlay, and recorder helpers.
- `libero_dashboard_controller.py`: thread-safe `ExperimentController`, explicit state machine, command queue, real backend, and CPU-only mock backend.
- `libero_dashboard.py`: Gradio Blocks UI and CLI entrypoint.
- `run_libero_dashboard.sh`: remote launch script.
- `tests/test_dashboard_controller.py` and `tests/test_experiment_helpers.py`: CPU-safe mock tests.

## Thread Boundary

Gradio callbacks never call OpenVLA, LIBERO, MuJoCo, `env.step()`, or `sim.forward()` directly. They only validate lightweight parameters, submit controller requests, enqueue commands, and return a message.

All model loading, environment creation, task inspection, policy inference, simulation stepping, qpos edits, observation refresh, reset, rollback, video writing, and episode finalization happen in the controller's single-worker executor. The UI timer only reads a locked snapshot plus a copied frame.

Pause, step once, manual disturbance, and stop are applied at policy-step boundaries. Pause does not interrupt a CUDA inference already in flight.

## Remote Launch

On the GPU server:

```bash
cd /home/lijingsu/vla
chmod +x run_libero_dashboard.sh
CUDA_VISIBLE_DEVICES=0 PORT=7860 ./run_libero_dashboard.sh
```

On the local computer:

```bash
ssh -N -L 7860:127.0.0.1:7860 USER@GPU_SERVER
```

Open locally:

```text
http://127.0.0.1:7860
```

The server binds to `127.0.0.1` and `share=False` by default. No X11, VNC, or remote desktop is needed. If the SSH tunnel drops, the worker episode continues; reconnect the tunnel and refresh the page to inspect the global controller state.

## EGL / OSMesa

The launcher sets EGL before Python imports LIBERO, robosuite, MuJoCo, or OpenGL:

```bash
export MUJOCO_GL="${MUJOCO_GL:-egl}"
export PYOPENGL_PLATFORM="${PYOPENGL_PLATFORM:-egl}"
```

If EGL fails on the remote machine, use OSMesa:

```bash
MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa ./run_libero_dashboard.sh
```

## Mock Mode

Mock mode does not import OpenVLA, LIBERO, or MuJoCo:

```bash
python libero_dashboard.py --mock --host 127.0.0.1 --port 7860
```

A non-interactive mock smoke test runs one short episode and exits:

```bash
python libero_dashboard.py --mock --smoke-test --default-out-dir /tmp/libero_dashboard_smoke
```

## Outputs

Each dashboard run writes:

```text
{out_dir}/{timestamp}_task{task_id}_{mode}/
    events.jsonl
    episode.json
    raw.mp4
    annotated.mp4
    dashboard.log
```

Dashboard results are written with `eligible_for_official_metrics=false` by default. Any pause, step-once, manual disturbance, stop, or other artificial control sets `human_intervention=true` in the episode output and event log. Automatic configured disturbance is recorded as experiment setup rather than human intervention.

## Suggested Real Smoke Test

After the mock tests pass, run a short real check on the remote GPU:

1. Load `/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial`.
2. Inspect task `0`.
3. Run `clean` with `max_steps=5`.
4. Pause, step once, then stop and save.
5. Run `reactive_disturbed`, queue one manual disturbance, and confirm the next displayed frame reflects the refreshed observation before the next inference.
