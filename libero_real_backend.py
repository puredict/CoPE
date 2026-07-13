"""Real LIBERO/OpenVLA backend for the dashboard single-worker controller.

This module is intentionally import-light: importing it must not load OpenVLA,
LIBERO, robosuite, MuJoCo, or torch.  Heavy runtime objects are created only by
``RealExperimentBackend.load`` and ``RealExperimentBackend.reset``, which the
dashboard controller calls from its single worker thread.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import time
from types import SimpleNamespace
from typing import Any

import numpy as np

from libero_experiment_core import (
    ExperimentConfig,
    build_recovery_prompt,
    create_libero_env,
    execute_policy_step,
    extract_episode_status,
    frame_from_obs,
    get_benchmark_suite,
    get_device_summary,
    get_dummy_action,
    get_image_resize_size,
    get_joint_qpos,
    json_safe,
    load_model_and_processor,
    make_budget_report,
    move_free_joint_xy,
    refresh_observation_after_sim_change,
    select_target_joint,
    set_seed,
    unload_torch_model_refs,
    validate_task_and_trial,
)


@dataclass
class RealStepResult:
    policy_step: int
    environment_step: int
    raw_frame: np.ndarray
    annotated_frame: np.ndarray
    raw_action: list[float]
    env_action: list[float]
    reward: float
    done: bool
    success: bool
    termination_reason: str | None
    current_prompt: str
    object_position: list[float] | None
    inference_seconds: float
    env_step_seconds: float
    info: dict[str, Any]
    episode_status: dict[str, Any]
    policy_budget_remaining: int
    fresh_observation: dict[str, Any] | None = None


@dataclass
class _EpisodeRuntime:
    config: ExperimentConfig
    task: Any
    initial_state: Any
    env: Any
    obs: dict[str, Any]
    task_description: str
    target_selection: Any
    resize_size: Any
    original_prompt: str
    current_prompt: str
    policy_step: int = 0
    environment_step: int = 0
    reward: float = 0.0
    done: bool = False
    info: dict[str, Any] = field(default_factory=dict)
    disturbance_count: int = 0
    auto_disturbance_count: int = 0
    manual_disturbance_count: int = 0
    last_disturbance: dict[str, Any] | None = None
    last_fresh_observation: dict[str, Any] | None = None
    recovery_state: dict[str, Any] | None = None
    raw_action: list[float] = field(default_factory=list)
    env_action: list[float] = field(default_factory=list)
    latest_frame: np.ndarray | None = None
    initial_target_qpos: list[float] | None = None
    policy_start_target_qpos: list[float] | None = None
    extra_environment_steps: int = 0


class RealExperimentBackend:
    """Worker-owned runtime bridge to the validated LIBERO/OpenVLA helpers."""

    backend_name = "real"

    def __init__(self) -> None:
        self.loaded = False
        self.config: ExperimentConfig | None = None
        self.model = None
        self.processor = None
        self.model_cfg: SimpleNamespace | None = None
        self.resolved_unnorm_key: str | None = None
        self.task_suite = None
        self.runtime: _EpisodeRuntime | None = None
        self.device_summary: dict[str, Any] = {"device": "unloaded", "cuda_available": False}

    @property
    def current_prompt(self) -> str:
        return self.runtime.current_prompt if self.runtime else ""

    @property
    def original_prompt(self) -> str:
        return self.runtime.original_prompt if self.runtime else ""

    @property
    def task_text(self) -> str:
        return self.runtime.task_description if self.runtime else ""

    @property
    def disturbance_count(self) -> int:
        return self.runtime.disturbance_count if self.runtime else 0

    @property
    def last_disturbance(self) -> dict[str, Any] | None:
        return json_safe(self.runtime.last_disturbance) if self.runtime and self.runtime.last_disturbance else None

    @property
    def resolved_target_joint(self) -> str:
        if not self.runtime or not self.runtime.target_selection.selected_joint:
            return ""
        return str(self.runtime.target_selection.selected_joint)

    @property
    def object_position(self) -> list[float] | None:
        if not self.runtime or not self.runtime.target_selection.selected_joint:
            return None
        try:
            qpos = get_joint_qpos(self.runtime.env, self.runtime.target_selection.selected_joint)
            return [float(qpos[0]), float(qpos[1]), float(qpos[2])]
        except Exception:
            return None

    @property
    def latest_frame(self) -> np.ndarray | None:
        if self.runtime and self.runtime.latest_frame is not None:
            return np.asarray(self.runtime.latest_frame, dtype=np.uint8)
        return None

    def load(self, config: ExperimentConfig | dict[str, Any] | str) -> dict[str, Any]:
        cfg = self._coerce_config(config)
        set_seed(cfg.seed)
        self.model, self.processor, self.model_cfg, self.resolved_unnorm_key = load_model_and_processor(cfg)
        self.task_suite = get_benchmark_suite(cfg.task_suite)
        self.config = cfg
        self.loaded = True
        self.device_summary = get_device_summary()
        return {
            "checkpoint": cfg.checkpoint,
            "resolved_unnorm_key": self.resolved_unnorm_key,
            "device": self.device_summary.get("device", "unknown"),
            "device_summary": self.device_summary,
            "backend": self.backend_name,
            "task_suite": cfg.task_suite,
        }

    def load_model(self, checkpoint: str = "") -> dict[str, Any]:
        base = self.config or ExperimentConfig(checkpoint=checkpoint or "")
        cfg = ExperimentConfig(**{**asdict(base), "checkpoint": checkpoint or base.checkpoint})
        return self.load(cfg)

    def inspect_task(self, config: ExperimentConfig) -> dict[str, Any]:
        cfg = self._coerce_config(config)
        task_suite = self.task_suite or get_benchmark_suite(cfg.task_suite)
        initial_states = validate_task_and_trial(task_suite, cfg)
        task = task_suite.get_task(cfg.task_id)
        env, task_description = create_libero_env(task, cfg)
        try:
            env.reset()
            obs = env.set_init_state(initial_states[cfg.trial_id])
            target_selection = select_target_joint(env, task_description, cfg.target_joint)
            frame = frame_from_obs(obs, cfg.resolution)
            return {
                "task_text": task_description,
                "available_trials": len(initial_states),
                "available_target_joints": [item["name"] for item in target_selection.candidates],
                "target_selection": json_safe(target_selection),
                "resolved_target_joint": target_selection.selected_joint,
                "target_position": get_joint_qpos(env, target_selection.selected_joint)
                if target_selection.selected_joint
                else None,
                "preview_frame": frame,
            }
        finally:
            self._close_env(env)

    def reset(self, task: Any = None, initial_state: Any = None, seed: int | None = None, config: ExperimentConfig | None = None) -> dict[str, Any]:
        if not self.loaded or self.model is None or self.processor is None or self.model_cfg is None:
            raise RuntimeError("Real backend must be loaded before reset().")
        cfg = self._coerce_config(config or self.config)
        if seed is not None:
            cfg = ExperimentConfig(**{**asdict(cfg), "seed": int(seed)})
        set_seed(cfg.seed)
        if self.runtime is not None:
            self._close_env(self.runtime.env)
            self.runtime = None

        task_suite = self.task_suite or get_benchmark_suite(cfg.task_suite)
        initial_states = validate_task_and_trial(task_suite, cfg)
        selected_task = task if task is not None else task_suite.get_task(cfg.task_id)
        selected_initial_state = initial_state if initial_state is not None else initial_states[cfg.trial_id]
        env, task_description = create_libero_env(selected_task, cfg)
        resize_size = get_image_resize_size(self.model_cfg)
        env.reset()
        obs = env.set_init_state(selected_initial_state)
        target_selection = select_target_joint(env, task_description, cfg.target_joint)
        if target_selection.selected_joint is None:
            raise ValueError(f"target selection did not produce a joint: {target_selection.reason}")
        initial_target_qpos = get_joint_qpos(env, target_selection.selected_joint)
        reward = 0.0
        done = False
        info: dict[str, Any] = {}
        for _ in range(cfg.num_steps_wait):
            obs, reward, done, info = env.step(get_dummy_action(self.model_cfg.model_family))
        frame = frame_from_obs(obs, resize_size)
        self.runtime = _EpisodeRuntime(
            config=cfg,
            task=selected_task,
            initial_state=selected_initial_state,
            env=env,
            obs=obs,
            task_description=task_description,
            target_selection=target_selection,
            resize_size=resize_size,
            original_prompt=task_description,
            current_prompt=task_description,
            environment_step=cfg.num_steps_wait,
            reward=float(reward),
            done=bool(done),
            info=json_safe(info),
            latest_frame=frame,
            initial_target_qpos=initial_target_qpos,
            policy_start_target_qpos=get_joint_qpos(env, target_selection.selected_joint),
        )
        return {
            "task_text": task_description,
            "original_prompt": task_description,
            "current_prompt": task_description,
            "resolved_target_joint": target_selection.selected_joint,
            "available_target_joints": [item["name"] for item in target_selection.candidates],
            "target_selection": json_safe(target_selection),
            "target_position": get_joint_qpos(env, target_selection.selected_joint),
            "initial_target_qpos": initial_target_qpos,
            "frame": frame,
            "fresh_observation": None,
        }

    def start_episode(self, config: ExperimentConfig) -> dict[str, Any]:
        return self.reset(config=config)

    def should_auto_disturb(self, config: ExperimentConfig, policy_step: int) -> bool:
        cfg = self._coerce_config(config)
        if cfg.mode == "clean" or not cfg.enable_auto_disturbance:
            return False
        if int(policy_step) != cfg.disturbance_step:
            return False
        if self.runtime and self.runtime.auto_disturbance_count > 0:
            return False
        return True

    def apply_disturbance(
        self,
        config: ExperimentConfig | None = None,
        *,
        policy_step: int | None = None,
        source: str = "manual_ui",
        target_joint: str | None = None,
        dx: float | None = None,
        dy: float | None = None,
    ) -> dict[str, Any]:
        runtime = self._require_runtime()
        cfg = self._coerce_config(config or runtime.config)
        if runtime.disturbance_count > 0 and not cfg.allow_multiple_disturbances:
            return {
                "applied": False,
                "reason": "disturbance_already_applied",
                "source": source,
                "policy_step": runtime.policy_step if policy_step is None else int(policy_step),
                "disturbance_count": runtime.disturbance_count,
            }

        requested = target_joint or cfg.target_joint
        joint = runtime.target_selection.selected_joint if requested == "auto" else requested
        if not joint:
            raise ValueError("No target joint selected for disturbance.")
        delta_x = float(cfg.dx if dx is None else dx)
        delta_y = float(cfg.dy if dy is None else dy)
        step = runtime.policy_step if policy_step is None else int(policy_step)
        disturbance = move_free_joint_xy(runtime.env, joint, delta_x, delta_y)
        disturbance.update(
            {
                "timestamp": disturbance.get("applied_at"),
                "source": source,
                "policy_step": step,
                "requested_target_joint": requested,
                "delta_xyz_actual": [
                    float(disturbance["after_qpos"][i] - disturbance["before_qpos"][i]) for i in range(3)
                ],
                "disturbance_count": runtime.disturbance_count + 1,
            }
        )
        runtime.obs, refresh = refresh_observation_after_sim_change(runtime.env, self.model_cfg)
        runtime.extra_environment_steps += int(bool(refresh.get("consumed_noop_env_step")))
        runtime.last_fresh_observation = refresh
        runtime.latest_frame = frame_from_obs(runtime.obs, runtime.resize_size)
        runtime.disturbance_count += 1
        if source == "manual_ui":
            runtime.manual_disturbance_count += 1
        else:
            runtime.auto_disturbance_count += 1

        new_prompt, recovery_state = build_recovery_prompt(cfg.mode, runtime.original_prompt, joint)
        prompt_changed = new_prompt != runtime.current_prompt
        runtime.current_prompt = new_prompt
        runtime.recovery_state = recovery_state
        disturbance["refresh"] = refresh
        disturbance["prompt_changed"] = prompt_changed
        disturbance["current_prompt"] = runtime.current_prompt
        runtime.last_disturbance = json_safe(disturbance)
        return json_safe(runtime.last_disturbance)

    def step_once(self) -> RealStepResult:
        runtime = self._require_runtime()
        cfg = runtime.config
        result = execute_policy_step(
            cfg=self.model_cfg,
            model=self.model,
            processor=self.processor,
            env=runtime.env,
            obs=runtime.obs,
            prompt=runtime.current_prompt,
            resize_size=runtime.resize_size,
        )
        runtime.policy_step += 1
        runtime.environment_step += 1
        runtime.obs = result.next_obs
        runtime.reward = float(result.reward)
        runtime.done = bool(result.done)
        runtime.info = json_safe(result.info)
        runtime.raw_action = list(result.raw_action)
        runtime.env_action = list(result.env_action)
        runtime.latest_frame = np.asarray(result.raw_frame, dtype=np.uint8)
        episode_status = extract_episode_status(
            runtime.reward,
            runtime.done,
            runtime.info,
            runtime.policy_step,
            cfg.max_steps,
        )
        if episode_status.success or episode_status.timeout or episode_status.simulator_error or episode_status.stopped:
            runtime.done = True
        budget = make_budget_report(
            policy_step_budget=cfg.max_steps,
            warmup_simulator_steps=cfg.num_steps_wait,
            policy_inference_steps=runtime.policy_step,
            extra_environment_steps=runtime.extra_environment_steps,
            pre_disturbance_policy_steps=min(runtime.policy_step, cfg.disturbance_step)
            if runtime.disturbance_count
            else runtime.policy_step,
            reset_count=0,
            rollback_count=0,
            success=episode_status.success,
        )
        runtime.environment_step = budget.environment_control_steps
        annotated = self._overlay(result.raw_frame, episode_status.status)
        return RealStepResult(
            policy_step=runtime.policy_step,
            environment_step=budget.environment_control_steps,
            raw_frame=result.raw_frame,
            annotated_frame=annotated,
            raw_action=list(result.raw_action),
            env_action=list(result.env_action),
            reward=runtime.reward,
            done=runtime.done,
            success=episode_status.success,
            termination_reason=episode_status.status if runtime.done else None,
            current_prompt=runtime.current_prompt,
            object_position=self.object_position,
            inference_seconds=result.inference_seconds,
            env_step_seconds=result.env_step_seconds,
            info=runtime.info,
            episode_status=json_safe(episode_status),
            policy_budget_remaining=max(0, cfg.max_steps - runtime.policy_step),
            fresh_observation=runtime.last_fresh_observation,
        )

    def step(self, config: ExperimentConfig, *, policy_step: int, paused: bool = False) -> RealStepResult:
        return self.step_once()

    def get_snapshot(self) -> dict[str, Any]:
        runtime = self.runtime
        if runtime is None:
            return {
                "backend": self.backend_name,
                "model_loaded": self.loaded,
                "device_summary": self.device_summary,
            }
        status = extract_episode_status(
            runtime.reward,
            runtime.done,
            runtime.info,
            runtime.policy_step,
            runtime.config.max_steps,
        )
        return {
            "backend": self.backend_name,
            "model_loaded": self.loaded,
            "checkpoint": runtime.config.checkpoint,
            "resolved_unnorm_key": self.resolved_unnorm_key,
            "task_suite": runtime.config.task_suite,
            "task_id": runtime.config.task_id,
            "trial_id": runtime.config.trial_id,
            "task_text": runtime.task_description,
            "original_prompt": runtime.original_prompt,
            "current_prompt": runtime.current_prompt,
            "mode": runtime.config.mode,
            "policy_step": runtime.policy_step,
            "environment_step": runtime.config.num_steps_wait + runtime.policy_step + runtime.extra_environment_steps,
            "policy_budget_remaining": max(0, runtime.config.max_steps - runtime.policy_step),
            "reward": runtime.reward,
            "done": runtime.done,
            "episode_status": json_safe(status),
            "target_joint": self.resolved_target_joint,
            "target_position": self.object_position,
            "target_selection": json_safe(runtime.target_selection),
            "disturbance_count": runtime.disturbance_count,
            "last_disturbance": self.last_disturbance,
            "fresh_observation": runtime.last_fresh_observation,
            "latest_action": {"raw_action": runtime.raw_action, "env_action": runtime.env_action},
            "recovery_state": runtime.recovery_state or {},
            "device_summary": self.device_summary,
        }

    def stop(self) -> None:
        self.close()

    def close(self) -> None:
        had_runtime = self.runtime is not None
        had_model = self.model is not None or self.processor is not None or self.loaded
        if self.runtime is not None:
            self._close_env(self.runtime.env)
            self.runtime = None
        self.model = None
        self.processor = None
        self.model_cfg = None
        self.loaded = False
        self.device_summary = {"cuda_available": False, "device": "released" if had_runtime or had_model else "unloaded"}
        if had_model:
            unload_torch_model_refs()

    def _overlay(self, frame: np.ndarray, episode_status: str) -> np.ndarray:
        from libero_experiment_core import draw_overlay

        snap = self.get_snapshot()
        snap["episode_status"] = episode_status
        return draw_overlay(frame, snap)

    def _require_runtime(self) -> _EpisodeRuntime:
        if self.runtime is None:
            raise RuntimeError("Real backend episode has not been reset.")
        return self.runtime

    def _coerce_config(self, config: ExperimentConfig | dict[str, Any] | str | None) -> ExperimentConfig:
        if isinstance(config, ExperimentConfig):
            return config
        if isinstance(config, str):
            return ExperimentConfig(checkpoint=config)
        if config is None:
            if self.config is None:
                raise ValueError("ExperimentConfig is required before backend load.")
            return self.config
        data = dict(config)
        if "output_dir" in data and "out_dir" not in data:
            data["out_dir"] = data.pop("output_dir")
        return ExperimentConfig(**data)

    @staticmethod
    def _close_env(env: Any) -> None:
        try:
            env.close()
        except Exception:
            pass
