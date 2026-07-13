from __future__ import annotations

import queue
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from libero_experiment_core import (
    CANONICAL_MODES,
    EpisodeRecorder,
    ExperimentConfig,
    PolicyStepResult,
    build_recovery_prompt,
    choose_target_joint,
    create_libero_env,
    draw_overlay,
    execute_policy_step,
    extract_episode_status,
    frame_from_obs,
    get_benchmark_suite,
    get_device_summary,
    get_dummy_action,
    get_image_resize_size,
    get_joint_qpos,
    iso_now,
    json_safe,
    list_free_joints,
    load_model_and_processor,
    make_model_cfg,
    move_free_joint_xy,
    refresh_observation_after_sim_change,
    set_seed,
    short_traceback,
    sim_from_env,
    unload_torch_model_refs,
    validate_task_and_trial,
    verifier_stop_state,
)


class ControllerState(str, Enum):
    IDLE = "idle"
    LOADING_MODEL = "loading_model"
    READY = "ready"
    INSPECTING_TASK = "inspecting_task"
    STARTING = "starting"
    STABILIZING = "stabilizing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class CommandType(str, Enum):
    MANUAL_DISTURBANCE = "manual_disturbance"
    STOP = "stop"


class StepPermission(str, Enum):
    RUN = "run"
    STOP = "stop"
    CHECK_COMMANDS = "check_commands"


@dataclass(frozen=True)
class ControlCommand:
    type: CommandType
    created_at: float
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class DashboardSnapshot:
    controller_state: str = ControllerState.IDLE.value
    message: str = "Idle."
    error: str | None = None
    traceback_tail: str | None = None
    model_loaded: bool = False
    checkpoint: str | None = None
    resolved_unnorm_key: str | None = None
    device: str | None = None
    device_info: dict[str, Any] = field(default_factory=dict)
    task_suite: str = "libero_spatial"
    task_id: int = 0
    trial_id: int = 0
    mode: str = "reactive_disturbed"
    task_description: str | None = None
    original_prompt: str | None = None
    current_prompt: str | None = None
    resolved_target_joint: str | None = None
    available_target_joints: list[dict[str, Any]] = field(default_factory=list)
    trial_count: int | None = None
    policy_step: int = 0
    phase_policy_step: int = 0
    total_policy_steps: int = 0
    max_steps: int = 0
    reward: float = 0.0
    done: bool = False
    success: bool = False
    paused: bool = False
    stop_requested: bool = False
    disturbance_applied: bool = False
    disturbance_count: int = 0
    last_disturbance: dict[str, Any] | None = None
    recovery_state: dict[str, Any] | None = None
    raw_action: list[float] | None = None
    env_action: list[float] | None = None
    inference_seconds: float | None = None
    env_step_seconds: float | None = None
    elapsed_seconds: float = 0.0
    human_intervention: bool = False
    eligible_for_official_metrics: bool = False
    run_dir: str | None = None
    raw_video_path: str | None = None
    annotated_video_path: str | None = None
    episode_json_path: str | None = None
    events_jsonl_path: str | None = None
    last_events: list[dict[str, Any]] = field(default_factory=list)
    reset_count: int = 0
    extra_env_steps: int = 0
    stopped_by_verifier: bool = False


@dataclass
class LoadedModel:
    model: Any = None
    processor: Any = None
    model_cfg: Any = None
    resolved_unnorm_key: str | None = None
    device_info: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskInspection:
    task_description: str
    trial_count: int
    free_joints: list[dict[str, Any]]
    auto_target_joint: str | None
    preview_frame: np.ndarray | None = None


@dataclass
class EpisodeContext:
    cfg: ExperimentConfig
    task_suite: Any
    task: Any
    initial_states: list[Any]
    env: Any
    obs: dict[str, Any]
    task_description: str
    resize_size: Any
    resolved_target_joint: str
    available_target_joints: list[dict[str, Any]]
    model_state: LoadedModel
    saved_rollback_state: Any = None


class RuntimeBackend(Protocol):
    def load_model(self, cfg: ExperimentConfig) -> LoadedModel:
        ...

    def unload_model(self, model_state: LoadedModel | None) -> None:
        ...

    def inspect_task(self, cfg: ExperimentConfig, model_state: LoadedModel | None) -> TaskInspection:
        ...

    def create_episode(self, cfg: ExperimentConfig, model_state: LoadedModel) -> EpisodeContext:
        ...

    def stabilize(self, ctx: EpisodeContext) -> tuple[dict[str, Any], float, bool, dict[str, Any], int]:
        ...

    def execute_policy_step(self, ctx: EpisodeContext, prompt: str) -> PolicyStepResult:
        ...

    def apply_disturbance(self, ctx: EpisodeContext, joint: str, dx: float, dy: float) -> tuple[dict[str, Any], dict[str, Any], np.ndarray | None, int]:
        ...

    def save_state(self, ctx: EpisodeContext) -> Any:
        ...

    def restore_state(self, ctx: EpisodeContext, state: Any) -> tuple[dict[str, Any], np.ndarray | None, int, dict[str, Any]]:
        ...

    def reset_episode(self, ctx: EpisodeContext) -> tuple[dict[str, Any], float, bool, dict[str, Any], int]:
        ...

    def close_episode(self, ctx: EpisodeContext | None) -> None:
        ...


class RealLiberoBackend:
    def load_model(self, cfg: ExperimentConfig) -> LoadedModel:
        set_seed(cfg.seed)
        model, processor, model_cfg, resolved = load_model_and_processor(cfg)
        return LoadedModel(model, processor, model_cfg, resolved, get_device_summary())

    def unload_model(self, model_state: LoadedModel | None) -> None:
        if model_state is not None:
            model_state.model = None
            model_state.processor = None
            model_state.model_cfg = None
        unload_torch_model_refs()

    def inspect_task(self, cfg: ExperimentConfig, model_state: LoadedModel | None) -> TaskInspection:
        model_cfg = model_state.model_cfg if model_state and model_state.model_cfg else make_model_cfg(cfg)
        suite = get_benchmark_suite(cfg.task_suite)
        initial_states = validate_task_and_trial(suite, cfg)
        task = suite.get_task(cfg.task_id)
        env = None
        try:
            env, task_description = create_libero_env(task, cfg)
            resize_size = get_image_resize_size(model_cfg)
            env.reset()
            obs = env.set_init_state(initial_states[cfg.trial_id])
            for _ in range(cfg.num_steps_wait):
                obs, _, _, _ = env.step(get_dummy_action("openvla"))
            free_joints = list_free_joints(env, task_description)
            auto_target = choose_target_joint(env, task_description, "auto") if free_joints else None
            frame = frame_from_obs(obs, resize_size)
            return TaskInspection(task_description, len(initial_states), free_joints, auto_target, frame)
        finally:
            if env is not None:
                try:
                    env.close()
                except Exception:
                    pass

    def create_episode(self, cfg: ExperimentConfig, model_state: LoadedModel) -> EpisodeContext:
        suite = get_benchmark_suite(cfg.task_suite)
        initial_states = validate_task_and_trial(suite, cfg)
        task = suite.get_task(cfg.task_id)
        env, task_description = create_libero_env(task, cfg)
        env.reset()
        obs = env.set_init_state(initial_states[cfg.trial_id])
        resize_size = get_image_resize_size(model_state.model_cfg)
        free_joints = list_free_joints(env, task_description)
        resolved_target = choose_target_joint(env, task_description, cfg.target_joint)
        return EpisodeContext(
            cfg=cfg,
            task_suite=suite,
            task=task,
            initial_states=initial_states,
            env=env,
            obs=obs,
            task_description=task_description,
            resize_size=resize_size,
            resolved_target_joint=resolved_target,
            available_target_joints=free_joints,
            model_state=model_state,
        )

    def stabilize(self, ctx: EpisodeContext) -> tuple[dict[str, Any], float, bool, dict[str, Any], int]:
        reward = 0.0
        done = False
        info: dict[str, Any] = {}
        obs = ctx.obs
        for _ in range(ctx.cfg.num_steps_wait):
            obs, reward, done, info = ctx.env.step(get_dummy_action("openvla"))
        ctx.obs = obs
        return obs, float(reward), bool(done), json_safe(info), int(ctx.cfg.num_steps_wait)

    def execute_policy_step(self, ctx: EpisodeContext, prompt: str) -> PolicyStepResult:
        result = execute_policy_step(
            cfg=ctx.model_state.model_cfg,
            model=ctx.model_state.model,
            processor=ctx.model_state.processor,
            env=ctx.env,
            obs=ctx.obs,
            prompt=prompt,
            resize_size=ctx.resize_size,
        )
        ctx.obs = result.next_obs
        return result

    def apply_disturbance(self, ctx: EpisodeContext, joint: str, dx: float, dy: float) -> tuple[dict[str, Any], dict[str, Any], np.ndarray | None, int]:
        record = move_free_joint_xy(ctx.env, joint, dx, dy)
        obs, refresh = refresh_observation_after_sim_change(ctx.env, ctx.model_state.model_cfg)
        ctx.obs = obs
        extra = 1 if refresh.get("consumed_noop_env_step") else 0
        frame = frame_from_obs(obs, ctx.resize_size)
        record["refresh"] = refresh
        return obs, record, frame, extra

    def save_state(self, ctx: EpisodeContext) -> Any:
        return sim_from_env(ctx.env).get_state().flatten().copy()

    def restore_state(self, ctx: EpisodeContext, state: Any) -> tuple[dict[str, Any], np.ndarray | None, int, dict[str, Any]]:
        sim = sim_from_env(ctx.env)
        sim.set_state_from_flattened(state)
        sim.forward()
        obs, refresh = refresh_observation_after_sim_change(ctx.env, ctx.model_state.model_cfg)
        ctx.obs = obs
        extra = 1 if refresh.get("consumed_noop_env_step") else 0
        return obs, frame_from_obs(obs, ctx.resize_size), extra, refresh

    def reset_episode(self, ctx: EpisodeContext) -> tuple[dict[str, Any], float, bool, dict[str, Any], int]:
        ctx.env.reset()
        obs = ctx.env.set_init_state(ctx.initial_states[ctx.cfg.trial_id])
        ctx.obs = obs
        _, reward, done, info, extra = self.stabilize(ctx)
        return ctx.obs, reward, done, info, extra

    def close_episode(self, ctx: EpisodeContext | None) -> None:
        if ctx is not None and ctx.env is not None:
            try:
                ctx.env.close()
            except Exception:
                pass


@dataclass
class MockEnvState:
    policy_step: int = 0
    disturbances: list[dict[str, Any]] = field(default_factory=list)


class MockBackend:
    def __init__(self, load_delay: float = 0.6, step_delay: float = 0.03, fail_on_step: int | None = None) -> None:
        self.load_delay = load_delay
        self.step_delay = step_delay
        self.fail_on_step = fail_on_step

    def load_model(self, cfg: ExperimentConfig) -> LoadedModel:
        time.sleep(self.load_delay)
        model = SimpleMockModel(norm_stats={cfg.task_suite: {}, f"{cfg.task_suite}_no_noops": {}})
        model_cfg = make_model_cfg(cfg)
        resolved = cfg.unnorm_key or cfg.task_suite
        model_cfg.unnorm_key = resolved
        return LoadedModel(model=model, processor=object(), model_cfg=model_cfg, resolved_unnorm_key=resolved, device_info={"device": "mock"})

    def unload_model(self, model_state: LoadedModel | None) -> None:
        return None

    def inspect_task(self, cfg: ExperimentConfig, model_state: LoadedModel | None) -> TaskInspection:
        time.sleep(0.01)
        free = [
            {"name": "akita_black_bowl_1_joint0", "joint_id": 0, "qpos_addr": 0, "object_name": "akita_black_bowl_1", "score": 2},
            {"name": "plate_1_joint0", "joint_id": 1, "qpos_addr": 7, "object_name": "plate_1", "score": 1},
        ]
        return TaskInspection(
            task_description="put the black bowl on the plate",
            trial_count=4,
            free_joints=free,
            auto_target_joint="akita_black_bowl_1_joint0",
            preview_frame=self._frame(0, "inspect"),
        )

    def create_episode(self, cfg: ExperimentConfig, model_state: LoadedModel) -> EpisodeContext:
        if cfg.trial_id >= 4:
            raise ValueError("trial_id 4 is outside available initial states 0..3")
        free = [
            {"name": "akita_black_bowl_1_joint0", "joint_id": 0, "qpos_addr": 0, "object_name": "akita_black_bowl_1", "score": 2},
            {"name": "plate_1_joint0", "joint_id": 1, "qpos_addr": 7, "object_name": "plate_1", "score": 1},
        ]
        target = free[0]["name"] if cfg.target_joint == "auto" else cfg.target_joint
        return EpisodeContext(
            cfg=cfg,
            task_suite=object(),
            task=object(),
            initial_states=[0, 1, 2, 3],
            env=MockEnvState(),
            obs={"step": 0},
            task_description="put the black bowl on the plate",
            resize_size=(cfg.resolution, cfg.resolution),
            resolved_target_joint=target,
            available_target_joints=free,
            model_state=model_state,
        )

    def stabilize(self, ctx: EpisodeContext) -> tuple[dict[str, Any], float, bool, dict[str, Any], int]:
        ctx.obs = {"step": 0, "stabilized": True}
        return ctx.obs, 0.0, False, {"mock": True}, ctx.cfg.num_steps_wait

    def execute_policy_step(self, ctx: EpisodeContext, prompt: str) -> PolicyStepResult:
        step = int(ctx.env.policy_step)
        if self.fail_on_step is not None and step >= self.fail_on_step:
            raise RuntimeError(f"mock failure at step {step}")
        time.sleep(self.step_delay)
        raw = self._frame(step, prompt)
        ctx.env.policy_step += 1
        next_obs = {"step": ctx.env.policy_step, "prompt": prompt}
        done = ctx.env.policy_step >= ctx.cfg.max_steps
        reward = 1.0 if done else min(0.99, ctx.env.policy_step / max(ctx.cfg.max_steps, 1))
        ctx.obs = next_obs
        return PolicyStepResult(
            raw_frame=raw,
            raw_action=[float(step), 0.1, -0.1, 0.0, 0.2, -0.2, 1.0],
            env_action=[float(step), 0.1, -0.1, 0.0, 0.2, -0.2, -1.0],
            next_obs=next_obs,
            reward=float(reward),
            done=bool(done),
            info={"mock": True},
            inference_seconds=self.step_delay,
            env_step_seconds=0.001,
        )

    def apply_disturbance(self, ctx: EpisodeContext, joint: str, dx: float, dy: float) -> tuple[dict[str, Any], dict[str, Any], np.ndarray | None, int]:
        record = {
            "joint": joint,
            "joint_id": 0,
            "qpos_addr": 0,
            "before_qpos": [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            "after_qpos": [float(dx), float(dy), 0.0, 1.0, 0.0, 0.0, 0.0],
            "delta_xy": [float(dx), float(dy)],
            "applied_at": iso_now(),
            "refresh": {"method": "mock_refresh", "consumed_noop_env_step": False},
        }
        ctx.env.disturbances.append(record)
        ctx.obs = {"step": ctx.env.policy_step, "disturbed": True}
        return ctx.obs, record, self._frame(ctx.env.policy_step, "disturbed"), 0

    def save_state(self, ctx: EpisodeContext) -> Any:
        return {"policy_step": ctx.env.policy_step, "disturbances": list(ctx.env.disturbances)}

    def restore_state(self, ctx: EpisodeContext, state: Any) -> tuple[dict[str, Any], np.ndarray | None, int, dict[str, Any]]:
        ctx.env.policy_step = int(state["policy_step"])
        ctx.env.disturbances = list(state["disturbances"])
        ctx.obs = {"step": ctx.env.policy_step, "restored": True}
        return ctx.obs, self._frame(ctx.env.policy_step, "rollback"), 0, {"method": "mock_restore", "consumed_noop_env_step": False}

    def reset_episode(self, ctx: EpisodeContext) -> tuple[dict[str, Any], float, bool, dict[str, Any], int]:
        ctx.env.policy_step = 0
        ctx.obs = {"step": 0, "reset": True}
        return ctx.obs, 0.0, False, {"mock_reset": True}, ctx.cfg.num_steps_wait

    def close_episode(self, ctx: EpisodeContext | None) -> None:
        return None

    def _frame(self, step: int, label: str) -> np.ndarray:
        size = 256
        y, x = np.mgrid[0:size, 0:size]
        base = (x + y + step * 17) % 255
        frame = np.stack(
            [
                base,
                (x * 2 + step * 11) % 255,
                (y * 3 + len(label) * 13) % 255,
            ],
            axis=-1,
        ).astype(np.uint8)
        return frame


@dataclass
class SimpleMockModel:
    norm_stats: dict[str, Any]


class ExperimentController:
    def __init__(self, backend: RuntimeBackend | None = None) -> None:
        self.backend = backend or RealLiberoBackend()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="libero-dashboard")
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._commands: queue.Queue[ControlCommand] = queue.Queue()
        self._snapshot = DashboardSnapshot()
        self._latest_frame: np.ndarray | None = None
        self._model_state: LoadedModel | None = None
        self._future: Future | None = None
        self._paused = False
        self._step_tokens = 0
        self._stop_requested = False
        self._active = False
        self._recorder: EpisodeRecorder | None = None

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)

    def snapshot(self) -> tuple[np.ndarray | None, dict[str, Any]]:
        with self._lock:
            snap = asdict(self._snapshot)
            frame = None if self._latest_frame is None else self._latest_frame.copy()
        return frame, json_safe(snap)

    def request_model_load(self, checkpoint: str, task_suite: str = "libero_spatial", unnorm_key: str | None = None) -> str:
        with self._condition:
            if self._active:
                return "An episode is running; wait for it to finish before loading a model."
            if self._snapshot.controller_state == ControllerState.LOADING_MODEL.value:
                return "Model load is already in progress."
            if self._snapshot.model_loaded:
                return "A model is already loaded; unload it before switching checkpoints."
            cfg = ExperimentConfig(checkpoint=checkpoint, task_suite=task_suite, unnorm_key=unnorm_key)
            self._replace_snapshot(
                controller_state=ControllerState.LOADING_MODEL.value,
                message="Model load requested.",
                checkpoint=checkpoint,
                task_suite=task_suite,
                error=None,
                traceback_tail=None,
            )
            self._append_event_memory("model_load_requested", {})
            self._future = self._executor.submit(self._model_load_worker, cfg)
            return "Model load submitted."

    def request_unload_model(self) -> str:
        with self._condition:
            if self._active:
                return "Cannot unload while an episode is active."
            if self._snapshot.controller_state == ControllerState.LOADING_MODEL.value:
                return "Cannot unload while model loading is in progress."
            if not self._snapshot.model_loaded:
                return "No model is loaded."
            self.backend.unload_model(self._model_state)
            self._model_state = None
            self._latest_frame = None
            self._snapshot = DashboardSnapshot(message="Model unloaded.")
            return "Model unloaded."

    def request_task_inspect(self, cfg: ExperimentConfig) -> str:
        with self._condition:
            if not self._snapshot.model_loaded:
                return "Load a model before inspecting a task."
            if self._active:
                return "Cannot inspect while an episode is active."
            if self._snapshot.controller_state == ControllerState.INSPECTING_TASK.value:
                return "Task inspection is already in progress."
            self._replace_snapshot(
                controller_state=ControllerState.INSPECTING_TASK.value,
                message="Task inspection requested.",
                **self._cfg_fields(cfg),
            )
            self._future = self._executor.submit(self._inspect_worker, cfg)
            return "Task inspection submitted."

    def request_start(self, cfg: ExperimentConfig) -> str:
        with self._condition:
            if not self._snapshot.model_loaded or self._model_state is None:
                return "Load a model before starting an experiment."
            if self._active:
                return "An episode is already running."
            if self._snapshot.controller_state == ControllerState.LOADING_MODEL.value:
                return "Model is still loading."
            self._drain_commands()
            self._paused = False
            self._step_tokens = 0
            self._stop_requested = False
            self._active = True
            self._replace_snapshot(
                controller_state=ControllerState.STARTING.value,
                message="Episode start requested.",
                error=None,
                traceback_tail=None,
                paused=False,
                stop_requested=False,
                human_intervention=False,
                eligible_for_official_metrics=False,
                **self._cfg_fields(cfg),
            )
            self._future = self._executor.submit(self._episode_worker, cfg)
            return "Episode submitted."

    def request_pause_toggle(self) -> str:
        with self._condition:
            if not self._active:
                return "No active episode to pause or resume."
            if self._paused:
                self._paused = False
                self._replace_snapshot(paused=False, message="Resume requested; it will continue at the next policy-step boundary.")
                self._record_event("resume_requested", {})
                self._condition.notify_all()
                return "Resume requested."
            self._paused = True
            self._mark_human("pause_requested")
            self._replace_snapshot(paused=True, message="Pause requested; it takes effect at the next policy-step boundary.")
            self._record_event("pause_requested", {})
            self._condition.notify_all()
            return "Pause requested."

    def request_step_once(self) -> str:
        with self._condition:
            if not self._active:
                return "No active episode to step."
            self._paused = True
            self._step_tokens += 1
            self._mark_human("step_once_requested")
            self._replace_snapshot(paused=True, message="One policy step requested.")
            self._record_event("step_once_requested", {"pending_step_tokens": self._step_tokens})
            self._condition.notify_all()
            return "One policy step requested."

    def request_manual_disturbance(self, target_joint: str, dx: float, dy: float) -> str:
        with self._condition:
            if not self._active:
                return "No active episode to disturb."
            payload = {
                "target_joint": target_joint or "auto",
                "dx": float(dx),
                "dy": float(dy),
                "requested_at": iso_now(),
            }
            self._commands.put(ControlCommand(CommandType.MANUAL_DISTURBANCE, time.monotonic(), payload))
            self._mark_human("manual_disturbance_requested")
            self._record_event("manual_disturbance_requested", payload)
            self._replace_snapshot(message="Manual disturbance queued for the next safe boundary.")
            self._condition.notify_all()
            return "Manual disturbance queued."

    def request_stop(self) -> str:
        with self._condition:
            if not self._active:
                return "No active episode to stop."
            self._stop_requested = True
            self._commands.put(ControlCommand(CommandType.STOP, time.monotonic(), {"requested_at": iso_now()}))
            self._mark_human("stop_requested")
            self._replace_snapshot(stop_requested=True, message="Stop requested; saving at the next safe boundary.")
            self._record_event("stop_requested", {})
            self._condition.notify_all()
            return "Stop requested."

    def clear_completed_state(self) -> str:
        with self._condition:
            if self._active:
                return "Cannot clear while an episode is active."
            if self._snapshot.model_loaded:
                self._replace_snapshot(
                    controller_state=ControllerState.READY.value,
                    message="Ready.",
                    error=None,
                    traceback_tail=None,
                    done=False,
                    success=False,
                )
                return "Cleared completed state."
            self._snapshot = DashboardSnapshot(message="Idle.")
            return "Cleared."

    def wait_for_idle(self, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                state = self._snapshot.controller_state
                active = self._active
            if state not in {ControllerState.LOADING_MODEL.value, ControllerState.INSPECTING_TASK.value, ControllerState.STARTING.value, ControllerState.STABILIZING.value, ControllerState.RUNNING.value, ControllerState.PAUSED.value, ControllerState.STOPPING.value} and not active:
                return True
            time.sleep(0.02)
        return False

    def _model_load_worker(self, cfg: ExperimentConfig) -> None:
        try:
            model_state = self.backend.load_model(cfg)
            with self._condition:
                self._model_state = model_state
                device_info = model_state.device_info or {}
                self._replace_snapshot(
                    controller_state=ControllerState.READY.value,
                    message="Model loaded.",
                    model_loaded=True,
                    checkpoint=cfg.checkpoint,
                    resolved_unnorm_key=model_state.resolved_unnorm_key,
                    device=device_info.get("device"),
                    device_info=device_info,
                    task_suite=cfg.task_suite,
                )
                self._append_event_memory("model_loaded", {"resolved_unnorm_key": model_state.resolved_unnorm_key})
        except Exception as exc:
            with self._condition:
                self._replace_snapshot(
                    controller_state=ControllerState.FAILED.value,
                    message="Model load failed.",
                    model_loaded=False,
                    error=f"{type(exc).__name__}: {exc}",
                    traceback_tail=short_traceback(),
                )
                self._append_event_memory("model_load_failed", {"error": repr(exc)})

    def _inspect_worker(self, cfg: ExperimentConfig) -> None:
        try:
            result = self.backend.inspect_task(cfg, self._model_state)
            annotated = result.preview_frame
            if annotated is not None:
                annotated = draw_overlay(
                    annotated,
                    {
                        "mode": cfg.mode,
                        "task_id": cfg.task_id,
                        "trial_id": cfg.trial_id,
                        "state": "INSPECT",
                        "policy_step": 0,
                        "reward": 0.0,
                        "target_joint": result.auto_target_joint or "n/a",
                    },
                )
            with self._condition:
                self._latest_frame = None if annotated is None else annotated.copy()
                self._replace_snapshot(
                    controller_state=ControllerState.READY.value,
                    message="Task inspected.",
                    task_description=result.task_description,
                    original_prompt=result.task_description,
                    current_prompt=result.task_description,
                    trial_count=result.trial_count,
                    available_target_joints=result.free_joints,
                    resolved_target_joint=result.auto_target_joint,
                    error=None,
                    traceback_tail=None,
                    **self._cfg_fields(cfg),
                )
                self._append_event_memory("task_inspected", {"task_description": result.task_description, "trial_count": result.trial_count})
        except Exception as exc:
            with self._condition:
                self._replace_snapshot(
                    controller_state=ControllerState.READY.value if self._snapshot.model_loaded else ControllerState.FAILED.value,
                    message="Task inspection failed.",
                    error=f"{type(exc).__name__}: {exc}",
                    traceback_tail=short_traceback(),
                )

    def _episode_worker(self, cfg: ExperimentConfig) -> None:
        ctx: EpisodeContext | None = None
        recorder: EpisodeRecorder | None = None
        actions: list[dict[str, Any]] = []
        disturbances: list[dict[str, Any]] = []
        recovery_state: dict[str, Any] | None = None
        done = False
        success = False
        reward = 0.0
        total_policy_steps = 0
        phase_policy_step = 0
        reset_count = 0
        extra_env_steps = 0
        disturbance_done = False
        stopped_by_verifier = False
        current_prompt: str | None = None
        original_prompt: str | None = None
        started = time.monotonic()
        terminal_state_value: str | None = None
        terminal_message: str | None = None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = Path(cfg.out_dir) / f"{timestamp}_task{cfg.task_id}_{cfg.mode}"
        recorder = EpisodeRecorder(run_dir, cfg)
        with self._condition:
            self._recorder = recorder
            self._replace_snapshot(
                run_dir=str(run_dir),
                raw_video_path=str(recorder.raw_video_path),
                annotated_video_path=str(recorder.annotated_video_path),
                episode_json_path=str(recorder.episode_path),
                events_jsonl_path=str(recorder.events_path),
                **self._cfg_fields(cfg),
            )
            self._record_event("episode_started", {"config": asdict(cfg)})

        try:
            ctx = self.backend.create_episode(cfg, self._model_state)  # type: ignore[arg-type]
            original_prompt = ctx.task_description
            current_prompt = original_prompt
            with self._condition:
                self._replace_snapshot(
                    controller_state=ControllerState.STABILIZING.value,
                    message="Stabilizing environment.",
                    task_description=ctx.task_description,
                    original_prompt=original_prompt,
                    current_prompt=current_prompt,
                    resolved_target_joint=ctx.resolved_target_joint,
                    available_target_joints=ctx.available_target_joints,
                    trial_count=len(ctx.initial_states),
                    elapsed_seconds=0.0,
                )
            _, reward, done, info, extra = self.backend.stabilize(ctx)
            extra_env_steps += extra
            self._record_event("stabilization_finished", {"extra_env_steps": extra, "reward": reward, "done": done, "info": info})
            with self._condition:
                self._replace_snapshot(
                    controller_state=ControllerState.RUNNING.value,
                    message="Running.",
                    reward=reward,
                    done=done,
                    extra_env_steps=extra_env_steps,
                )

            while total_policy_steps < cfg.max_steps and not done:
                command_status = self._process_commands(ctx, disturbances)
                if command_status == StepPermission.STOP:
                    break

                auto_status = self._maybe_apply_auto_disturbance(
                    cfg=cfg,
                    ctx=ctx,
                    disturbances=disturbances,
                    total_policy_steps=total_policy_steps,
                    phase_policy_step=phase_policy_step,
                    disturbance_done=disturbance_done,
                    current_prompt=current_prompt,
                )
                if auto_status["applied"]:
                    disturbance_done = True
                    extra_env_steps += int(auto_status.get("extra_env_steps", 0))
                    recovery_state = auto_status.get("recovery_state", recovery_state)
                    if auto_status.get("current_prompt"):
                        current_prompt = auto_status["current_prompt"]
                    if auto_status.get("reset"):
                        phase_policy_step = 0
                        reset_count += 1
                        extra_env_steps += int(auto_status.get("reset_extra_env_steps", 0))
                        self._replace_snapshot(reset_count=reset_count, phase_policy_step=phase_policy_step, extra_env_steps=extra_env_steps)
                        continue
                    if auto_status.get("verifier_stop"):
                        stopped_by_verifier = True
                        done = True
                        success = False
                        self._record_event("verifier_stopped", auto_status.get("recovery_state") or {})
                        break

                permission = self._wait_for_step_permission()
                if permission == StepPermission.STOP:
                    break
                if permission == StepPermission.CHECK_COMMANDS:
                    continue

                result = self.backend.execute_policy_step(ctx, current_prompt or ctx.task_description)
                done = bool(result.done)
                reward = float(result.reward)
                total_policy_steps += 1
                phase_policy_step += 1
                episode_status = extract_episode_status(reward, done, result.info, total_policy_steps, cfg.max_steps)
                success = episode_status.success
                annotated = draw_overlay(
                    result.raw_frame.copy(),
                    {
                        "mode": cfg.mode,
                        "task_id": cfg.task_id,
                        "trial_id": cfg.trial_id,
                        "state": "PAUSED" if self._paused else "RUNNING",
                        "policy_step": total_policy_steps,
                        "reward": reward,
                        "target_joint": ctx.resolved_target_joint,
                        "recovery_prompt": current_prompt != original_prompt,
                    },
                )
                recorder.append_frames(result.raw_frame, annotated)
                action_row = {
                    "t": total_policy_steps - 1,
                    "phase_policy_step": phase_policy_step - 1,
                    "task_prompt": current_prompt,
                    "raw_action": result.raw_action,
                    "env_action": result.env_action,
                    "reward": reward,
                    "done": done,
                    "inference_seconds": result.inference_seconds,
                    "env_step_seconds": result.env_step_seconds,
                }
                actions.append(action_row)
                with self._condition:
                    self._latest_frame = annotated.copy()
                    self._replace_snapshot(
                        controller_state=ControllerState.RUNNING.value if not self._paused else ControllerState.PAUSED.value,
                        message="Policy step completed.",
                        policy_step=total_policy_steps,
                        total_policy_steps=total_policy_steps,
                        phase_policy_step=phase_policy_step,
                        reward=reward,
                        done=done,
                        success=success,
                        raw_action=result.raw_action,
                        env_action=result.env_action,
                        inference_seconds=result.inference_seconds,
                        env_step_seconds=result.env_step_seconds,
                        elapsed_seconds=time.monotonic() - started,
                        current_prompt=current_prompt,
                        recovery_state=recovery_state,
                        reset_count=reset_count,
                        extra_env_steps=extra_env_steps,
                    )
                self._record_event("policy_step_completed", action_row)

            final_state = ControllerState.ABORTED if self._stop_requested else ControllerState.COMPLETED
            event_name = "episode_aborted" if self._stop_requested else "episode_completed"
            if stopped_by_verifier:
                final_state = ControllerState.COMPLETED
                event_name = "episode_completed"
            terminal_state_value = final_state.value
            terminal_message = "Episode stopped and saved." if self._stop_requested else "Episode completed."
            with self._condition:
                self._active = False
                self._replace_snapshot(
                    controller_state=ControllerState.STOPPING.value,
                    message="Finalizing episode outputs.",
                    done=done,
                    success=success,
                    stopped_by_verifier=stopped_by_verifier,
                    elapsed_seconds=time.monotonic() - started,
                    current_prompt=current_prompt,
                    recovery_state=recovery_state,
                    reset_count=reset_count,
                    extra_env_steps=extra_env_steps,
                )
            self._record_event(event_name, {"success": success, "stopped_by_verifier": stopped_by_verifier})
        except Exception as exc:
            if recorder is not None:
                recorder.log_exception("episode_failed")
            terminal_state_value = ControllerState.FAILED.value
            terminal_message = "Episode failed."
            with self._condition:
                self._active = False
                self._replace_snapshot(
                    controller_state=ControllerState.STOPPING.value,
                    message="Episode failed; finalizing partial outputs.",
                    error=f"{type(exc).__name__}: {exc}",
                    traceback_tail="".join(traceback.format_exc().splitlines(keepends=True)[-12:]),
                    elapsed_seconds=time.monotonic() - started,
                )
            self._record_event("episode_failed", {"error": repr(exc)})
        finally:
            try:
                self.backend.close_episode(ctx)
            finally:
                video_status = recorder.close() if recorder is not None else None
                with self._condition:
                    self._active = False
                    self._paused = False
                    self._step_tokens = 0
                    self._stop_requested = False
                    if video_status is not None:
                        self._replace_snapshot(
                            raw_video_path=video_status.raw_video_path,
                            annotated_video_path=video_status.annotated_video_path,
                            paused=False,
                            stop_requested=False,
                        )
                    episode_payload = {
                        "config": asdict(cfg),
                        "task_description": original_prompt,
                        "original_prompt": original_prompt,
                        "current_prompt": current_prompt,
                        "target_joint": self._snapshot.resolved_target_joint,
                        "available_target_joints": self._snapshot.available_target_joints,
                        "success": self._snapshot.success,
                        "done": self._snapshot.done,
                        "stopped_by_verifier": self._snapshot.stopped_by_verifier,
                        "final_reward": self._snapshot.reward,
                        "num_policy_steps": self._snapshot.total_policy_steps,
                        "phase_policy_step": self._snapshot.phase_policy_step,
                        "reset_count": self._snapshot.reset_count,
                        "extra_env_steps": self._snapshot.extra_env_steps,
                        "disturbances": disturbances,
                        "last_disturbance": self._snapshot.last_disturbance,
                        "recovery_state": self._snapshot.recovery_state,
                        "actions": actions,
                        "human_intervention": self._snapshot.human_intervention,
                        "eligible_for_official_metrics": False,
                        "run_dir": self._snapshot.run_dir,
                        "raw_video_path": self._snapshot.raw_video_path,
                        "annotated_video_path": self._snapshot.annotated_video_path,
                        "events_jsonl_path": self._snapshot.events_jsonl_path,
                        "episode_json_path": self._snapshot.episode_json_path,
                        "error": self._snapshot.error,
                    }
                if recorder is not None:
                    recorder.write_episode(episode_payload)
                with self._condition:
                    if terminal_state_value is not None:
                        self._replace_snapshot(
                            controller_state=terminal_state_value,
                            message=terminal_message or self._snapshot.message,
                            paused=False,
                            stop_requested=False,
                        )
                    self._recorder = None

    def _maybe_apply_auto_disturbance(
        self,
        *,
        cfg: ExperimentConfig,
        ctx: EpisodeContext,
        disturbances: list[dict[str, Any]],
        total_policy_steps: int,
        phase_policy_step: int,
        disturbance_done: bool,
        current_prompt: str,
    ) -> dict[str, Any]:
        if disturbance_done:
            return {"applied": False}
        if not cfg.enable_auto_disturbance or cfg.mode == "clean":
            return {"applied": False}
        if phase_policy_step != cfg.disturbance_step:
            return {"applied": False}
        if self._snapshot.disturbance_count > 0 and not cfg.allow_multiple_disturbances:
            self._record_event(
                "disturbance_skipped",
                {"reason": "disturbance_already_applied", "source": "auto_config"},
            )
            return {"applied": False}

        saved_state = None
        if cfg.mode == "oracle_rollback":
            saved_state = self.backend.save_state(ctx)

        obs, record, frame, extra = self.backend.apply_disturbance(ctx, ctx.resolved_target_joint, cfg.dx, cfg.dy)
        record.update(
            {
                "source": "auto_config",
                "policy_step": total_policy_steps,
                "phase_policy_step": phase_policy_step,
                "requested_at": None,
                "actual_joint": ctx.resolved_target_joint,
            }
        )
        disturbances.append(record)
        self._disturbance_applied(record, frame, extra)

        result: dict[str, Any] = {"applied": True, "extra_env_steps": extra}
        if cfg.mode == "verifier_stop":
            result["verifier_stop"] = True
            result["recovery_state"] = verifier_stop_state()
            with self._condition:
                self._replace_snapshot(recovery_state=result["recovery_state"], stopped_by_verifier=True)
            return result
        if cfg.mode in {"structured_relocalize_prompt", "stage_backtrack_subgoal"}:
            prompt, recovery = build_recovery_prompt(cfg.mode, ctx.task_description, ctx.resolved_target_joint)
            self._record_event("prompt_changed", {"old_prompt": current_prompt, "new_prompt": prompt, "recovery": recovery})
            with self._condition:
                self._replace_snapshot(current_prompt=prompt, recovery_state=recovery)
            result["current_prompt"] = prompt
            result["recovery_state"] = recovery
            return result
        if cfg.mode == "full_reset_replan":
            self._record_event("full_reset_started", {"source": "auto_config"})
            _, reward, done, info, reset_extra = self.backend.reset_episode(ctx)
            recovery = {
                "type": "full_reset_replan",
                "progress_preserved": False,
                "extra_wait_steps": cfg.num_steps_wait,
                "reward_after_reset": reward,
                "done_after_reset": done,
                "info_after_reset": info,
            }
            with self._condition:
                self._replace_snapshot(current_prompt=ctx.task_description, recovery_state=recovery, reward=reward, done=done)
            result.update({"reset": True, "reset_extra_env_steps": reset_extra, "recovery_state": recovery, "current_prompt": ctx.task_description})
            return result
        if cfg.mode == "oracle_rollback":
            _, frame, rollback_extra, refresh = self.backend.restore_state(ctx, saved_state)
            recovery = {
                "type": "oracle_rollback_to_pre_disturbance_state",
                "progress_preserved": "sim_state_restored_but_external_disturbance_undone",
                "refresh": refresh,
            }
            self._record_event("rollback_applied", recovery)
            if frame is not None:
                with self._condition:
                    self._latest_frame = draw_overlay(
                        frame,
                        {
                            "mode": cfg.mode,
                            "task_id": cfg.task_id,
                            "trial_id": cfg.trial_id,
                            "state": "ROLLBACK",
                            "policy_step": total_policy_steps,
                            "reward": self._snapshot.reward,
                            "target_joint": ctx.resolved_target_joint,
                            "recovery_prompt": False,
                        },
                    )
            result.update({"extra_env_steps": extra + rollback_extra, "recovery_state": recovery})
            with self._condition:
                self._replace_snapshot(recovery_state=recovery)
            return result
        return result

    def _process_commands(self, ctx: EpisodeContext, disturbances: list[dict[str, Any]]) -> StepPermission:
        processed = False
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                break
            processed = True
            if command.type == CommandType.STOP:
                with self._condition:
                    self._stop_requested = True
                    self._replace_snapshot(controller_state=ControllerState.STOPPING.value, stop_requested=True)
                return StepPermission.STOP
            if command.type == CommandType.MANUAL_DISTURBANCE:
                cfg = ctx.cfg
                if self._snapshot.disturbance_count > 0 and not cfg.allow_multiple_disturbances:
                    self._record_event("disturbance_skipped", {"reason": "disturbance_already_applied", "source": "manual_ui", "request": command.payload})
                    continue
                target = command.payload.get("target_joint") or "auto"
                actual_joint = ctx.resolved_target_joint if target == "auto" else str(target)
                obs, record, frame, extra = self.backend.apply_disturbance(
                    ctx,
                    actual_joint,
                    float(command.payload.get("dx", cfg.dx)),
                    float(command.payload.get("dy", cfg.dy)),
                )
                record.update(
                    {
                        "source": "manual_ui",
                        "request": command.payload,
                        "request_monotonic": command.created_at,
                        "applied_monotonic": time.monotonic(),
                        "policy_step": self._snapshot.total_policy_steps,
                        "phase_policy_step": self._snapshot.phase_policy_step,
                        "actual_joint": actual_joint,
                    }
                )
                disturbances.append(record)
                self._disturbance_applied(record, frame, extra)
        return StepPermission.CHECK_COMMANDS if processed else StepPermission.RUN

    def _disturbance_applied(self, record: dict[str, Any], frame: np.ndarray | None, extra_env_steps: int) -> None:
        self._record_event("disturbance_applied", record)
        refresh = record.get("refresh")
        if refresh:
            self._record_event("observation_refreshed", refresh)
        with self._condition:
            annotated = None
            if frame is not None:
                annotated = draw_overlay(
                    frame,
                    {
                        "mode": self._snapshot.mode,
                        "task_id": self._snapshot.task_id,
                        "trial_id": self._snapshot.trial_id,
                        "state": "DISTURBED",
                        "policy_step": self._snapshot.total_policy_steps,
                        "reward": self._snapshot.reward,
                        "target_joint": record.get("actual_joint") or record.get("joint"),
                        "recovery_prompt": self._snapshot.current_prompt != self._snapshot.original_prompt,
                    },
                )
                self._latest_frame = annotated.copy()
            self._replace_snapshot(
                disturbance_applied=True,
                disturbance_count=self._snapshot.disturbance_count + 1,
                last_disturbance=record,
                extra_env_steps=self._snapshot.extra_env_steps + int(extra_env_steps),
                message="Disturbance applied.",
            )

    def _wait_for_step_permission(self) -> StepPermission:
        with self._condition:
            while True:
                if self._stop_requested:
                    return StepPermission.STOP
                if not self._commands.empty():
                    return StepPermission.CHECK_COMMANDS
                if self._step_tokens > 0:
                    self._step_tokens -= 1
                    self._replace_snapshot(controller_state=ControllerState.RUNNING.value, paused=True, message="Executing one requested policy step.")
                    return StepPermission.RUN
                if not self._paused:
                    self._replace_snapshot(controller_state=ControllerState.RUNNING.value, paused=False)
                    return StepPermission.RUN
                if self._snapshot.controller_state != ControllerState.PAUSED.value:
                    self._replace_snapshot(controller_state=ControllerState.PAUSED.value, paused=True, message="Paused at policy-step boundary.")
                    self._record_event("paused", {})
                self._condition.wait(timeout=0.1)

    def _replace_snapshot(self, **kwargs: Any) -> None:
        data = asdict(self._snapshot)
        data.update(json_safe(kwargs))
        self._snapshot = DashboardSnapshot(**data)

    def _cfg_fields(self, cfg: ExperimentConfig) -> dict[str, Any]:
        return {
            "checkpoint": cfg.checkpoint,
            "task_suite": cfg.task_suite,
            "task_id": cfg.task_id,
            "trial_id": cfg.trial_id,
            "mode": cfg.mode,
            "max_steps": cfg.max_steps,
        }

    def _record_event(self, event: str, payload: dict[str, Any]) -> None:
        with self._condition:
            if self._recorder is not None:
                row = self._recorder.event(event, self._snapshot.total_policy_steps, self._snapshot.phase_policy_step, payload)
            else:
                row = {
                    "wall_time": 0.0,
                    "timestamp": iso_now(),
                    "event": event,
                    "policy_step": self._snapshot.total_policy_steps,
                    "phase_policy_step": self._snapshot.phase_policy_step,
                    "payload": json_safe(payload),
                }
            self._append_event_row(row)

    def _append_event_memory(self, event: str, payload: dict[str, Any]) -> None:
        with self._condition:
            row = {
                "wall_time": 0.0,
                "timestamp": iso_now(),
                "event": event,
                "policy_step": self._snapshot.total_policy_steps,
                "phase_policy_step": self._snapshot.phase_policy_step,
                "payload": json_safe(payload),
            }
            self._append_event_row(row)

    def _append_event_row(self, row: dict[str, Any]) -> None:
        events = list(self._snapshot.last_events)
        events.append(json_safe(row))
        self._replace_snapshot(last_events=events[-50:])

    def _mark_human(self, reason: str) -> None:
        self._replace_snapshot(human_intervention=True, eligible_for_official_metrics=False)

    def _drain_commands(self) -> None:
        while True:
            try:
                self._commands.get_nowait()
            except queue.Empty:
                return


__all__ = [
    "CANONICAL_MODES",
    "CommandType",
    "ControlCommand",
    "ControllerState",
    "DashboardSnapshot",
    "ExperimentConfig",
    "ExperimentController",
    "MockBackend",
    "RealLiberoBackend",
]
