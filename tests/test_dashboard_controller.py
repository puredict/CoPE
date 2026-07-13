import json
from pathlib import Path
import time

import pytest

from libero_dashboard_controller import ControllerState, ExperimentController, wait_for_state
from libero_mock_backend import MockBackend, MockRunConfig


def controller():
    return ExperimentController(lambda: MockBackend(load_delay=0.0))


def wait_until(ctrl, predicate, timeout=5.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        _, snap = ctrl.snapshot()
        last = snap
        if predicate(snap):
            return snap
        time.sleep(0.02)
    raise AssertionError(f"condition timed out; last snapshot={last}")


def load_ready(ctrl):
    result = ctrl.request_load("mock://test")
    assert result.ok, result.message
    return wait_for_state(ctrl, {ControllerState.READY}, timeout=5)


def terminal(ctrl, timeout=8):
    return wait_for_state(ctrl, {ControllerState.SUCCEEDED, ControllerState.FAILED, ControllerState.ERROR}, timeout=timeout)


def test_illegal_start_before_load_and_reset():
    ctrl = controller()
    try:
        result = ctrl.start_episode(MockRunConfig())
        assert not result.ok
        assert "IDLE" in result.message
        reset = ctrl.reset()
        assert not reset.ok
    finally:
        ctrl.shutdown()


def test_load_and_reject_duplicate_start(tmp_path):
    ctrl = controller()
    try:
        load_ready(ctrl)
        first = ctrl.start_episode(
            MockRunConfig(output_dir=str(tmp_path), max_steps=20, success_step=18, step_delay=0.01)
        )
        assert first.ok
        second = ctrl.start_episode(MockRunConfig(output_dir=str(tmp_path)))
        assert not second.ok
        assert "RUNNING" in second.message
        stop = ctrl.stop()
        assert stop.ok
        snap = terminal(ctrl)
        assert snap["termination_reason"] == "manual_stop"
    finally:
        ctrl.shutdown()


def test_pause_resume_and_no_growth_while_paused(tmp_path):
    ctrl = controller()
    try:
        load_ready(ctrl)
        ctrl.start_episode(MockRunConfig(output_dir=str(tmp_path), max_steps=40, success_step=35, step_delay=0.01))
        wait_until(ctrl, lambda s: s["policy_step"] >= 2 and s["state"] == "RUNNING")
        assert ctrl.pause().ok
        paused = wait_for_state(ctrl, {ControllerState.PAUSED}, timeout=5)
        step_at_pause = paused["policy_step"]
        time.sleep(0.08)
        _, still = ctrl.snapshot()
        assert still["policy_step"] == step_at_pause
        assert ctrl.resume().ok
        wait_until(ctrl, lambda s: s["policy_step"] > step_at_pause and s["state"] == "RUNNING")
        assert ctrl.stop().ok
        terminal(ctrl)
    finally:
        ctrl.shutdown()


def test_strict_single_step_returns_to_paused(tmp_path):
    ctrl = controller()
    try:
        load_ready(ctrl)
        ctrl.start_episode(MockRunConfig(output_dir=str(tmp_path), max_steps=40, success_step=35, step_delay=0.01))
        wait_until(ctrl, lambda s: s["policy_step"] >= 2 and s["state"] == "RUNNING")
        ctrl.pause()
        paused = wait_for_state(ctrl, {ControllerState.PAUSED}, timeout=5)
        before = paused["policy_step"]
        assert ctrl.step_once().ok
        after = wait_until(
            ctrl,
            lambda s: s["state"] == "PAUSED" and s["policy_step"] == before + 1,
        )
        time.sleep(0.08)
        _, still = ctrl.snapshot()
        assert after["policy_step"] == before + 1
        assert still["policy_step"] == before + 1
        ctrl.stop()
        terminal(ctrl)
    finally:
        ctrl.shutdown()


def test_auto_disturbance_only_once(tmp_path):
    ctrl = controller()
    try:
        load_ready(ctrl)
        ctrl.start_episode(
            MockRunConfig(
                output_dir=str(tmp_path),
                max_steps=16,
                success_step=10,
                disturbance_step=2,
                step_delay=0.005,
                mode="reactive_disturbed",
            )
        )
        snap = terminal(ctrl)
        assert snap["state"] == "SUCCEEDED"
        assert snap["disturbance_count"] == 1
        events = [event for event in snap["events_tail"] if event["event"] == "disturbance_applied"]
        assert len(events) == 1
        assert events[0]["payload"]["source"] == "auto"
    finally:
        ctrl.shutdown()


def test_manual_disturbance_command_applies_once(tmp_path):
    ctrl = controller()
    try:
        load_ready(ctrl)
        ctrl.start_episode(
            MockRunConfig(
                output_dir=str(tmp_path),
                max_steps=40,
                success_step=35,
                enable_auto_disturbance=False,
                step_delay=0.01,
            )
        )
        wait_until(ctrl, lambda s: s["policy_step"] >= 1)
        ctrl.pause()
        wait_for_state(ctrl, {ControllerState.PAUSED}, timeout=5)
        assert ctrl.apply_disturbance(target_joint="auto", dx=0.03, dy=0.04).ok
        disturbed = wait_until(ctrl, lambda s: s["disturbance_count"] == 1)
        time.sleep(0.08)
        _, still = ctrl.snapshot()
        assert still["disturbance_count"] == 1
        names = {event["event"] for event in disturbed["events_tail"]}
        assert "manual_disturbance" in names
        assert disturbed["manual_intervention"] is True
        ctrl.stop()
        terminal(ctrl)
    finally:
        ctrl.shutdown()


def test_stop_saves_required_outputs(tmp_path):
    ctrl = controller()
    try:
        load_ready(ctrl)
        ctrl.start_episode(MockRunConfig(output_dir=str(tmp_path), max_steps=50, success_step=45, step_delay=0.01))
        wait_until(ctrl, lambda s: s["policy_step"] >= 2)
        assert ctrl.stop().ok
        snap = terminal(ctrl)
        run_dir = Path(snap["run_dir"])
        for name in ["run_config.json", "events.jsonl", "episode_summary.json", "raw.mp4", "annotated.mp4"]:
            path = run_dir / name
            assert path.exists(), name
            assert path.stat().st_size > 0, name
        summary = json.loads((run_dir / "episode_summary.json").read_text())
        assert summary["termination_reason"] == "manual_stop"
        assert summary["manual_intervention"] is True
        assert summary["interactive"] is True
        assert summary["formal_run"] is False
        events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines() if line.strip()]
        assert any(event["event"] == "manual_stop" for event in events)
        assert all("timestamp" in event and "step" in event and "event" in event for event in events)
    finally:
        ctrl.shutdown()


def test_worker_exception_enters_error_and_keeps_traceback(tmp_path):
    ctrl = controller()
    try:
        load_ready(ctrl)
        ctrl.start_episode(
            MockRunConfig(
                output_dir=str(tmp_path),
                max_steps=20,
                mock_outcome="exception",
                exception_step=1,
                step_delay=0.005,
            )
        )
        snap = wait_for_state(ctrl, {ControllerState.ERROR}, timeout=5)
        assert "Mock worker exception" in snap["error"]
        assert "RuntimeError" in snap["traceback_tail"]
        run_dir = Path(snap["run_dir"])
        assert (run_dir / "episode_summary.json").exists()
    finally:
        ctrl.shutdown()


def test_snapshot_frame_is_copied(tmp_path):
    ctrl = controller()
    try:
        load_ready(ctrl)
        ctrl.start_episode(MockRunConfig(output_dir=str(tmp_path), max_steps=12, success_step=8, step_delay=0.005))
        wait_until(ctrl, lambda s: s["latest_frame_shape"] is not None)
        frame, snap = ctrl.snapshot(include_frame=True)
        assert frame is not None
        assert snap["latest_frame"] is not None
        frame[0, 0, :] = 0
        snap["latest_frame"][0, 1, :] = 0
        frame2, snap2 = ctrl.snapshot(include_frame=True)
        assert frame2 is not None
        assert frame2[0, 0, :].sum() != 0
        assert snap2["latest_frame"][0, 1, :].sum() != 0
        terminal(ctrl)
    finally:
        ctrl.shutdown()
