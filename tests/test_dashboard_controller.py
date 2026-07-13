from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from libero_dashboard_controller import ControllerState, ExperimentConfig, ExperimentController, MockBackend


def make_cfg(tmp_path: Path, **overrides) -> ExperimentConfig:
    data = {
        "checkpoint": "mock-checkpoint",
        "task_suite": "libero_spatial",
        "task_id": 0,
        "trial_id": 0,
        "mode": "reactive_disturbed",
        "max_steps": 5,
        "num_steps_wait": 0,
        "disturbance_step": 1,
        "target_joint": "auto",
        "out_dir": str(tmp_path),
    }
    data.update(overrides)
    return ExperimentConfig(**data)


def wait_for(controller: ExperimentController, predicate, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        _, snap = controller.snapshot()
        last = snap
        if predicate(snap):
            return snap
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting; last snapshot={last}")


def loaded_controller() -> ExperimentController:
    controller = ExperimentController(MockBackend(load_delay=0.01, step_delay=0.01))
    assert "submitted" in controller.request_model_load("mock-checkpoint").lower()
    wait_for(controller, lambda s: s["controller_state"] == ControllerState.READY.value)
    return controller


def test_rejects_start_without_model(tmp_path: Path) -> None:
    controller = ExperimentController(MockBackend(load_delay=0.01, step_delay=0.01))
    try:
        msg = controller.request_start(make_cfg(tmp_path))
        assert "load a model" in msg.lower()
        _, snap = controller.snapshot()
        assert snap["controller_state"] == ControllerState.IDLE.value
    finally:
        controller.shutdown()


def test_mock_model_load_reaches_ready() -> None:
    controller = ExperimentController(MockBackend(load_delay=0.01, step_delay=0.01))
    try:
        assert "submitted" in controller.request_model_load("mock-checkpoint").lower()
        snap = wait_for(controller, lambda s: s["controller_state"] == ControllerState.READY.value)
        assert snap["model_loaded"] is True
        assert snap["resolved_unnorm_key"] == "libero_spatial"
    finally:
        controller.shutdown()


def test_start_enters_running(tmp_path: Path) -> None:
    controller = loaded_controller()
    try:
        assert "submitted" in controller.request_start(make_cfg(tmp_path, max_steps=10)).lower()
        snap = wait_for(controller, lambda s: s["controller_state"] in {ControllerState.RUNNING.value, ControllerState.PAUSED.value})
        assert snap["task_description"] == "put the black bowl on the plate"
    finally:
        controller.request_stop()
        controller.wait_for_idle(timeout=3)
        controller.shutdown()


def test_pause_at_safe_boundary(tmp_path: Path) -> None:
    controller = loaded_controller()
    try:
        controller.request_start(make_cfg(tmp_path, max_steps=20, disturbance_step=100))
        wait_for(controller, lambda s: s["total_policy_steps"] >= 1)
        assert "pause" in controller.request_pause_toggle().lower()
        snap = wait_for(controller, lambda s: s["controller_state"] == ControllerState.PAUSED.value)
        assert snap["paused"] is True
        paused_step = snap["total_policy_steps"]
        time.sleep(0.05)
        _, later = controller.snapshot()
        assert later["total_policy_steps"] == paused_step
    finally:
        controller.request_stop()
        controller.wait_for_idle(timeout=3)
        controller.shutdown()


def test_step_once_adds_one_step_and_repauses(tmp_path: Path) -> None:
    controller = loaded_controller()
    try:
        controller.request_start(make_cfg(tmp_path, max_steps=20, disturbance_step=100))
        wait_for(controller, lambda s: s["total_policy_steps"] >= 1)
        controller.request_pause_toggle()
        paused = wait_for(controller, lambda s: s["controller_state"] == ControllerState.PAUSED.value)
        before = paused["total_policy_steps"]
        controller.request_step_once()
        after = wait_for(
            controller,
            lambda s: s["total_policy_steps"] == before + 1 and s["controller_state"] == ControllerState.PAUSED.value,
        )
        assert after["total_policy_steps"] == before + 1
    finally:
        controller.request_stop()
        controller.wait_for_idle(timeout=3)
        controller.shutdown()


def test_manual_disturbance_applies_once_when_multiple_disabled(tmp_path: Path) -> None:
    controller = loaded_controller()
    try:
        controller.request_start(make_cfg(tmp_path, max_steps=20, disturbance_step=100, allow_multiple_disturbances=False))
        wait_for(controller, lambda s: s["total_policy_steps"] >= 1)
        controller.request_pause_toggle()
        wait_for(controller, lambda s: s["controller_state"] == ControllerState.PAUSED.value)
        controller.request_manual_disturbance("auto", 0.2, 0.0)
        snap = wait_for(controller, lambda s: s["disturbance_count"] == 1)
        assert snap["last_disturbance"]["source"] == "manual_ui"
        controller.request_manual_disturbance("auto", 0.3, 0.0)
        time.sleep(0.08)
        _, later = controller.snapshot()
        assert later["disturbance_count"] == 1
    finally:
        controller.request_stop()
        controller.wait_for_idle(timeout=3)
        controller.shutdown()


def test_auto_disturbance_does_not_repeat_when_multiple_disabled(tmp_path: Path) -> None:
    controller = loaded_controller()
    try:
        controller.request_start(make_cfg(tmp_path, max_steps=4, disturbance_step=0, allow_multiple_disturbances=False))
        snap = wait_for(controller, lambda s: s["controller_state"] == ControllerState.COMPLETED.value, timeout=5)
        assert snap["disturbance_count"] == 1
        assert snap["last_disturbance"]["source"] == "auto_config"
    finally:
        controller.shutdown()


def test_stop_aborts_worker(tmp_path: Path) -> None:
    controller = loaded_controller()
    try:
        controller.request_start(make_cfg(tmp_path, max_steps=50, disturbance_step=100))
        wait_for(controller, lambda s: s["total_policy_steps"] >= 1)
        controller.request_stop()
        snap = wait_for(controller, lambda s: s["controller_state"] == ControllerState.ABORTED.value, timeout=5)
        assert snap["stop_requested"] is False
    finally:
        controller.shutdown()


def test_mock_completion_reaches_completed(tmp_path: Path) -> None:
    controller = loaded_controller()
    try:
        controller.request_start(make_cfg(tmp_path, max_steps=2, disturbance_step=100))
        snap = wait_for(controller, lambda s: s["controller_state"] == ControllerState.COMPLETED.value, timeout=5)
        assert snap["success"] is True
        assert snap["total_policy_steps"] == 2
    finally:
        controller.shutdown()


def test_worker_exception_enters_failed(tmp_path: Path) -> None:
    controller = ExperimentController(MockBackend(load_delay=0.01, step_delay=0.01, fail_on_step=1))
    try:
        controller.request_model_load("mock-checkpoint")
        wait_for(controller, lambda s: s["controller_state"] == ControllerState.READY.value)
        controller.request_start(make_cfg(tmp_path, max_steps=5, disturbance_step=100))
        snap = wait_for(controller, lambda s: s["controller_state"] == ControllerState.FAILED.value, timeout=5)
        assert "mock failure" in snap["error"]
        assert snap["traceback_tail"]
    finally:
        controller.shutdown()


def test_snapshot_is_json_serializable(tmp_path: Path) -> None:
    controller = loaded_controller()
    try:
        controller.request_start(make_cfg(tmp_path, max_steps=1, disturbance_step=100))
        snap = wait_for(controller, lambda s: s["controller_state"] == ControllerState.COMPLETED.value, timeout=5)
        json.dumps(snap)
    finally:
        controller.shutdown()


def test_episode_output_marks_human_intervention(tmp_path: Path) -> None:
    controller = loaded_controller()
    try:
        controller.request_start(make_cfg(tmp_path, max_steps=4, disturbance_step=100))
        wait_for(controller, lambda s: s["total_policy_steps"] >= 1)
        controller.request_manual_disturbance("auto", 0.1, 0.0)
        snap = wait_for(controller, lambda s: s["controller_state"] == ControllerState.COMPLETED.value, timeout=5)
        episode_path = Path(snap["episode_json_path"])
        payload = json.loads(episode_path.read_text(encoding="utf-8"))
        assert payload["human_intervention"] is True
        assert payload["eligible_for_official_metrics"] is False
    finally:
        controller.shutdown()
