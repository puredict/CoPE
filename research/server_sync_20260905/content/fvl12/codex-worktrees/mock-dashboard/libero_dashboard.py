"""Gradio entrypoint for the CPU-only mock LIBERO dashboard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

from libero_dashboard_controller import (
    ControllerState,
    ExperimentController,
    snapshot_for_json,
    wait_for_state,
)
from libero_mock_backend import MOCK_EXPERIMENT_MODES, MockRunConfig


DEFAULT_CHECKPOINT = "mock://libero-dashboard"
DEFAULT_OUT_DIR = "/tmp/libero_mock_dashboard"


def make_controller() -> ExperimentController:
    return ExperimentController()


def _json_text(payload: Any) -> str:
    return json.dumps(snapshot_for_json(payload), indent=2, sort_keys=True)


def build_dashboard(controller: ExperimentController):
    try:
        import gradio as gr
    except Exception as exc:  # pragma: no cover - depends on local environment.
        raise RuntimeError(
            "Gradio is required to launch the browser dashboard, but it is not installed "
            "in the current environment. Do not install it from this workflow; run "
            "--mock-smoke to validate the controller/backend without the web UI."
        ) from exc

    try:
        from gradio_client import utils as gradio_client_utils

        original_schema_parser = gradio_client_utils._json_schema_to_python_type

        def patched_schema_parser(schema, defs):
            if isinstance(schema, bool):
                return "Any"
            return original_schema_parser(schema, defs)

        gradio_client_utils._json_schema_to_python_type = patched_schema_parser
    except Exception:
        pass

    def refresh():
        frame, snapshot = controller.snapshot()
        state_line = (
            f"{snapshot['state']} | step {snapshot['policy_step']}/{snapshot['max_steps']} | "
            f"reward {snapshot['reward']:.3f} | run {snapshot.get('run_id') or '-'}"
        )
        events = snapshot.get("events_tail", [])[-12:]
        event_lines = [
            f"{item.get('step', 0):04d} {item.get('event')} {item.get('payload', {})}" for item in events
        ]
        return (
            frame,
            state_line,
            _json_text(snapshot),
            snapshot.get("task_text", ""),
            snapshot.get("current_prompt", ""),
            _json_text(snapshot.get("raw_action", [])),
            _json_text(snapshot.get("env_action", [])),
            snapshot.get("reward", 0.0),
            snapshot.get("policy_step", 0),
            "\n".join(event_lines),
            snapshot.get("error") or "",
            snapshot.get("annotated_video_path") if snapshot.get("done") else None,
        )

    def on_load(checkpoint: str):
        return controller.request_load(checkpoint or DEFAULT_CHECKPOINT).message

    def on_start(
        task_id,
        trial_id,
        mode,
        max_steps,
        auto_disturbance,
        disturbance_step,
        target_joint,
        dx,
        dy,
        allow_multiple,
        output_dir,
        seed,
    ):
        cfg = MockRunConfig(
            task_id=int(task_id),
            trial_id=int(trial_id),
            mode=str(mode),
            max_steps=int(max_steps),
            enable_auto_disturbance=bool(auto_disturbance),
            disturbance_step=int(disturbance_step),
            target_joint=str(target_joint or "auto"),
            dx=float(dx),
            dy=float(dy),
            allow_multiple_disturbances=bool(allow_multiple),
            output_dir=str(output_dir or DEFAULT_OUT_DIR),
            seed=int(seed),
        )
        return controller.start_episode(cfg).message

    def on_pause():
        return controller.pause().message

    def on_resume():
        return controller.resume().message

    def on_step():
        return controller.step_once().message

    def on_disturb(target_joint, dx, dy):
        return controller.apply_disturbance(target_joint=str(target_joint or "auto"), dx=float(dx), dy=float(dy)).message

    def on_stop():
        return controller.stop().message

    def on_reset():
        return controller.reset().message

    with gr.Blocks(title="LIBERO Mock Dashboard") as demo:
        gr.Markdown("# LIBERO Mock Dashboard")
        status_message = gr.Textbox(label="Command status", interactive=False)
        with gr.Row():
            checkpoint = gr.Textbox(value=DEFAULT_CHECKPOINT, label="Checkpoint")
            load_button = gr.Button("Load Mock Backend")
            reset_button = gr.Button("Reset")

        with gr.Row():
            with gr.Column(scale=1):
                task_id = gr.Number(value=0, precision=0, label="Task")
                trial_id = gr.Number(value=0, precision=0, label="Trial")
                mode = gr.Dropdown(choices=list(MOCK_EXPERIMENT_MODES), value="reactive_disturbed", label="Mode")
                max_steps = gr.Number(value=30, precision=0, label="Max steps")
                auto_disturbance = gr.Checkbox(value=True, label="Auto disturbance")
                disturbance_step = gr.Number(value=5, precision=0, label="Disturbance step")
                target_joint = gr.Textbox(value="auto", label="Target joint")
                dx = gr.Number(value=0.10, label="dx")
                dy = gr.Number(value=0.05, label="dy")
                allow_multiple = gr.Checkbox(value=False, label="Allow multiple disturbances")
                output_dir = gr.Textbox(value=DEFAULT_OUT_DIR, label="Output directory")
                seed = gr.Number(value=7, precision=0, label="Seed")
                with gr.Row():
                    start_button = gr.Button("Start")
                    stop_button = gr.Button("Stop and save")
                with gr.Row():
                    pause_button = gr.Button("Pause")
                    resume_button = gr.Button("Resume")
                    step_button = gr.Button("Step once")
                disturb_button = gr.Button("Disturb now")
            with gr.Column(scale=2):
                image = gr.Image(label="Latest mock camera frame", type="numpy")
                state_text = gr.Textbox(label="State", interactive=False)
                with gr.Row():
                    reward = gr.Number(label="Reward", interactive=False)
                    step = gr.Number(label="Step", interactive=False)
                video = gr.Video(label="Annotated video")
            with gr.Column(scale=2):
                task_text = gr.Textbox(label="Task", interactive=False)
                prompt = gr.Textbox(label="Current prompt", interactive=False, lines=4)
                raw_action = gr.Textbox(label="Raw action JSON", interactive=False, lines=3)
                env_action = gr.Textbox(label="Env action JSON", interactive=False, lines=3)
                snapshot_json = gr.Textbox(label="Snapshot JSON", interactive=False, lines=16)
                events = gr.Textbox(label="Recent events", interactive=False, lines=12)
                error_text = gr.Textbox(label="Error", interactive=False, lines=3)

        timer = gr.Timer(0.5)
        timer.tick(
            refresh,
            outputs=[
                image,
                state_text,
                snapshot_json,
                task_text,
                prompt,
                raw_action,
                env_action,
                reward,
                step,
                events,
                error_text,
                video,
            ],
            queue=False,
        )
        load_button.click(on_load, inputs=[checkpoint], outputs=[status_message], queue=False)
        start_button.click(
            on_start,
            inputs=[
                task_id,
                trial_id,
                mode,
                max_steps,
                auto_disturbance,
                disturbance_step,
                target_joint,
                dx,
                dy,
                allow_multiple,
                output_dir,
                seed,
            ],
            outputs=[status_message],
            queue=False,
        )
        pause_button.click(on_pause, outputs=[status_message], queue=False)
        resume_button.click(on_resume, outputs=[status_message], queue=False)
        step_button.click(on_step, outputs=[status_message], queue=False)
        disturb_button.click(on_disturb, inputs=[target_joint, dx, dy], outputs=[status_message], queue=False)
        stop_button.click(on_stop, outputs=[status_message], queue=False)
        reset_button.click(on_reset, outputs=[status_message], queue=False)
    return demo


def run_mock_smoke(output_dir: str) -> dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    controller = make_controller()
    try:
        load = controller.request_load(DEFAULT_CHECKPOINT)
        if not load.ok:
            raise RuntimeError(load.message)
        wait_for_state(controller, {ControllerState.READY}, timeout=5)

        cfg = MockRunConfig(
            output_dir=str(out_dir),
            max_steps=24,
            success_step=14,
            disturbance_step=4,
            step_delay=0.005,
            mode="structured_relocalize_prompt",
        )
        start = controller.start_episode(cfg)
        if not start.ok:
            raise RuntimeError(start.message)
        _wait_until(lambda s: s["policy_step"] >= 2 and s["state"] == ControllerState.RUNNING.value, controller, 5)
        pause = controller.pause()
        if not pause.ok:
            raise RuntimeError(pause.message)
        paused = wait_for_state(controller, {ControllerState.PAUSED}, timeout=5)
        step_before = int(paused["policy_step"])
        time.sleep(0.08)
        _, still = controller.snapshot()
        if int(still["policy_step"]) != step_before:
            raise AssertionError("Policy step changed while paused.")
        one = controller.step_once()
        if not one.ok:
            raise RuntimeError(one.message)
        _wait_until(
            lambda s: s["state"] == ControllerState.PAUSED.value and int(s["policy_step"]) == step_before + 1,
            controller,
            5,
        )
        disturb = controller.apply_disturbance(target_joint="auto", dx=0.05, dy=-0.03)
        if not disturb.ok:
            raise RuntimeError(disturb.message)
        _wait_until(lambda s: int(s["disturbance_count"]) >= 1, controller, 5)
        resume = controller.resume()
        if not resume.ok:
            raise RuntimeError(resume.message)
        terminal = wait_for_state(controller, {ControllerState.SUCCEEDED, ControllerState.FAILED, ControllerState.ERROR}, timeout=10)
        if terminal["state"] != ControllerState.SUCCEEDED.value:
            raise AssertionError(f"Expected success in smoke episode, got {terminal['state']}: {terminal.get('error')}")

        controller.reset()
        wait_for_state(controller, {ControllerState.READY}, timeout=5)
        stop_cfg = MockRunConfig(output_dir=str(out_dir), max_steps=40, success_step=39, step_delay=0.01)
        controller.start_episode(stop_cfg)
        _wait_until(lambda s: s["state"] == ControllerState.RUNNING.value and int(s["policy_step"]) >= 1, controller, 5)
        stop = controller.stop()
        if not stop.ok:
            raise RuntimeError(stop.message)
        stopped = wait_for_state(controller, {ControllerState.FAILED, ControllerState.ERROR}, timeout=5)
        if stopped["termination_reason"] != "manual_stop":
            raise AssertionError(f"Stop run did not terminate as manual_stop: {stopped['termination_reason']}")

        run_dir = Path(stopped["run_dir"])
        required = ["run_config.json", "events.jsonl", "episode_summary.json", "raw.mp4", "annotated.mp4"]
        missing = [name for name in required if not (run_dir / name).exists()]
        if missing:
            raise AssertionError(f"Missing smoke outputs in {run_dir}: {missing}")
        summary = json.loads((run_dir / "episode_summary.json").read_text())
        events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines() if line.strip()]
        manual_events = {event["event"] for event in events if event["event"].startswith("manual_")}
        if "manual_stop" not in manual_events:
            raise AssertionError("manual_stop event missing from smoke output.")
        return {
            "ok": True,
            "output_dir": str(out_dir),
            "last_run_dir": str(run_dir),
            "last_summary": summary,
            "manual_events": sorted(manual_events),
        }
    finally:
        controller.shutdown()


def _wait_until(predicate, controller: ExperimentController, timeout: float) -> dict[str, Any]:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        _, snapshot = controller.snapshot()
        last = snapshot
        if predicate(snapshot):
            return snapshot
        time.sleep(0.02)
    raise TimeoutError(f"Condition not met; last snapshot={last}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CPU-only mock LIBERO dashboard")
    parser.add_argument("--mock", action="store_true", help="Launch the mock backend dashboard.")
    parser.add_argument("--mock-smoke", action="store_true", help="Run a non-web mock smoke test and exit.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--default-checkpoint", default=DEFAULT_CHECKPOINT)
    parser.add_argument("--default-task-suite", default="libero_spatial")
    parser.add_argument("--default-out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--output-dir", default=None, help="Output directory for --mock-smoke.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mock_smoke:
        result = run_mock_smoke(args.output_dir or args.default_out_dir)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if not args.mock:
        print("Only --mock is implemented in this workflow; real OpenVLA/LIBERO is intentionally not imported.", file=sys.stderr)
        return 2
    controller = make_controller()
    demo = build_dashboard(controller)
    demo.launch(
        server_name=args.host,
        server_port=args.port,
        share=False,
        inbrowser=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
