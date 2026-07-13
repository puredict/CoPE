from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import SimpleNamespace
import time

import numpy as np

from libero_dashboard_controller import ControllerState, ExperimentController, wait_for_state


@dataclass(frozen=True)
class FakeRealConfig:
    checkpoint: str = "fake://openvla"
    task_suite: str = "libero_spatial"
    task_id: int = 0
    trial_id: int = 0
    mode: str = "reactive_disturbed"
    max_steps: int = 12
    disturbance_step: int = 99
    target_joint: str = "auto"
    dx: float = 0.1
    dy: float = 0.05
    seed: int = 7
    out_dir: str = "/tmp/fake_real_dashboard"
    enable_auto_disturbance: bool = False
    allow_multiple_disturbances: bool = False


class FakeRealBackend:
    backend_name = "fake_real"

    def __init__(self) -> None:
        self.loaded = False
        self.policy_step = 0
        self.environment_step = 0
        self.reward = 0.0
        self.disturbance_count = 0
        self.current_prompt = "move the fake object"
        self.original_prompt = self.current_prompt
        self.task_text = self.current_prompt
        self.resolved_target_joint = "fake_object_joint0"
        self.last_disturbance = None
        self.latest_frame = self._frame(0)
        self.stopped = False

    @property
    def object_position(self):
        return [0.1 + self.disturbance_count * 0.1, 0.2, 0.0]

    def load(self, config):
        self.loaded = True
        return {
            "checkpoint": getattr(config, "checkpoint", "fake://openvla"),
            "resolved_unnorm_key": "fake_no_noops",
            "device": "cpu",
            "backend": self.backend_name,
        }

    def inspect_task(self, config):
        return {
            "task_text": self.task_text,
            "available_trials": 1,
            "available_target_joints": [self.resolved_target_joint],
            "resolved_target_joint": self.resolved_target_joint,
            "target_position": self.object_position,
            "preview_frame": self.latest_frame,
        }

    def start_episode(self, config):
        self.policy_step = 0
        self.environment_step = 0
        self.disturbance_count = 0
        self.current_prompt = self.original_prompt
        self.last_disturbance = None
        self.latest_frame = self._frame(0)
        return {
            "task_text": self.task_text,
            "original_prompt": self.original_prompt,
            "current_prompt": self.current_prompt,
            "resolved_target_joint": self.resolved_target_joint,
            "available_target_joints": [self.resolved_target_joint],
            "target_selection": {"selected_joint": self.resolved_target_joint},
            "target_position": self.object_position,
            "frame": self.latest_frame,
        }

    def should_auto_disturb(self, config, policy_step):
        return False

    def apply_disturbance(self, config, *, policy_step, source, target_joint=None, dx=None, dy=None):
        self.disturbance_count += 1
        self.current_prompt = "relocalize the fake object, then move the fake object"
        self.last_disturbance = {
            "applied": True,
            "source": source,
            "policy_step": policy_step,
            "joint": self.resolved_target_joint,
            "requested_target_joint": target_joint or "auto",
            "dx": dx,
            "dy": dy,
            "prompt_changed": True,
            "refresh": {"method": "fake.force_update", "consumed_noop_env_step": False},
        }
        self.latest_frame = self._frame(self.policy_step + 10)
        return dict(self.last_disturbance)

    def step(self, config, *, policy_step, paused=False):
        time.sleep(0.005)
        self.policy_step = policy_step + 1
        self.environment_step += 1
        self.reward = min(1.0, self.policy_step / 10)
        done = False
        success = False
        self.latest_frame = self._frame(self.policy_step)
        return SimpleNamespace(
            policy_step=self.policy_step,
            environment_step=self.environment_step,
            raw_frame=self.latest_frame,
            annotated_frame=self.latest_frame,
            raw_action=[0.1, 0.2, 0.3],
            env_action=[0.1, 0.2, 0.3],
            reward=self.reward,
            done=done,
            success=success,
            termination_reason=None,
            current_prompt=self.current_prompt,
            object_position=self.object_position,
            inference_seconds=0.0,
            env_step_seconds=0.0,
            info={},
            episode_status={"status": "success" if success else "failure", "success": success},
        )

    def get_snapshot(self):
        return {
            "backend": self.backend_name,
            "model_loaded": self.loaded,
            "task_text": self.task_text,
            "current_prompt": self.current_prompt,
            "original_prompt": self.original_prompt,
            "target_joint": self.resolved_target_joint,
            "target_position": self.object_position,
            "disturbance_count": self.disturbance_count,
            "last_disturbance": self.last_disturbance,
            "fresh_observation": {"method": "fake.force_update"} if self.disturbance_count else None,
            "latest_action": {"raw_action": [0.1], "env_action": [0.1]},
            "policy_budget_remaining": 12 - self.policy_step,
            "recovery_state": {"has_selective_recovery_state": bool(self.disturbance_count)},
        }

    def stop(self):
        self.stopped = True
        self.loaded = False

    def close(self):
        self.stop()

    def _frame(self, step: int) -> np.ndarray:
        frame = np.zeros((96, 96, 3), dtype=np.uint8)
        frame[:, :, 0] = (step * 17) % 255
        frame[:, :, 1] = 80
        frame[:, :, 2] = 160
        return frame


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


def test_manual_events_mark_run_interactive_and_non_formal(tmp_path) -> None:
    cfg = FakeRealConfig(out_dir=str(tmp_path))
    ctrl = ExperimentController(lambda: FakeRealBackend())
    try:
        assert ctrl.request_load(cfg.checkpoint, config=cfg).ok
        wait_for_state(ctrl, {ControllerState.READY}, timeout=5)
        assert ctrl.load_task(cfg).ok
        wait_until(ctrl, lambda s: s["task_text"] == "move the fake object")
        assert ctrl.start_episode(cfg).ok
        wait_until(ctrl, lambda s: s["policy_step"] >= 1 and s["state"] == "RUNNING")
        assert ctrl.pause().ok
        wait_for_state(ctrl, {ControllerState.PAUSED}, timeout=5)
        assert ctrl.resume().ok
        wait_for_state(ctrl, {ControllerState.RUNNING}, timeout=5)
        assert ctrl.step_once().ok
        wait_for_state(ctrl, {ControllerState.PAUSED}, timeout=5)
        assert ctrl.apply_disturbance(target_joint="auto", dx=0.02, dy=0.03).ok
        wait_until(ctrl, lambda s: s["disturbance_count"] == 1)
        assert ctrl.stop().ok
        snap = wait_for_state(ctrl, {ControllerState.FAILED, ControllerState.ERROR}, timeout=5)

        assert snap["termination_reason"] == "manual_stop"
        assert snap["interactive"] is True
        assert snap["formal_run"] is False
        assert snap["eligible_for_official_metrics"] is False
        assert snap["model_loaded"] is False

        run_dir = Path(snap["run_dir"])
        summary = json.loads((run_dir / "episode_summary.json").read_text())
        events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines() if line.strip()]
        names = {event["event"] for event in events}
        assert {"manual_pause", "manual_resume", "manual_step", "manual_disturbance", "manual_stop"}.issubset(names)
        assert summary["interactive"] is True
        assert summary["formal_run"] is False
        assert summary["eligible_for_official_metrics"] is False
        assert summary["exclude_from_formal_success_summaries"] is True
        assert summary["manual_intervention"] is True
    finally:
        ctrl.shutdown()
