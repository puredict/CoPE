from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from libero_dashboard_controller import CANONICAL_MODES, ControllerState, ExperimentConfig, ExperimentController, MockBackend, RealLiberoBackend


DEFAULT_CHECKPOINT = "/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial"
DEFAULT_OUT_DIR = "/home/lijingsu/vla/dashboard_outputs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--default-checkpoint", default=DEFAULT_CHECKPOINT)
    parser.add_argument("--default-task-suite", default="libero_spatial")
    parser.add_argument("--default-out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--smoke-test", action="store_true", help="Run one mock episode and exit without importing Gradio.")
    return parser.parse_args()


def configure_runtime_env() -> None:
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("MUJOCO_GL", "egl")
    os.environ.setdefault("PYOPENGL_PLATFORM", "egl")


def make_config(
    checkpoint: str,
    task_suite: str,
    unnorm_key: str,
    task_id: int,
    trial_id: int,
    mode: str,
    max_steps: int,
    num_steps_wait: int,
    enable_auto_disturbance: bool,
    disturbance_step: int,
    target_joint: str,
    dx: float,
    dy: float,
    allow_multiple_disturbances: bool,
    out_dir: str,
    seed: int,
) -> ExperimentConfig:
    return ExperimentConfig(
        checkpoint=checkpoint,
        task_suite=task_suite,
        unnorm_key=unnorm_key.strip() or None,
        task_id=int(task_id),
        trial_id=int(trial_id),
        mode=mode,
        max_steps=int(max_steps),
        num_steps_wait=int(num_steps_wait),
        disturbance_step=int(disturbance_step),
        target_joint=(target_joint or "auto").strip() or "auto",
        dx=float(dx),
        dy=float(dy),
        seed=int(seed),
        out_dir=out_dir,
        enable_auto_disturbance=bool(enable_auto_disturbance),
        allow_multiple_disturbances=bool(allow_multiple_disturbances),
    )


def build_ui(controller: ExperimentController, args: argparse.Namespace) -> Any:
    import gradio as gr
    import gradio_client.utils as gradio_client_utils

    if not getattr(gradio_client_utils, "_libero_bool_schema_patch", False):
        original_schema_to_type = gradio_client_utils._json_schema_to_python_type

        def schema_to_type_with_bool(schema, defs=None):
            if isinstance(schema, bool):
                return "Any" if schema else "None"
            return original_schema_to_type(schema, defs)

        gradio_client_utils._json_schema_to_python_type = schema_to_type_with_bool
        gradio_client_utils._libero_bool_schema_patch = True

    def cfg_from_inputs(*values):
        return make_config(*values)

    def load_model(checkpoint, task_suite, unnorm_key):
        return controller.request_model_load(checkpoint, task_suite, unnorm_key.strip() or None)

    def unload_model():
        return controller.request_unload_model()

    def inspect_task(*values):
        return controller.request_task_inspect(cfg_from_inputs(*values))

    def start_episode(*values):
        return controller.request_start(cfg_from_inputs(*values))

    def pause_toggle():
        return controller.request_pause_toggle()

    def step_once():
        return controller.request_step_once()

    def disturb(target_joint, dx, dy):
        return controller.request_manual_disturbance(target_joint, dx, dy)

    def stop():
        return controller.request_stop()

    def clear():
        return controller.clear_completed_state()

    def refresh():
        frame, snap = controller.snapshot()
        state = snap["controller_state"]
        active = state in {
            ControllerState.STARTING.value,
            ControllerState.STABILIZING.value,
            ControllerState.RUNNING.value,
            ControllerState.PAUSED.value,
            ControllerState.STOPPING.value,
        }
        loaded = bool(snap["model_loaded"])
        can_load = not loaded and state != ControllerState.LOADING_MODEL.value and not active
        can_unload = loaded and not active and state != ControllerState.LOADING_MODEL.value
        can_start = loaded and not active and state not in {ControllerState.LOADING_MODEL.value, ControllerState.INSPECTING_TASK.value}
        can_inspect = loaded and not active
        can_control = state in {ControllerState.RUNNING.value, ControllerState.PAUSED.value, ControllerState.STABILIZING.value}
        can_clear = not active and state in {ControllerState.COMPLETED.value, ControllerState.ABORTED.value, ControllerState.FAILED.value}

        status = f"## {state.upper()}\n{snap.get('message') or ''}"
        metrics = (
            f"step {snap['total_policy_steps']} / {snap['max_steps']} | "
            f"phase {snap['phase_policy_step']} | reward {snap['reward']:.3f} | "
            f"elapsed {snap['elapsed_seconds']:.1f}s | "
            f"infer {snap['inference_seconds'] or 0:.3f}s | env {snap['env_step_seconds'] or 0:.3f}s"
        )
        model_status = (
            f"loaded={loaded}\n"
            f"checkpoint={snap.get('checkpoint')}\n"
            f"unnorm_key={snap.get('resolved_unnorm_key')}\n"
            f"device={snap.get('device')}"
        )
        task_info = (
            f"task: {snap.get('task_description') or ''}\n"
            f"trials: {snap.get('trial_count')}\n"
            f"target: {snap.get('resolved_target_joint')}\n"
            f"free joints: {', '.join(j['name'] for j in snap.get('available_target_joints') or [])}"
        )
        events = [
            [
                row.get("timestamp"),
                row.get("event"),
                row.get("policy_step"),
                json.dumps(row.get("payload", {}), ensure_ascii=True)[:500],
            ]
            for row in (snap.get("last_events") or [])[-50:]
        ]
        error = ""
        if snap.get("error"):
            error = f"{snap['error']}\n\n{snap.get('traceback_tail') or ''}"
        video_path = snap.get("annotated_video_path") if state in {ControllerState.COMPLETED.value, ControllerState.ABORTED.value, ControllerState.FAILED.value} else None
        return (
            frame,
            status,
            metrics,
            video_path,
            model_status,
            json.dumps(snap.get("device_info") or {}, indent=2, ensure_ascii=True),
            task_info,
            snap.get("original_prompt") or "",
            snap.get("current_prompt") or "",
            json.dumps(snap.get("raw_action") or {}, indent=2, ensure_ascii=True),
            json.dumps(snap.get("env_action") or {}, indent=2, ensure_ascii=True),
            json.dumps(snap.get("last_disturbance") or {}, indent=2, ensure_ascii=True),
            json.dumps(snap.get("recovery_state") or {}, indent=2, ensure_ascii=True),
            events,
            error,
            gr.update(interactive=can_load),
            gr.update(interactive=can_unload),
            gr.update(interactive=can_inspect),
            gr.update(interactive=can_start),
            gr.update(interactive=can_control, value="继续" if snap.get("paused") else "暂停"),
            gr.update(interactive=can_control),
            gr.update(interactive=can_control),
            gr.update(interactive=can_control),
            gr.update(interactive=can_clear),
        )

    with gr.Blocks(title="LIBERO / OpenVLA Dashboard") as demo:
        gr.Markdown("# LIBERO / OpenVLA Dashboard")
        with gr.Row():
            with gr.Column(scale=2):
                checkpoint = gr.Textbox(label="Checkpoint", value=args.default_checkpoint)
                task_suite = gr.Textbox(label="Task suite", value=args.default_task_suite)
                unnorm_key = gr.Textbox(label="Unnorm key", value="")
            with gr.Column(scale=1):
                load_btn = gr.Button("加载模型", variant="primary")
                unload_btn = gr.Button("卸载模型")
                model_status = gr.Textbox(label="Model status", lines=4, interactive=False)
                device_json = gr.Textbox(label="CUDA / memory", lines=6, interactive=False)

        with gr.Row():
            with gr.Column(scale=1):
                task_id = gr.Number(label="Task ID", value=0, precision=0)
                trial_id = gr.Number(label="Trial ID", value=0, precision=0)
                mode = gr.Dropdown(label="Mode", choices=list(CANONICAL_MODES), value="reactive_disturbed")
                max_steps = gr.Number(label="Max steps", value=220, precision=0)
                num_steps_wait = gr.Number(label="Stabilization steps", value=10, precision=0)
                enable_auto = gr.Checkbox(label="Automatic disturbance", value=True)
                disturbance_step = gr.Number(label="Disturbance step", value=70, precision=0)
                target_joint = gr.Textbox(label="Target joint", value="auto")
                dx = gr.Number(label="dx", value=0.10)
                dy = gr.Number(label="dy", value=0.05)
                allow_multiple = gr.Checkbox(label="Allow multiple disturbances", value=False)
                out_dir = gr.Textbox(label="Output directory", value=args.default_out_dir)
                seed = gr.Number(label="Seed", value=7, precision=0)
                inspect_btn = gr.Button("检查任务")
                task_info = gr.Textbox(label="Task inspection", lines=6, interactive=False)

            with gr.Column(scale=2):
                image = gr.Image(label="Live frame", type="numpy", height=512)
                state_md = gr.Markdown("## IDLE")
                metrics_md = gr.Markdown("step 0 / 0")
                video = gr.Video(label="Annotated video")

            with gr.Column(scale=1):
                original_prompt = gr.Textbox(label="Original prompt", lines=3, interactive=False)
                current_prompt = gr.Textbox(label="Current prompt", lines=3, interactive=False)
                raw_action = gr.Textbox(label="Raw action JSON", lines=4, interactive=False)
                env_action = gr.Textbox(label="Env action JSON", lines=4, interactive=False)
                last_disturbance = gr.Textbox(label="Last disturbance JSON", lines=6, interactive=False)
                recovery = gr.Textbox(label="Recovery state JSON", lines=6, interactive=False)
                events = gr.Dataframe(headers=["timestamp", "event", "step", "payload"], datatype=["str", "str", "number", "str"], label="Recent events")
                error_box = gr.Textbox(label="Error / traceback", lines=6, interactive=False)

        with gr.Row():
            start_btn = gr.Button("开始实验", variant="primary")
            pause_btn = gr.Button("暂停")
            step_btn = gr.Button("执行一步")
            disturb_btn = gr.Button("立即扰动")
            stop_btn = gr.Button("停止并保存", variant="stop")
            clear_btn = gr.Button("清空已完成状态")

        cfg_inputs = [
            checkpoint,
            task_suite,
            unnorm_key,
            task_id,
            trial_id,
            mode,
            max_steps,
            num_steps_wait,
            enable_auto,
            disturbance_step,
            target_joint,
            dx,
            dy,
            allow_multiple,
            out_dir,
            seed,
        ]
        status_output = gr.Textbox(label="Last command", interactive=False)
        load_btn.click(load_model, inputs=[checkpoint, task_suite, unnorm_key], outputs=[status_output], queue=False)
        unload_btn.click(unload_model, outputs=[status_output], queue=False)
        inspect_btn.click(inspect_task, inputs=cfg_inputs, outputs=[status_output], queue=False)
        start_btn.click(start_episode, inputs=cfg_inputs, outputs=[status_output], queue=False)
        pause_btn.click(pause_toggle, outputs=[status_output], queue=False)
        step_btn.click(step_once, outputs=[status_output], queue=False)
        disturb_btn.click(disturb, inputs=[target_joint, dx, dy], outputs=[status_output], queue=False)
        stop_btn.click(stop, outputs=[status_output], queue=False)
        clear_btn.click(clear, outputs=[status_output], queue=False)

        timer = gr.Timer(value=0.25)
        timer.tick(
            refresh,
            outputs=[
                image,
                state_md,
                metrics_md,
                video,
                model_status,
                device_json,
                task_info,
                original_prompt,
                current_prompt,
                raw_action,
                env_action,
                last_disturbance,
                recovery,
                events,
                error_box,
                load_btn,
                unload_btn,
                inspect_btn,
                start_btn,
                pause_btn,
                step_btn,
                disturb_btn,
                stop_btn,
                clear_btn,
            ],
            queue=False,
        )
    return demo


def run_smoke_test(args: argparse.Namespace) -> None:
    out_dir = Path(args.default_out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    controller = ExperimentController(MockBackend(load_delay=0.6, step_delay=0.01))
    try:
        print(controller.request_model_load(args.default_checkpoint, args.default_task_suite, None), flush=True)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            _, snap = controller.snapshot()
            if snap["controller_state"] == ControllerState.READY.value:
                break
            time.sleep(0.05)
        cfg = ExperimentConfig(
            checkpoint=args.default_checkpoint,
            task_suite=args.default_task_suite,
            max_steps=3,
            num_steps_wait=1,
            disturbance_step=1,
            out_dir=str(out_dir),
            mode="reactive_disturbed",
        )
        print(controller.request_start(cfg), flush=True)
        if not controller.wait_for_idle(timeout=10):
            raise TimeoutError("mock smoke episode did not finish")
        _, snap = controller.snapshot()
        print(json.dumps({"state": snap["controller_state"], "steps": snap["total_policy_steps"], "episode": snap["episode_json_path"]}, indent=2), flush=True)
        if snap["controller_state"] != ControllerState.COMPLETED.value:
            raise RuntimeError(f"unexpected smoke-test state {snap['controller_state']}")
    finally:
        controller.shutdown()


def main() -> None:
    args = parse_args()
    configure_runtime_env()
    if args.smoke_test:
        run_smoke_test(args)
        return
    backend = MockBackend() if args.mock else RealLiberoBackend()
    controller = ExperimentController(backend)
    demo = build_ui(controller, args)
    demo.launch(
        server_name=args.host,
        server_port=args.port,
        share=False,
        inbrowser=False,
    )


if __name__ == "__main__":
    main()
