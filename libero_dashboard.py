"""Gradio entrypoint for the LIBERO/OpenVLA dashboard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

from libero_dashboard_controller import ControllerState, ExperimentController, snapshot_for_json, wait_for_state
from libero_experiment_core import CANONICAL_MODES, ExperimentConfig
from libero_mock_backend import MockBackend, MockRunConfig


DEFAULT_MOCK_CHECKPOINT = "mock://libero-dashboard"
DEFAULT_REAL_CHECKPOINT = "/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial"
DEFAULT_MOCK_OUT_DIR = "/tmp/libero_mock_dashboard"
DEFAULT_REAL_OUT_DIR = "/home/lijingsu/vla/dashboard_outputs/interactive"


def make_controller(*, real: bool = False) -> ExperimentController:
    if real:
        from libero_real_backend import RealExperimentBackend

        return ExperimentController(lambda: RealExperimentBackend())
    return ExperimentController(lambda: MockBackend())


def _json_text(payload: Any) -> str:
    return json.dumps(snapshot_for_json(payload), indent=2, sort_keys=True)


def _as_bool(value: Any) -> bool:
    return bool(value)


def _target_candidate_lines(snapshot: dict[str, Any]) -> str:
    candidates = snapshot.get("target_joint_candidates") or []
    if not candidates:
        return ""
    lines = []
    for item in candidates:
        if not isinstance(item, dict):
            lines.append(str(item))
            continue
        joint = item.get("joint") or item.get("name") or ""
        score = item.get("score")
        reason = item.get("reason") or item.get("score_reason") or ""
        lines.append(f"{joint} | score={score} | {reason}")
    if snapshot.get("target_joint_ambiguous"):
        lines.append("ambiguous=true")
    recommended = snapshot.get("recommended_target_joint")
    if recommended:
        lines.append(f"recommended={recommended}")
    return "\n".join(lines)


def _target_dropdown_update(gr, snapshot: dict[str, Any]):
    choices = []
    for item in snapshot.get("target_joint_candidates") or []:
        if isinstance(item, dict):
            joint = item.get("joint") or item.get("name")
            if joint:
                choices.append(str(joint))
    value = snapshot.get("target_joint") or snapshot.get("recommended_target_joint") or None
    if value and value not in choices:
        choices.append(str(value))
    return gr.update(choices=choices, value=value)


def make_config(
    *,
    real: bool,
    checkpoint: str,
    task_suite: str,
    task_id: Any,
    trial_id: Any,
    mode: str,
    max_steps: Any,
    auto_disturbance: Any,
    disturbance_step: Any,
    target_joint: str,
    dx: Any,
    dy: Any,
    allow_multiple: Any,
    output_dir: str,
    seed: Any,
    resolution: Any,
) -> ExperimentConfig | MockRunConfig:
    if real:
        return ExperimentConfig(
            checkpoint=str(checkpoint or DEFAULT_REAL_CHECKPOINT),
            task_suite=str(task_suite or "libero_spatial"),
            task_id=int(task_id),
            trial_id=int(trial_id),
            mode=str(mode),
            max_steps=int(max_steps),
            disturbance_step=int(disturbance_step),
            target_joint=str(target_joint or "auto"),
            dx=float(dx),
            dy=float(dy),
            seed=int(seed),
            resolution=int(resolution),
            out_dir=str(output_dir or DEFAULT_REAL_OUT_DIR),
            enable_auto_disturbance=_as_bool(auto_disturbance),
            allow_multiple_disturbances=_as_bool(allow_multiple),
        )
    return MockRunConfig(
        task_id=int(task_id),
        trial_id=int(trial_id),
        task_suite=str(task_suite or "libero_spatial"),
        mode=str(mode),
        max_steps=int(max_steps),
        enable_auto_disturbance=_as_bool(auto_disturbance),
        disturbance_step=int(disturbance_step),
        target_joint=str(target_joint or "auto"),
        dx=float(dx),
        dy=float(dy),
        allow_multiple_disturbances=_as_bool(allow_multiple),
        output_dir=str(output_dir or DEFAULT_MOCK_OUT_DIR),
        seed=int(seed),
        frame_size=int(resolution),
    )


def build_dashboard(controller: ExperimentController, *, real: bool = False, defaults: argparse.Namespace | None = None):
    try:
        import gradio as gr
    except Exception as exc:  # pragma: no cover - depends on local environment.
        raise RuntimeError("Gradio is required to launch the browser dashboard.") from exc

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

    default_checkpoint = getattr(defaults, "default_checkpoint", None) or (
        DEFAULT_REAL_CHECKPOINT if real else DEFAULT_MOCK_CHECKPOINT
    )
    default_out_dir = getattr(defaults, "default_out_dir", None) or (DEFAULT_REAL_OUT_DIR if real else DEFAULT_MOCK_OUT_DIR)
    title = "LIBERO / OpenVLA Real Dashboard" if real else "LIBERO Mock Dashboard"

    def cfg_from_inputs(
        checkpoint,
        task_suite,
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
        resolution,
    ):
        return make_config(
            real=real,
            checkpoint=checkpoint,
            task_suite=task_suite,
            task_id=task_id,
            trial_id=trial_id,
            mode=mode,
            max_steps=max_steps,
            auto_disturbance=auto_disturbance,
            disturbance_step=disturbance_step,
            target_joint=target_joint,
            dx=dx,
            dy=dy,
            allow_multiple=allow_multiple,
            output_dir=output_dir,
            seed=seed,
            resolution=resolution,
        )

    def refresh():
        frame, snapshot = controller.snapshot()
        state_line = (
            f"{snapshot['state']} | policy {snapshot['policy_step']}/{snapshot['max_steps']} | "
            f"env {snapshot.get('environment_step', 0)} | reward {snapshot['reward']:.3f} | "
            f"run {snapshot.get('run_id') or '-'}"
        )
        events = snapshot.get("events_tail", [])[-16:]
        event_lines = [
            f"{item.get('policy_step', item.get('step', 0)):04d} {item.get('event')} {item.get('payload', {})}"
            for item in events
        ]
        return (
            frame,
            state_line,
            snapshot.get("task_text", ""),
            snapshot.get("current_prompt", ""),
            snapshot.get("mode") or "",
            int(snapshot.get("policy_step", 0)),
            int(snapshot.get("environment_step", 0)),
            int(snapshot.get("policy_budget_remaining", 0)),
            float(snapshot.get("reward", 0.0)),
            _json_text(snapshot.get("episode_status")),
            snapshot.get("target_joint") or snapshot.get("resolved_target_joint") or "",
            _target_candidate_lines(snapshot),
            _json_text(snapshot.get("target_position")),
            _json_text(snapshot.get("disturbance_state")),
            _json_text(snapshot.get("fresh_observation")),
            _json_text(snapshot.get("latest_action")),
            "\n".join(event_lines),
            snapshot.get("error") or "",
            _json_text(snapshot),
            snapshot.get("annotated_video_path") if snapshot.get("done") else None,
        )

    def on_load(checkpoint, task_suite, task_id, trial_id, mode, max_steps, auto_disturbance, disturbance_step, target_joint, dx, dy, allow_multiple, output_dir, seed, resolution):
        cfg = cfg_from_inputs(
            checkpoint,
            task_suite,
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
            resolution,
        )
        if real:
            return controller.request_load(str(checkpoint or DEFAULT_REAL_CHECKPOINT), config=cfg).message
        return controller.request_load(str(checkpoint or DEFAULT_MOCK_CHECKPOINT)).message

    def on_load_task(*values):
        result = controller.load_task(cfg_from_inputs(*values))
        if not result.ok:
            return result.message, gr.update(), ""
        deadline = time.time() + 240
        last = {}
        while time.time() < deadline:
            _, snapshot = controller.snapshot()
            last = snapshot
            if snapshot.get("state") == ControllerState.ERROR.value:
                return snapshot.get("error") or "Task load failed.", gr.update(), _target_candidate_lines(snapshot)
            if snapshot.get("task_text") and str(snapshot.get("message", "")).startswith("Task loaded."):
                return snapshot.get("message") or "Task loaded.", _target_dropdown_update(gr, snapshot), _target_candidate_lines(snapshot)
            time.sleep(0.2)
        return "Task load queued.", _target_dropdown_update(gr, last), _target_candidate_lines(last)

    def on_start(*values):
        return controller.start_episode(cfg_from_inputs(*values)).message

    def on_pause_resume():
        _, snapshot = controller.snapshot()
        if snapshot["state"] == ControllerState.PAUSED.value:
            return controller.resume().message
        return controller.pause().message

    def on_step():
        return controller.step_once().message

    def on_disturb(target_joint, dx, dy):
        return controller.apply_disturbance(target_joint=str(target_joint or "auto"), dx=float(dx), dy=float(dy)).message

    def on_stop():
        return controller.stop().message

    def on_reset():
        return controller.reset().message

    with gr.Blocks(title=title) as demo:
        gr.Markdown(f"# {title}")
        status_message = gr.Textbox(label="Command status", interactive=False)
        with gr.Row():
            checkpoint = gr.Textbox(value=default_checkpoint, label="Checkpoint")
            load_button = gr.Button("Load model")
            load_task_button = gr.Button("Load task")
            reset_button = gr.Button("Reset")

        with gr.Row():
            with gr.Column(scale=1):
                task_suite = gr.Textbox(value=getattr(defaults, "default_task_suite", "libero_spatial"), label="Task suite")
                task_id = gr.Number(value=0, precision=0, label="Task")
                trial_id = gr.Number(value=0, precision=0, label="Trial")
                mode = gr.Dropdown(choices=list(CANONICAL_MODES), value="reactive_disturbed", label="Mode")
                max_steps = gr.Number(value=12 if not real else 220, precision=0, label="Policy budget")
                auto_disturbance = gr.Checkbox(value=True, label="Auto disturbance")
                disturbance_step = gr.Number(value=4 if not real else 70, precision=0, label="Disturbance step")
                try:
                    target_joint = gr.Dropdown(
                        choices=[],
                        value=None,
                        allow_custom_value=True,
                        interactive=True,
                        label="Target joint",
                    )
                except TypeError:
                    target_joint = gr.Textbox(value="", label="Target joint")
                dx = gr.Number(value=0.10, label="dx")
                dy = gr.Number(value=0.05, label="dy")
                allow_multiple = gr.Checkbox(value=False, label="Allow multiple disturbances")
                output_dir = gr.Textbox(value=default_out_dir, label="Output directory")
                seed = gr.Number(value=7, precision=0, label="Seed")
                resolution = gr.Number(value=256, precision=0, label="Camera resolution")
                config_inputs = [
                    checkpoint,
                    task_suite,
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
                    resolution,
                ]
                with gr.Row():
                    start_button = gr.Button("Start")
                    pause_resume_button = gr.Button("Pause / resume")
                with gr.Row():
                    step_button = gr.Button("Strict single-step")
                    disturb_button = gr.Button("Manual disturbance")
                    stop_button = gr.Button("Safe stop")
            with gr.Column(scale=2):
                image = gr.Image(label="Policy camera", type="numpy")
                state_text = gr.Textbox(label="State", interactive=False)
                with gr.Row():
                    mode_text = gr.Textbox(label="Mode", interactive=False)
                    reward = gr.Number(label="Reward", interactive=False)
                with gr.Row():
                    policy_step = gr.Number(label="Policy step", interactive=False)
                    env_step = gr.Number(label="Environment step", interactive=False)
                    budget_remaining = gr.Number(label="Policy budget remaining", interactive=False)
                task_text = gr.Textbox(label="Task", interactive=False)
                prompt = gr.Textbox(label="Current prompt", interactive=False, lines=4)
                video = gr.Video(label="Annotated video")
            with gr.Column(scale=2):
                episode_status = gr.Textbox(label="Episode status", interactive=False, lines=4)
                target_joint_view = gr.Textbox(label="Target joint", interactive=False)
                target_candidates = gr.Textbox(label="Target candidates", interactive=False, lines=6)
                target_position = gr.Textbox(label="Target position", interactive=False, lines=3)
                disturbance_state = gr.Textbox(label="Disturbance state", interactive=False, lines=4)
                fresh_observation = gr.Textbox(label="Fresh observation", interactive=False, lines=4)
                latest_action = gr.Textbox(label="Latest action", interactive=False, lines=5)
                events = gr.Textbox(label="Event tail", interactive=False, lines=12)
                error_text = gr.Textbox(label="Error", interactive=False, lines=3)
                snapshot_json = gr.Textbox(label="Snapshot JSON", interactive=False, lines=12)

        timer = gr.Timer(0.5)
        timer.tick(
            refresh,
            outputs=[
                image,
                state_text,
                task_text,
                prompt,
                mode_text,
                policy_step,
                env_step,
                budget_remaining,
                reward,
                episode_status,
                target_joint_view,
                target_candidates,
                target_position,
                disturbance_state,
                fresh_observation,
                latest_action,
                events,
                error_text,
                snapshot_json,
                video,
            ],
            queue=False,
        )
        load_button.click(on_load, inputs=config_inputs, outputs=[status_message], queue=False)
        load_task_button.click(on_load_task, inputs=config_inputs, outputs=[status_message, target_joint, target_candidates], queue=False)
        start_button.click(on_start, inputs=config_inputs, outputs=[status_message], queue=False)
        pause_resume_button.click(on_pause_resume, outputs=[status_message], queue=False)
        step_button.click(on_step, outputs=[status_message], queue=False)
        disturb_button.click(on_disturb, inputs=[target_joint, dx, dy], outputs=[status_message], queue=False)
        stop_button.click(on_stop, outputs=[status_message], queue=False)
        reset_button.click(on_reset, outputs=[status_message], queue=False)
    return demo


def run_mock_smoke(output_dir: str) -> dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    controller = make_controller(real=False)
    try:
        load = controller.request_load(DEFAULT_MOCK_CHECKPOINT)
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
    parser = argparse.ArgumentParser(description="LIBERO/OpenVLA dashboard")
    backend = parser.add_mutually_exclusive_group()
    backend.add_argument("--mock", action="store_true", help="Launch the mock backend dashboard.")
    backend.add_argument("--real", action="store_true", help="Launch the real LIBERO/OpenVLA dashboard.")
    parser.add_argument("--mock-smoke", action="store_true", help="Run a non-web mock smoke test and exit.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--default-checkpoint", default=None)
    parser.add_argument("--default-task-suite", default="libero_spatial")
    parser.add_argument("--default-out-dir", default=None)
    parser.add_argument("--output-dir", default=None, help="Output directory for --mock-smoke.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mock_smoke:
        result = run_mock_smoke(args.output_dir or args.default_out_dir or DEFAULT_MOCK_OUT_DIR)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.host == "0.0.0.0":
        print("Refusing to bind the dashboard to 0.0.0.0; use 127.0.0.1 and SSH forwarding.", file=sys.stderr)
        return 2
    real = bool(args.real)
    if not real and not args.mock:
        print("Choose --mock or --real.", file=sys.stderr)
        return 2
    controller = make_controller(real=real)
    demo = build_dashboard(controller, real=real, defaults=args)
    demo.launch(
        server_name=args.host,
        server_port=args.port,
        share=False,
        inbrowser=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
