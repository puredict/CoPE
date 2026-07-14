from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import SimpleNamespace
import time

import numpy as np

from libero_dashboard_controller import ControllerState, ExperimentController, snapshot_for_json, wait_for_state
from summarize_disturbance_results import summarize_run


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

    def __init__(
        self,
        *,
        candidates=None,
        ambiguous=False,
        recommended_joint="fake_object_joint0",
        clear_disturbance_on_stop=False,
    ) -> None:
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
        self.candidates = candidates or [
            {"joint": "fake_object_joint0", "name": "fake_object_joint0", "score": 2, "reason": "fake unique candidate"}
        ]
        self.ambiguous = ambiguous
        self.recommended_joint = recommended_joint
        self.start_configs = []
        self.clear_disturbance_on_stop = clear_disturbance_on_stop

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
            "available_target_joints": [item["joint"] for item in self.candidates],
            "target_joint_candidates": list(self.candidates),
            "target_joint_top_score": max(item["score"] for item in self.candidates) if self.candidates else None,
            "target_joint_ambiguous": self.ambiguous,
            "recommended_target_joint": self.recommended_joint,
            "target_selection": {
                "candidates": list(self.candidates),
                "ambiguous": self.ambiguous,
                "recommended_joint": self.recommended_joint,
            },
            "resolved_target_joint": self.recommended_joint if not self.ambiguous else None,
            "target_position": self.object_position if self.recommended_joint else None,
            "preview_frame": self.latest_frame,
        }

    def start_episode(self, config):
        self.start_configs.append(config)
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
        if self.clear_disturbance_on_stop:
            self.disturbance_count = 0
            self.last_disturbance = None

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
        run_config = json.loads((run_dir / "run_config.json").read_text())
        summary = json.loads((run_dir / "episode_summary.json").read_text())
        events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines() if line.strip()]
        actions = [json.loads(line) for line in (run_dir / "actions.jsonl").read_text().splitlines() if line.strip()]
        names = {event["event"] for event in events}
        assert {"manual_pause", "manual_resume", "manual_step", "manual_disturbance", "manual_stop"}.issubset(names)
        assert run_config["interactive"] is True
        assert run_config["formal_run"] is False
        assert run_config["eligible_for_official_metrics"] is False
        assert run_config["exclude_from_formal_success_summaries"] is True
        assert all(event["exclude_from_formal_success_summaries"] is True for event in events)
        assert actions
        assert all(action["interactive"] is True for action in actions)
        assert all(action["formal_run"] is False for action in actions)
        assert all(action["eligible_for_official_metrics"] is False for action in actions)
        assert all(action["exclude_from_formal_success_summaries"] is True for action in actions)
        assert summary["interactive"] is True
        assert summary["formal_run"] is False
        assert summary["eligible_for_official_metrics"] is False
        assert summary["exclude_from_formal_success_summaries"] is True
        assert summary["manual_intervention"] is True
    finally:
        ctrl.shutdown()


def test_manual_stop_summary_preserves_disturbance_after_backend_release(tmp_path) -> None:
    cfg = FakeRealConfig(out_dir=str(tmp_path))
    backend = FakeRealBackend(clear_disturbance_on_stop=True)
    ctrl = ExperimentController(lambda: backend)
    try:
        assert ctrl.request_load(cfg.checkpoint, config=cfg).ok
        wait_for_state(ctrl, {ControllerState.READY}, timeout=5)
        assert ctrl.load_task(cfg).ok
        wait_until(ctrl, lambda s: s["task_text"] == "move the fake object")
        assert ctrl.start_episode(cfg).ok
        wait_until(ctrl, lambda s: s["policy_step"] >= 1 and s["state"] == "RUNNING")
        assert ctrl.pause().ok
        wait_for_state(ctrl, {ControllerState.PAUSED}, timeout=5)
        assert ctrl.apply_disturbance(target_joint="auto", dx=0.02, dy=0.03).ok
        wait_until(ctrl, lambda s: s["disturbance_count"] == 1)
        assert ctrl.stop().ok
        snap = wait_for_state(ctrl, {ControllerState.FAILED, ControllerState.ERROR}, timeout=5)

        run_dir = Path(snap["run_dir"])
        summary = json.loads((run_dir / "episode_summary.json").read_text())

        assert backend.disturbance_count == 0
        assert backend.last_disturbance is None
        assert summary["disturbance_count"] == 1
        assert summary["last_disturbance"]["applied"] is True
        assert summary["last_disturbance"]["source"] == "manual_ui"
        assert snap["disturbance_count"] == 1
        assert snap["last_disturbance"]["source"] == "manual_ui"
    finally:
        ctrl.shutdown()


def test_clean_mode_allows_empty_target_joint_after_task_load(tmp_path) -> None:
    tied = [
        {"joint": "akita_black_bowl_1_joint0", "name": "akita_black_bowl_1_joint0", "score": 2, "reason": "tie"},
        {"joint": "akita_black_bowl_2_joint0", "name": "akita_black_bowl_2_joint0", "score": 2, "reason": "tie"},
    ]
    backend = FakeRealBackend(candidates=tied, ambiguous=True, recommended_joint=None)
    cfg = FakeRealConfig(out_dir=str(tmp_path), mode="clean", enable_auto_disturbance=False, target_joint="")
    ctrl = ExperimentController(lambda: backend)
    try:
        assert ctrl.request_load(cfg.checkpoint, config=cfg).ok
        wait_for_state(ctrl, {ControllerState.READY}, timeout=5)
        assert ctrl.load_task(cfg).ok
        snap = wait_until(ctrl, lambda s: s["task_text"] == "move the fake object")
        assert snap["state"] == "READY"
        assert snap["target_joint_ambiguous"] is True
        assert ctrl.start_episode(cfg).ok
        wait_until(ctrl, lambda s: bool(backend.start_configs) and s["state"] == "RUNNING")
        assert ctrl.stop().ok
        wait_for_state(ctrl, {ControllerState.FAILED}, timeout=5)
    finally:
        ctrl.shutdown()


def test_disturbed_tied_candidates_require_user_target_without_error(tmp_path) -> None:
    tied = [
        {"joint": "akita_black_bowl_1_joint0", "name": "akita_black_bowl_1_joint0", "score": 2, "reason": "tie"},
        {"joint": "akita_black_bowl_2_joint0", "name": "akita_black_bowl_2_joint0", "score": 2, "reason": "tie"},
    ]
    backend = FakeRealBackend(candidates=tied, ambiguous=True, recommended_joint=None)
    cfg = FakeRealConfig(out_dir=str(tmp_path), mode="reactive_disturbed", enable_auto_disturbance=False, target_joint="")
    ctrl = ExperimentController(lambda: backend)
    try:
        assert ctrl.request_load(cfg.checkpoint, config=cfg).ok
        wait_for_state(ctrl, {ControllerState.READY}, timeout=5)
        queued = ctrl.load_task(cfg)
        assert queued.ok
        assert queued.message == "Task load queued."
        snap = wait_until(ctrl, lambda s: len(s["available_target_joints"]) == 2)
        assert snap["state"] == "READY"
        assert snap["target_joint_ambiguous"] is True
        assert snap["message"] == "Task loaded. Select a target joint before starting disturbed mode."
        start = ctrl.start_episode(cfg)
        assert not start.ok
        assert start.message == "Please select a target joint before starting a disturbed run."
        _, after = ctrl.snapshot()
        assert after["state"] == "READY"
        assert after["message"] == start.message
        assert not backend.start_configs
    finally:
        ctrl.shutdown()


def test_disturbed_selected_candidate_can_start(tmp_path) -> None:
    tied = [
        {"joint": "akita_black_bowl_1_joint0", "name": "akita_black_bowl_1_joint0", "score": 2, "reason": "tie"},
        {"joint": "akita_black_bowl_2_joint0", "name": "akita_black_bowl_2_joint0", "score": 2, "reason": "tie"},
    ]
    backend = FakeRealBackend(candidates=tied, ambiguous=True, recommended_joint=None)
    cfg = FakeRealConfig(
        out_dir=str(tmp_path),
        mode="reactive_disturbed",
        enable_auto_disturbance=False,
        target_joint="akita_black_bowl_1_joint0",
    )
    ctrl = ExperimentController(lambda: backend)
    try:
        assert ctrl.request_load(cfg.checkpoint, config=cfg).ok
        wait_for_state(ctrl, {ControllerState.READY}, timeout=5)
        assert ctrl.load_task(cfg).ok
        wait_until(ctrl, lambda s: len(s["available_target_joints"]) == 2)
        assert ctrl.start_episode(cfg).ok
        wait_until(ctrl, lambda s: bool(backend.start_configs) and s["state"] == "RUNNING")
        assert backend.start_configs[-1].target_joint == "akita_black_bowl_1_joint0"
        assert ctrl.stop().ok
        wait_for_state(ctrl, {ControllerState.FAILED}, timeout=5)
    finally:
        ctrl.shutdown()


def test_disturbed_rejects_unknown_target_without_error(tmp_path) -> None:
    backend = FakeRealBackend()
    cfg = FakeRealConfig(
        out_dir=str(tmp_path),
        mode="reactive_disturbed",
        enable_auto_disturbance=False,
        target_joint="missing_joint0",
    )
    ctrl = ExperimentController(lambda: backend)
    try:
        assert ctrl.request_load(cfg.checkpoint, config=cfg).ok
        wait_for_state(ctrl, {ControllerState.READY}, timeout=5)
        assert ctrl.load_task(cfg).ok
        wait_until(ctrl, lambda s: s["available_target_joints"])
        start = ctrl.start_episode(cfg)
        assert not start.ok
        assert "not in the loaded task candidates" in start.message
        _, snap = ctrl.snapshot()
        assert snap["state"] == "READY"
        assert not backend.start_configs
    finally:
        ctrl.shutdown()


def test_unique_candidate_is_used_as_recommendation(tmp_path) -> None:
    backend = FakeRealBackend()
    cfg = FakeRealConfig(out_dir=str(tmp_path), mode="reactive_disturbed", enable_auto_disturbance=False, target_joint="")
    ctrl = ExperimentController(lambda: backend)
    try:
        assert ctrl.request_load(cfg.checkpoint, config=cfg).ok
        wait_for_state(ctrl, {ControllerState.READY}, timeout=5)
        assert ctrl.load_task(cfg).ok
        snap = wait_until(ctrl, lambda s: s["recommended_target_joint"] == "fake_object_joint0")
        assert snap["target_joint_ambiguous"] is False
        start = ctrl.start_episode(cfg)
        assert start.ok
        assert start.message == "Using recommended target joint fake_object_joint0."
        wait_until(ctrl, lambda s: bool(backend.start_configs) and s["state"] == "RUNNING")
        assert backend.start_configs[-1].target_joint == "fake_object_joint0"
        assert ctrl.stop().ok
        wait_for_state(ctrl, {ControllerState.FAILED}, timeout=5)
    finally:
        ctrl.shutdown()


def test_summary_warns_and_excludes_interactive_runs(tmp_path, capsys) -> None:
    (tmp_path / "episode_summary.json").write_text(
        json.dumps(
            {
                "interactive": True,
                "formal_run": False,
                "eligible_for_official_metrics": False,
                "exclude_from_formal_success_summaries": True,
                "success": True,
            }
        ),
        encoding="utf-8",
    )

    rows = summarize_run("interactive-smoke", tmp_path)
    captured = capsys.readouterr()

    assert rows == [
        {
            "label": "interactive-smoke",
            "run_dir": str(tmp_path),
            "condition": "diagnostic_skipped",
            "n": 0,
            "successes": 0,
            "success_rate": "",
            "disturbance_applied": 0,
        }
    ]
    assert "WARNING: excluding 1 interactive/non-formal record(s)" in captured.err


def test_snapshot_for_json_accepts_empty_nested_payloads() -> None:
    assert snapshot_for_json(None) is None
    assert snapshot_for_json({"latest_frame": np.zeros((2, 2, 3), dtype=np.uint8), "episode_status": None}) == {
        "latest_frame": None,
        "episode_status": None,
    }
