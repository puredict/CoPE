"""Thread-safe single-worker controller for LIBERO dashboard backends."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import copy
import json
from pathlib import Path
import queue
import threading
import time
import traceback
from typing import Any, Callable
import uuid

import numpy as np

from libero_mock_backend import MockBackend, MockRunConfig, SimpleVideoRecorder, json_safe, utc_now_iso, write_json


class ControllerState(str, Enum):
    IDLE = "IDLE"
    LOADING = "LOADING"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    COMPLETED = "SUCCEEDED"  # Compatibility alias for older specs.


class CommandType(str, Enum):
    LOAD = "LOAD"
    LOAD_TASK = "LOAD_TASK"
    START = "START"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    STEP_ONCE = "STEP_ONCE"
    APPLY_DISTURBANCE = "APPLY_DISTURBANCE"
    STOP = "STOP"
    RESET = "RESET"
    SHUTDOWN = "SHUTDOWN"


@dataclass(frozen=True)
class ControlCommand:
    type: CommandType
    created_at: float
    payload: dict[str, Any]


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    message: str


TERMINAL_STATES = {
    ControllerState.SUCCEEDED,
    ControllerState.FAILED,
    ControllerState.ERROR,
}


def _state_value(state: ControllerState | str) -> str:
    return state.value if isinstance(state, ControllerState) else str(state)


def _config_dict(config: Any) -> dict[str, Any]:
    try:
        return asdict(config)
    except TypeError:
        if isinstance(config, dict):
            return dict(config)
        return dict(getattr(config, "__dict__", {}))


def _cfg(config: Any, name: str, default: Any = None) -> Any:
    if isinstance(config, dict):
        return config.get(name, default)
    return getattr(config, name, default)


def _cfg_output_dir(config: Any) -> str:
    return str(_cfg(config, "output_dir", None) or _cfg(config, "out_dir", None) or "/tmp/libero_dashboard")


def _backend_snapshot(backend: Any) -> dict[str, Any]:
    if not hasattr(backend, "get_snapshot"):
        return {}
    try:
        snap = backend.get_snapshot()
    except Exception as exc:
        return {"backend_snapshot_error": f"{type(exc).__name__}: {exc}"}
    return json_safe(snap or {})


def _initial_snapshot() -> dict[str, Any]:
    return {
        "state": ControllerState.IDLE.value,
        "message": "Dashboard controller is idle.",
        "run_id": None,
        "policy_step": 0,
        "environment_step": 0,
        "policy_budget_remaining": 0,
        "total_policy_steps": 0,
        "phase_policy_step": 0,
        "max_steps": 0,
        "mode": None,
        "task_suite": "libero_spatial",
        "task_id": 0,
        "trial_id": 0,
        "task_text": "",
        "original_prompt": "",
        "current_prompt": "",
        "resolved_target_joint": "",
        "target_joint": "",
        "target_position": None,
        "target_selection": {},
        "available_target_joints": [],
        "fresh_observation": None,
        "episode_status": None,
        "disturbance_state": {},
        "paused": False,
        "stop_requested": False,
        "disturbance_applied": False,
        "disturbance_count": 0,
        "manual_intervention": False,
        "human_intervention": False,
        "interactive": True,
        "formal_run": False,
        "eligible_for_official_metrics": False,
        "reward": 0.0,
        "done": False,
        "success": False,
        "termination_reason": None,
        "raw_action": [],
        "env_action": [],
        "latest_action": {"raw_action": [], "env_action": []},
        "latest_frame": None,
        "latest_frame_shape": None,
        "events_tail": [],
        "last_events": [],
        "error": None,
        "traceback_tail": "",
        "run_dir": None,
        "run_config_path": None,
        "events_jsonl_path": None,
        "episode_summary_path": None,
        "raw_video_path": None,
        "annotated_video_path": None,
        "last_disturbance": None,
        "recovery_state": {},
        "elapsed_seconds": 0.0,
        "inference_seconds": 0.0,
        "env_step_seconds": 0.0,
        "backend": "mock",
        "checkpoint": None,
        "resolved_unnorm_key": None,
        "device": "cpu",
        "model_loaded": False,
        "worker_alive": False,
        "active_episode": False,
    }


class ExperimentController:
    """Single-worker experiment controller.

    UI callbacks should call request_* methods, which validate lightweight state
    and enqueue commands.  Only the controller worker thread calls backend load,
    start, step, disturbance, or save methods.
    """

    def __init__(self, backend_factory: Callable[[], Any] | None = None) -> None:
        self._backend_factory = backend_factory or (lambda: MockBackend())
        self._backend = self._backend_factory()
        self._lock = threading.RLock()
        self._commands: queue.Queue[ControlCommand] = queue.Queue()
        self._state = ControllerState.IDLE
        self._snapshot = _initial_snapshot()
        self._latest_frame: np.ndarray | None = None
        self._events_tail: list[dict[str, Any]] = []
        self._shutdown = False
        self._worker_thread = threading.Thread(target=self._worker_main, name="libero-dashboard-worker", daemon=True)
        self._worker_thread.start()
        with self._lock:
            self._snapshot["worker_alive"] = True

    @property
    def worker_alive(self) -> bool:
        return self._worker_thread.is_alive()

    def snapshot(self, *, include_frame: bool = False) -> tuple[np.ndarray | None, dict[str, Any]]:
        with self._lock:
            frame = self._latest_frame.copy() if self._latest_frame is not None else None
            snap = copy.deepcopy(self._snapshot)
            snap["events_tail"] = copy.deepcopy(self._events_tail[-50:])
            snap["last_events"] = copy.deepcopy(self._events_tail[-50:])
            snap["worker_alive"] = self._worker_thread.is_alive()
            snap["state"] = _state_value(self._state)
            snap["latest_frame_shape"] = list(frame.shape) if frame is not None else None
            snap["latest_frame"] = frame.copy() if include_frame and frame is not None else None
            return frame, snap

    def request_load(self, checkpoint: str = "mock://libero-dashboard", config: Any | None = None) -> CommandResult:
        with self._lock:
            if self._state != ControllerState.IDLE:
                return CommandResult(False, f"Cannot load backend from state {self._state.value}.")
            self._set_state_locked(ControllerState.LOADING, "Backend load queued.")
        self._enqueue(CommandType.LOAD, {"checkpoint": checkpoint, "config": config})
        return CommandResult(True, "Backend load queued.")

    def load_task(self, config: Any) -> CommandResult:
        cfg = self._validated_config(config)
        if cfg is None:
            return CommandResult(False, "Invalid task config.")
        with self._lock:
            if self._state != ControllerState.READY:
                return CommandResult(False, f"Cannot load task from state {self._state.value}.")
        self._enqueue(CommandType.LOAD_TASK, {"config": cfg})
        return CommandResult(True, "Task load queued.")

    def start_episode(self, config: Any | None = None, **overrides: Any) -> CommandResult:
        try:
            cfg = self._validated_config(config or MockRunConfig(**overrides))
        except Exception as exc:
            return CommandResult(False, f"Invalid episode config: {exc}")
        if cfg is None:
            return CommandResult(False, "Invalid episode config.")
        with self._lock:
            if self._state != ControllerState.READY:
                return CommandResult(False, f"Cannot start episode from state {self._state.value}.")
            self._set_state_locked(ControllerState.RUNNING, "Episode start queued.")
            self._snapshot["active_episode"] = True
        self._enqueue(CommandType.START, {"config": cfg})
        return CommandResult(True, "Episode start queued.")

    def pause(self) -> CommandResult:
        with self._lock:
            if self._state not in {ControllerState.RUNNING, ControllerState.PAUSED}:
                return CommandResult(False, f"Cannot pause from state {self._state.value}.")
        self._enqueue(CommandType.PAUSE, {})
        return CommandResult(True, "Pause requested.")

    def resume(self) -> CommandResult:
        with self._lock:
            if self._state not in {ControllerState.RUNNING, ControllerState.PAUSED}:
                return CommandResult(False, f"Cannot resume from state {self._state.value}.")
        self._enqueue(CommandType.RESUME, {})
        return CommandResult(True, "Resume requested.")

    def step_once(self) -> CommandResult:
        with self._lock:
            if self._state not in {ControllerState.RUNNING, ControllerState.PAUSED}:
                return CommandResult(False, f"Cannot step from state {self._state.value}.")
        self._enqueue(CommandType.STEP_ONCE, {})
        return CommandResult(True, "Single policy step requested.")

    def apply_disturbance(self, *, target_joint: str = "auto", dx: float = 0.10, dy: float = 0.05) -> CommandResult:
        with self._lock:
            if self._state not in {ControllerState.RUNNING, ControllerState.PAUSED}:
                return CommandResult(False, f"Cannot disturb from state {self._state.value}.")
        self._enqueue(CommandType.APPLY_DISTURBANCE, {"target_joint": target_joint, "dx": float(dx), "dy": float(dy)})
        return CommandResult(True, "Manual disturbance requested.")

    def stop(self) -> CommandResult:
        with self._lock:
            if self._state not in {ControllerState.RUNNING, ControllerState.PAUSED, ControllerState.STOPPING}:
                return CommandResult(False, f"Cannot stop from state {self._state.value}.")
            self._set_state_locked(ControllerState.STOPPING, "Stop requested; saving will happen on the worker.")
            self._snapshot["stop_requested"] = True
        self._enqueue(CommandType.STOP, {})
        return CommandResult(True, "Stop requested.")

    def reset(self) -> CommandResult:
        with self._lock:
            if self._state not in TERMINAL_STATES and self._state != ControllerState.READY:
                return CommandResult(False, f"Cannot reset from state {self._state.value}.")
        self._enqueue(CommandType.RESET, {})
        return CommandResult(True, "Reset requested.")

    def shutdown(self, timeout: float = 5.0) -> None:
        self._enqueue(CommandType.SHUTDOWN, {})
        self._worker_thread.join(timeout=timeout)
        with self._lock:
            self._snapshot["worker_alive"] = self._worker_thread.is_alive()

    def _enqueue(self, command_type: CommandType, payload: dict[str, Any]) -> None:
        self._commands.put(ControlCommand(command_type, time.time(), payload))

    @staticmethod
    def _validated_config(config: Any) -> Any:
        return config.validated() if hasattr(config, "validated") else config

    def _worker_main(self) -> None:
        while not self._shutdown:
            try:
                command = self._commands.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                if command.type == CommandType.LOAD:
                    self._handle_load(command)
                elif command.type == CommandType.LOAD_TASK:
                    self._handle_load_task(command)
                elif command.type == CommandType.START:
                    self._run_episode(command.payload["config"])
                elif command.type == CommandType.RESET:
                    self._handle_reset()
                elif command.type == CommandType.SHUTDOWN:
                    self._shutdown = True
                else:
                    self._update_message(f"Command {command.type.value} is only valid during an active episode.")
            except Exception as exc:
                self._set_error(exc)
        with self._lock:
            self._snapshot["worker_alive"] = False

    def _handle_load(self, command: ControlCommand) -> None:
        with self._lock:
            self._set_state_locked(ControllerState.LOADING, "Loading backend.")
        try:
            config = command.payload.get("config")
            if hasattr(self._backend, "load"):
                info = self._backend.load(config or command.payload.get("checkpoint", "mock://libero-dashboard"))
            else:
                info = self._backend.load_model(command.payload.get("checkpoint", "mock://libero-dashboard"))
        except Exception as exc:
            self._set_error(exc)
            return
        with self._lock:
            self._snapshot.update(
                {
                    "model_loaded": True,
                    "checkpoint": info.get("checkpoint"),
                    "resolved_unnorm_key": info.get("resolved_unnorm_key"),
                    "device": info.get("device", "cpu"),
                    "backend": info.get("backend", "mock"),
                    "device_summary": info.get("device_summary"),
                }
            )
            self._set_state_locked(ControllerState.READY, "Backend loaded.")

    def _handle_load_task(self, command: ControlCommand) -> None:
        with self._lock:
            if self._state != ControllerState.READY:
                self._update_message(f"Cannot load task from state {self._state.value}.")
                return
            self._set_state_locked(ControllerState.READY, "Loading task on worker.")
        try:
            info = self._backend.inspect_task(command.payload["config"])
        except Exception as exc:
            self._set_error(exc)
            return
        frame = info.get("preview_frame")
        with self._lock:
            if frame is not None:
                self._latest_frame = np.asarray(frame, dtype=np.uint8).copy()
            target_joint = info.get("resolved_target_joint") or ""
            self._snapshot.update(
                {
                    "task_text": info.get("task_text", ""),
                    "current_prompt": info.get("task_text", ""),
                    "original_prompt": info.get("task_text", ""),
                    "available_target_joints": list(info.get("available_target_joints", [])),
                    "resolved_target_joint": target_joint,
                    "target_joint": target_joint,
                    "target_position": info.get("target_position"),
                    "target_selection": info.get("target_selection", {}),
                    "message": "Task loaded.",
                }
            )

    def _handle_reset(self) -> None:
        with self._lock:
            model_loaded = bool(self._snapshot.get("model_loaded"))
            preserved = {
                "model_loaded": model_loaded,
                "checkpoint": self._snapshot.get("checkpoint"),
                "resolved_unnorm_key": self._snapshot.get("resolved_unnorm_key"),
                "device": self._snapshot.get("device"),
                "device_summary": self._snapshot.get("device_summary"),
                "backend": self._snapshot.get("backend", "mock"),
            }
            self._snapshot = _initial_snapshot()
            self._snapshot.update(preserved)
            self._events_tail = []
            self._latest_frame = None
            self._state = ControllerState.READY if model_loaded else ControllerState.IDLE
            self._snapshot["state"] = self._state.value
            self._snapshot["message"] = "Controller reset."

    def _run_episode(self, config: Any) -> None:
        cfg = self._validated_config(config)
        run_id = self._make_run_id(cfg)
        run_dir = Path(_cfg_output_dir(cfg)).expanduser() / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        events_path = run_dir / "events.jsonl"
        summary_path = run_dir / "episode_summary.json"
        config_path = run_dir / "run_config.json"
        raw_video_path = run_dir / "raw.mp4"
        annotated_video_path = run_dir / "annotated.mp4"
        worker_log_path = run_dir / "worker_error.log"
        event_file = events_path.open("a", encoding="utf-8", buffering=1)
        recorder: SimpleVideoRecorder | None = None
        event_count = 0
        start_time = time.time()
        policy_step = 0
        environment_step = 0
        reward = 0.0
        done = False
        success = False
        termination_reason: str | None = None
        episode_status: dict[str, Any] | None = None
        raw_action: list[float] = []
        env_action: list[float] = []
        manual_intervention = False
        paused = False
        step_tokens = 0
        stop_requested = False
        shutdown_after_save = False
        error_text: str | None = None
        traceback_tail = ""
        video_info: dict[str, Any] = {}
        recovery_state: dict[str, Any] = {}
        terminal_state = ControllerState.FAILED
        cfg_payload = _config_dict(cfg)
        mode = str(_cfg(cfg, "mode", "reactive_disturbed"))

        def record(event: str, payload: dict[str, Any] | None = None) -> None:
            nonlocal event_count
            event_count += 1
            record_payload = {
                "timestamp": utc_now_iso(),
                "wall_time": round(time.time() - start_time, 6),
                "step": policy_step,
                "policy_step": policy_step,
                "environment_step": environment_step,
                "event": event,
                "state": _state_value(self._state),
                "mode": mode,
                "reward": reward,
                "paused": paused,
                "disturbance_count": getattr(self._backend, "disturbance_count", 0),
                "interactive": True,
                "formal_run": False,
                "eligible_for_official_metrics": False,
                "payload": json_safe(payload or {}),
            }
            event_file.write(json.dumps(json_safe(record_payload), sort_keys=True) + "\n")
            with self._lock:
                self._events_tail.append(record_payload)
                self._events_tail = self._events_tail[-50:]
                self._snapshot["events_tail"] = copy.deepcopy(self._events_tail)
                self._snapshot["last_events"] = copy.deepcopy(self._events_tail)

        def update_snapshot(
            state: ControllerState,
            message: str,
            frame: np.ndarray | None = None,
            *,
            force_active: bool = True,
        ) -> None:
            backend_snap = _backend_snapshot(self._backend)
            target_joint = (
                backend_snap.get("target_joint")
                or backend_snap.get("resolved_target_joint")
                or getattr(self._backend, "resolved_target_joint", "")
            )
            target_position = backend_snap.get("target_position")
            latest_action = backend_snap.get("latest_action") or {"raw_action": raw_action, "env_action": env_action}
            with self._lock:
                self._state = state
                if frame is not None:
                    self._latest_frame = np.asarray(frame, dtype=np.uint8).copy()
                self._snapshot.update(
                    {
                        "state": state.value,
                        "message": message,
                        "run_id": run_id,
                        "policy_step": policy_step,
                        "environment_step": environment_step,
                        "policy_budget_remaining": backend_snap.get(
                            "policy_budget_remaining", max(0, int(_cfg(cfg, "max_steps", 0)) - policy_step)
                        ),
                        "total_policy_steps": policy_step,
                        "phase_policy_step": policy_step,
                        "max_steps": int(_cfg(cfg, "max_steps", 0)),
                        "mode": mode,
                        "task_suite": _cfg(cfg, "task_suite", "libero_spatial"),
                        "task_id": int(_cfg(cfg, "task_id", 0)),
                        "trial_id": int(_cfg(cfg, "trial_id", 0)),
                        "task_text": backend_snap.get("task_text", getattr(self._backend, "task_text", "")),
                        "original_prompt": backend_snap.get("original_prompt", getattr(self._backend, "original_prompt", "")),
                        "current_prompt": backend_snap.get("current_prompt", getattr(self._backend, "current_prompt", "")),
                        "resolved_target_joint": target_joint,
                        "target_joint": target_joint,
                        "target_position": target_position,
                        "target_selection": backend_snap.get("target_selection", self._snapshot.get("target_selection", {})),
                        "available_target_joints": self._snapshot.get("available_target_joints", []),
                        "fresh_observation": backend_snap.get("fresh_observation"),
                        "episode_status": episode_status or backend_snap.get("episode_status"),
                        "disturbance_state": {
                            "applied": getattr(self._backend, "disturbance_count", 0) > 0,
                            "count": getattr(self._backend, "disturbance_count", 0),
                            "last": getattr(self._backend, "last_disturbance", None),
                        },
                        "paused": paused,
                        "stop_requested": stop_requested,
                        "disturbance_applied": getattr(self._backend, "disturbance_count", 0) > 0,
                        "disturbance_count": getattr(self._backend, "disturbance_count", 0),
                        "manual_intervention": manual_intervention,
                        "human_intervention": manual_intervention,
                        "interactive": True,
                        "formal_run": False,
                        "eligible_for_official_metrics": False,
                        "reward": float(reward),
                        "done": done,
                        "success": success,
                        "termination_reason": termination_reason,
                        "raw_action": list(raw_action),
                        "env_action": list(env_action),
                        "latest_action": latest_action,
                        "latest_frame_shape": list(self._latest_frame.shape) if self._latest_frame is not None else None,
                        "latest_frame": None,
                        "events_tail": copy.deepcopy(self._events_tail),
                        "last_events": copy.deepcopy(self._events_tail),
                        "error": error_text,
                        "traceback_tail": traceback_tail,
                        "run_dir": str(run_dir),
                        "run_config_path": str(config_path),
                        "events_jsonl_path": str(events_path),
                        "episode_summary_path": str(summary_path),
                        "raw_video_path": str(raw_video_path),
                        "annotated_video_path": str(annotated_video_path),
                        "last_disturbance": getattr(self._backend, "last_disturbance", None),
                        "recovery_state": backend_snap.get("recovery_state", copy.deepcopy(recovery_state)),
                        "elapsed_seconds": round(time.time() - start_time, 6),
                        "active_episode": force_active,
                    }
                )

        def latest_backend_frame() -> np.ndarray | None:
            frame = getattr(self._backend, "latest_frame", None)
            if frame is not None:
                return np.asarray(frame, dtype=np.uint8)
            return self._latest_frame

        def apply_disturbance_from_command(payload: dict[str, Any], source: str) -> dict[str, Any]:
            nonlocal manual_intervention, recovery_state
            if source == "manual_ui":
                manual_intervention = True
            disturbance = self._backend.apply_disturbance(
                cfg,
                policy_step=policy_step,
                source=source,
                target_joint=payload.get("target_joint"),
                dx=payload.get("dx"),
                dy=payload.get("dy"),
            )
            if disturbance.get("applied"):
                record("disturbance_applied", disturbance)
                if source == "manual_ui":
                    record("manual_disturbance", disturbance)
                backend_snap = _backend_snapshot(self._backend)
                recovery_state = backend_snap.get("recovery_state", recovery_state)
                if disturbance.get("prompt_changed"):
                    if not recovery_state:
                        recovery_state = {
                            "affected_joint": disturbance.get("joint"),
                            "failure_state": "object moved during execution",
                            "recovery_prompt": getattr(self._backend, "current_prompt", ""),
                        }
                    record("prompt_changed", recovery_state)
            else:
                record("disturbance_skipped", disturbance)
            refresh = disturbance.get("refresh") or {"method": "mock_backend.render_frame", "consumed_noop_env_step": False}
            record("observation_refreshed", refresh)
            frame = None
            if hasattr(self._backend, "render_frame"):
                frame = self._backend.render_frame(
                    cfg,
                    policy_step=policy_step,
                    paused=paused,
                    state_label=ControllerState.PAUSED.value if paused else ControllerState.RUNNING.value,
                    task_text=getattr(self._backend, "task_text", ""),
                    prompt=getattr(self._backend, "current_prompt", ""),
                    object_position=getattr(self._backend, "object_position", None),
                    disturbed=getattr(self._backend, "disturbance_count", 0) > 0,
                    disturbance_count=getattr(self._backend, "disturbance_count", 0),
                )
            if frame is None:
                frame = latest_backend_frame()
            update_snapshot(ControllerState.PAUSED if paused else ControllerState.RUNNING, "Disturbance processed.", frame)
            return disturbance

        def process_episode_command(command: ControlCommand) -> None:
            nonlocal paused, step_tokens, stop_requested, manual_intervention, shutdown_after_save
            if command.type == CommandType.PAUSE:
                manual_intervention = True
                paused = True
                record("manual_pause", {"requested_at": command.created_at})
                record("paused", {"source": "manual_ui"})
                update_snapshot(ControllerState.PAUSED, "Paused at policy-step boundary.")
            elif command.type == CommandType.RESUME:
                manual_intervention = True
                paused = False
                record("manual_resume", {"requested_at": command.created_at})
                update_snapshot(ControllerState.RUNNING, "Resumed.")
            elif command.type == CommandType.STEP_ONCE:
                manual_intervention = True
                paused = True
                step_tokens += 1
                record("manual_step", {"requested_at": command.created_at, "step_tokens": step_tokens})
                update_snapshot(ControllerState.PAUSED, "Single-step token granted.")
            elif command.type == CommandType.APPLY_DISTURBANCE:
                apply_disturbance_from_command(command.payload, "manual_ui")
            elif command.type == CommandType.STOP:
                manual_intervention = True
                stop_requested = True
                record("manual_stop", {"requested_at": command.created_at})
                update_snapshot(ControllerState.STOPPING, "Stop accepted; finalizing run.")
            elif command.type == CommandType.SHUTDOWN:
                stop_requested = True
                shutdown_after_save = True
                record("manual_stop", {"requested_at": command.created_at, "source": "shutdown"})
                update_snapshot(ControllerState.STOPPING, "Shutdown requested; finalizing run.")
            elif command.type == CommandType.START:
                record("start_rejected", {"reason": "episode_already_active"})
            elif command.type == CommandType.RESET:
                record("reset_rejected", {"reason": "episode_active"})
            elif command.type == CommandType.LOAD:
                record("load_rejected", {"reason": "episode_active"})
            elif command.type == CommandType.LOAD_TASK:
                record("load_task_rejected", {"reason": "episode_active"})

        def drain_commands() -> None:
            while True:
                try:
                    command = self._commands.get_nowait()
                except queue.Empty:
                    return
                process_episode_command(command)

        def wait_for_permission() -> bool:
            nonlocal paused, step_tokens
            while paused and step_tokens <= 0 and not stop_requested:
                try:
                    command = self._commands.get(timeout=0.05)
                except queue.Empty:
                    update_snapshot(ControllerState.PAUSED, "Paused.")
                    continue
                process_episode_command(command)
            if stop_requested:
                return False
            if step_tokens > 0:
                step_tokens -= 1
                return True
            return True

        try:
            write_json(
                config_path,
                {
                    "config": cfg_payload,
                    "run_id": run_id,
                    "created_at": utc_now_iso(),
                    "interactive": True,
                    "formal_run": False,
                    "eligible_for_official_metrics": False,
                    "backend": self._snapshot.get("backend", "mock"),
                },
            )
            start_info = self._backend.start_episode(cfg)
            recorder = SimpleVideoRecorder(raw_video_path, annotated_video_path)
            with self._lock:
                self._events_tail = []
                self._snapshot["available_target_joints"] = list(start_info.get("available_target_joints", []))
                self._snapshot["target_selection"] = start_info.get("target_selection", self._snapshot.get("target_selection", {}))
            initial_frame = start_info["frame"]
            recorder.append(initial_frame, initial_frame)
            record("episode_started", {"config": cfg_payload, "run_dir": str(run_dir)})
            update_snapshot(ControllerState.RUNNING, "Episode running.", initial_frame)

            while True:
                drain_commands()
                if stop_requested:
                    termination_reason = "manual_stop"
                    done = True
                    success = False
                    break

                if self._backend.should_auto_disturb(cfg, policy_step):
                    if getattr(self._backend, "disturbance_count", 0) > 0 and not bool(
                        _cfg(cfg, "allow_multiple_disturbances", False)
                    ):
                        record("disturbance_skipped", {"reason": "manual_disturbance_already_applied", "source": "auto"})
                    else:
                        apply_disturbance_from_command(
                            {"target_joint": _cfg(cfg, "target_joint", "auto"), "dx": _cfg(cfg, "dx", 0.10), "dy": _cfg(cfg, "dy", 0.05)},
                            "auto",
                        )

                if mode == "verifier_stop" and getattr(self._backend, "disturbance_count", 0) > 0:
                    termination_reason = "verifier_stop"
                    done = True
                    success = False
                    record("verifier_stopped", {"decision": "stop_or_full_replan", "has_selective_recovery_state": False})
                    break

                if not wait_for_permission():
                    termination_reason = "manual_stop"
                    done = True
                    success = False
                    break

                update_snapshot(ControllerState.RUNNING, "Executing policy step.")
                result = self._backend.step(cfg, policy_step=policy_step, paused=False)
                policy_step = int(result.policy_step)
                environment_step = int(getattr(result, "environment_step", environment_step + 1))
                reward = float(result.reward)
                done = bool(result.done)
                success = bool(result.success)
                termination_reason = result.termination_reason
                raw_action = list(result.raw_action)
                env_action = list(result.env_action)
                episode_status = json_safe(getattr(result, "episode_status", None))
                recorder.append(result.raw_frame, result.annotated_frame)
                record(
                    "policy_step_completed",
                    {
                        "raw_action": raw_action,
                        "env_action": env_action,
                        "inference_seconds": result.inference_seconds,
                        "env_step_seconds": result.env_step_seconds,
                        "done": done,
                        "success": success,
                        "termination_reason": termination_reason,
                        "episode_status": episode_status,
                    },
                )
                with self._lock:
                    self._snapshot["inference_seconds"] = result.inference_seconds
                    self._snapshot["env_step_seconds"] = result.env_step_seconds
                update_snapshot(ControllerState.RUNNING, "Policy step completed.", result.annotated_frame)
                if done:
                    break
                if paused:
                    update_snapshot(ControllerState.PAUSED, "Paused after strict single-step.", result.annotated_frame)

            terminal_state = ControllerState.SUCCEEDED if success else ControllerState.FAILED
            if termination_reason == "manual_stop":
                record("episode_stopped", {"termination_reason": termination_reason})
            elif success:
                record("episode_succeeded", {"termination_reason": termination_reason})
            else:
                record("episode_failed", {"termination_reason": termination_reason})
        except Exception as exc:
            done = True
            success = False
            termination_reason = "worker_exception"
            error_text = f"{type(exc).__name__}: {exc}"
            traceback_full = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            traceback_tail = "".join(traceback_full.splitlines(keepends=True)[-12:])
            terminal_state = ControllerState.ERROR
            worker_log_path.write_text(traceback_full, encoding="utf-8")
            try:
                record("worker_exception", {"error": error_text, "traceback_tail": traceback_tail, "worker_log_path": str(worker_log_path)})
            except Exception:
                pass
        finally:
            try:
                if recorder is not None:
                    video_info = recorder.close()
            except Exception as exc:  # pragma: no cover - defensive finalization.
                video_info = {"warnings": [f"video finalization failed: {type(exc).__name__}: {exc}"]}

            if termination_reason == "manual_stop" and hasattr(self._backend, "stop"):
                try:
                    self._backend.stop()
                except Exception as exc:
                    error_text = error_text or f"Backend stop failed: {type(exc).__name__}: {exc}"
                    terminal_state = ControllerState.ERROR

            backend_final_snapshot = _backend_snapshot(self._backend)
            summary = {
                "run_id": run_id,
                "state": terminal_state.value,
                "success": success,
                "done": done,
                "termination_reason": termination_reason,
                "episode_status": episode_status or backend_final_snapshot.get("episode_status"),
                "error": error_text,
                "traceback_tail": traceback_tail,
                "config": cfg_payload,
                "policy_step": policy_step,
                "environment_step": environment_step,
                "policy_budget_remaining": backend_final_snapshot.get(
                    "policy_budget_remaining", max(0, int(_cfg(cfg, "max_steps", 0)) - policy_step)
                ),
                "reward": reward,
                "disturbance_count": getattr(self._backend, "disturbance_count", 0),
                "last_disturbance": getattr(self._backend, "last_disturbance", None),
                "manual_intervention": manual_intervention,
                "human_intervention": manual_intervention,
                "interactive": True,
                "formal_run": False,
                "eligible_for_official_metrics": False,
                "exclude_from_formal_success_summaries": True,
                "current_prompt": backend_final_snapshot.get("current_prompt", getattr(self._backend, "current_prompt", "")),
                "original_prompt": backend_final_snapshot.get("original_prompt", getattr(self._backend, "original_prompt", "")),
                "target_joint": backend_final_snapshot.get("target_joint", getattr(self._backend, "resolved_target_joint", "")),
                "target_position": backend_final_snapshot.get("target_position"),
                "fresh_observation": backend_final_snapshot.get("fresh_observation"),
                "latest_action": backend_final_snapshot.get("latest_action", {"raw_action": raw_action, "env_action": env_action}),
                "recovery_state": backend_final_snapshot.get("recovery_state", recovery_state),
                "backend_snapshot": backend_final_snapshot,
                "paths": {
                    "run_dir": str(run_dir),
                    "run_config": str(config_path),
                    "events_jsonl": str(events_path),
                    "episode_summary": str(summary_path),
                    "raw_video": str(raw_video_path),
                    "annotated_video": str(annotated_video_path),
                    "worker_log": str(worker_log_path),
                },
                "video": video_info,
                "event_count": event_count,
                "completed_at": utc_now_iso(),
            }
            try:
                write_json(summary_path, summary)
                record("episode_summary_written", {"episode_summary_path": str(summary_path)})
            except Exception as exc:
                error_text = error_text or f"Summary write failed: {type(exc).__name__}: {exc}"
                terminal_state = ControllerState.ERROR
            try:
                event_file.flush()
                event_file.close()
            except Exception:
                pass
            stop_requested = False
            paused = False
            update_snapshot(
                terminal_state,
                f"Episode finished: {termination_reason or terminal_state.value}.",
                frame=self._latest_frame,
                force_active=False,
            )
            with self._lock:
                self._snapshot.update(
                    {
                        "done": True,
                        "success": success,
                        "termination_reason": termination_reason,
                        "episode_status": episode_status or backend_final_snapshot.get("episode_status"),
                        "error": error_text,
                        "traceback_tail": traceback_tail,
                        "active_episode": False,
                        "episode_summary_path": str(summary_path),
                        "raw_video_path": str(raw_video_path),
                        "annotated_video_path": str(annotated_video_path),
                        "model_loaded": bool(getattr(self._backend, "loaded", self._snapshot.get("model_loaded", False))),
                    }
                )
            if shutdown_after_save:
                self._shutdown = True

    def _make_run_id(self, cfg: Any) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        short = uuid.uuid4().hex[:8]
        return f"{stamp}_task{_cfg(cfg, 'task_id', 0)}_trial{_cfg(cfg, 'trial_id', 0)}_{_cfg(cfg, 'mode', 'unknown')}_{short}"

    def _set_state_locked(self, state: ControllerState, message: str) -> None:
        self._state = state
        self._snapshot["state"] = state.value
        self._snapshot["message"] = message

    def _update_message(self, message: str) -> None:
        with self._lock:
            self._snapshot["message"] = message

    def _set_error(self, exc: BaseException) -> None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)[-8:])
        with self._lock:
            self._state = ControllerState.ERROR
            self._snapshot.update(
                {
                    "state": ControllerState.ERROR.value,
                    "message": "Worker error.",
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback_tail": tb,
                    "active_episode": False,
                }
            )


def wait_for_state(
    controller: ExperimentController,
    states: set[ControllerState] | set[str],
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    wanted = {_state_value(state) for state in states}
    deadline = time.time() + timeout
    last_snapshot: dict[str, Any] = {}
    while time.time() < deadline:
        _, snapshot = controller.snapshot()
        last_snapshot = snapshot
        if snapshot["state"] in wanted:
            return snapshot
        time.sleep(0.02)
    raise TimeoutError(f"Timed out waiting for states {sorted(wanted)}; last snapshot={last_snapshot}")


def snapshot_for_json(snapshot: dict[str, Any]) -> dict[str, Any]:
    cleaned = copy.deepcopy(snapshot)
    cleaned["latest_frame"] = None
    return json_safe(cleaned)
