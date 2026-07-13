from __future__ import annotations

import inspect
import json
import os
import re
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

import numpy as np


ExperimentMode = Literal[
    "clean",
    "reactive_disturbed",
    "verifier_stop",
    "structured_relocalize_prompt",
    "stage_backtrack_subgoal",
    "full_reset_replan",
    "oracle_rollback",
]


@dataclass(frozen=True)
class EpisodeStatus:
    status: Literal["success", "failure", "timeout", "stopped", "simulator_error"]
    success: bool
    failure: bool
    timeout: bool
    stopped: bool
    simulator_error: bool
    reward: float
    done: bool
    policy_step: int
    max_steps: int
    source: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TargetSelection:
    selected_joint: str | None
    candidates: list[dict[str, Any]]
    reason: str
    requested_joint: str = "auto"
    ambiguous: bool = False


@dataclass(frozen=True)
class BudgetReport:
    policy_step_budget: int
    warmup_simulator_steps: int
    policy_inference_steps: int
    environment_control_steps: int
    pre_disturbance_policy_steps: int
    recovery_policy_steps: int
    total_policy_steps_consumed: int
    reset_count: int
    rollback_count: int
    success_within_original_budget: bool


CANONICAL_MODES: tuple[str, ...] = (
    "clean",
    "reactive_disturbed",
    "verifier_stop",
    "structured_relocalize_prompt",
    "stage_backtrack_subgoal",
    "full_reset_replan",
    "oracle_rollback",
)

MODE_ALIASES = {
    "disturbed": "reactive_disturbed",
    "structured_reprompt_recovery": "structured_relocalize_prompt",
}


@dataclass(frozen=True)
class ExperimentConfig:
    checkpoint: str
    task_suite: str = "libero_spatial"
    unnorm_key: str | None = None
    task_id: int = 0
    trial_id: int = 0
    mode: ExperimentMode = "reactive_disturbed"
    max_steps: int = 220
    num_steps_wait: int = 10
    disturbance_step: int = 70
    target_joint: str = "auto"
    dx: float = 0.10
    dy: float = 0.05
    seed: int = 7
    resolution: int = 256
    out_dir: str = "/home/lijingsu/vla/dashboard_outputs"
    enable_auto_disturbance: bool = True
    allow_multiple_disturbances: bool = False

    def __post_init__(self) -> None:
        mode = canonicalize_mode(self.mode)
        object.__setattr__(self, "mode", mode)
        if self.max_steps <= 0:
            raise ValueError("max_steps must be > 0")
        if self.num_steps_wait < 0:
            raise ValueError("num_steps_wait must be >= 0")
        if self.disturbance_step < 0:
            raise ValueError("disturbance_step must be >= 0")
        if self.task_id < 0:
            raise ValueError("task_id must be >= 0")
        if self.trial_id < 0:
            raise ValueError("trial_id must be >= 0")
        if self.resolution <= 0:
            raise ValueError("resolution must be > 0")
        if mode == "clean":
            object.__setattr__(self, "enable_auto_disturbance", False)


@dataclass
class PolicyStepResult:
    raw_frame: np.ndarray
    raw_action: list[float]
    env_action: list[float]
    next_obs: dict[str, Any]
    reward: float
    done: bool
    info: dict[str, Any]
    inference_seconds: float
    env_step_seconds: float


@dataclass
class VideoStatus:
    raw_video_path: str
    annotated_video_path: str
    warnings: list[str] = field(default_factory=list)


def canonicalize_mode(mode: str) -> str:
    canonical = MODE_ALIASES.get(mode, mode)
    if canonical not in CANONICAL_MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {list(CANONICAL_MODES)}")
    return canonical


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if hasattr(value, "__dataclass_fields__"):
        return json_safe(asdict(value))
    return value


def _truthy_info_value(info: dict[str, Any], keys: tuple[str, ...]) -> tuple[bool, str | None]:
    for key in keys:
        if key in info and bool(info[key]):
            return True, key
    return False, None


def extract_episode_status(
    reward: float,
    done: bool,
    info: dict[str, Any] | None,
    policy_step: int,
    max_steps: int,
) -> EpisodeStatus:
    info = json_safe(info or {})
    detail: dict[str, Any] = {"info_keys": sorted(info.keys())}
    simulator_error, error_key = _truthy_info_value(info, ("simulator_error", "exception", "env_error"))
    if simulator_error:
        detail["error_key"] = error_key
        return EpisodeStatus(
            status="simulator_error",
            success=False,
            failure=False,
            timeout=False,
            stopped=False,
            simulator_error=True,
            reward=float(reward),
            done=bool(done),
            policy_step=int(policy_step),
            max_steps=int(max_steps),
            source=f"info.{error_key}",
            detail=detail,
        )

    stopped, stopped_key = _truthy_info_value(info, ("stopped", "stop_requested", "stopped_by_verifier"))
    if stopped:
        detail["stopped_key"] = stopped_key
        return EpisodeStatus(
            status="stopped",
            success=False,
            failure=False,
            timeout=False,
            stopped=True,
            simulator_error=False,
            reward=float(reward),
            done=bool(done),
            policy_step=int(policy_step),
            max_steps=int(max_steps),
            source=f"info.{stopped_key}",
            detail=detail,
        )

    info_success, success_key = _truthy_info_value(info, ("success", "is_success", "task_success", "successful"))
    reward_success = float(reward) >= 1.0
    success = bool(info_success or done or reward_success)
    if success:
        if info_success:
            source = f"info.{success_key}"
        elif done:
            source = "done_current_libero_bddl_success"
        else:
            source = "sparse_reward_ge_1"
        return EpisodeStatus(
            status="success",
            success=True,
            failure=False,
            timeout=False,
            stopped=False,
            simulator_error=False,
            reward=float(reward),
            done=bool(done),
            policy_step=int(policy_step),
            max_steps=int(max_steps),
            source=source,
            detail=detail,
        )

    info_timeout, timeout_key = _truthy_info_value(info, ("timeout", "truncated", "TimeLimit.truncated"))
    timed_out = bool(info_timeout or int(policy_step) >= int(max_steps))
    if timed_out:
        source = f"info.{timeout_key}" if info_timeout else "policy_step_budget_exhausted"
        return EpisodeStatus(
            status="timeout",
            success=False,
            failure=False,
            timeout=True,
            stopped=False,
            simulator_error=False,
            reward=float(reward),
            done=bool(done),
            policy_step=int(policy_step),
            max_steps=int(max_steps),
            source=source,
            detail=detail,
        )

    return EpisodeStatus(
        status="failure",
        success=False,
        failure=True,
        timeout=False,
        stopped=False,
        simulator_error=False,
        reward=float(reward),
        done=bool(done),
        policy_step=int(policy_step),
        max_steps=int(max_steps),
        source="episode_ended_without_success_or_timeout",
        detail=detail,
    )


def make_budget_report(
    *,
    policy_step_budget: int,
    warmup_simulator_steps: int,
    policy_inference_steps: int,
    extra_environment_steps: int = 0,
    pre_disturbance_policy_steps: int = 0,
    reset_count: int = 0,
    rollback_count: int = 0,
    success: bool = False,
) -> BudgetReport:
    total_policy_steps = int(policy_inference_steps)
    pre_steps = max(0, min(int(pre_disturbance_policy_steps), total_policy_steps))
    recovery_steps = max(0, total_policy_steps - pre_steps)
    return BudgetReport(
        policy_step_budget=int(policy_step_budget),
        warmup_simulator_steps=int(warmup_simulator_steps),
        policy_inference_steps=total_policy_steps,
        environment_control_steps=int(warmup_simulator_steps) + total_policy_steps + int(extra_environment_steps),
        pre_disturbance_policy_steps=pre_steps,
        recovery_policy_steps=recovery_steps,
        total_policy_steps_consumed=total_policy_steps,
        reset_count=int(reset_count),
        rollback_count=int(rollback_count),
        success_within_original_budget=bool(success and total_policy_steps <= int(policy_step_budget)),
    )


def short_traceback(limit: int = 12) -> str:
    return "".join(traceback.format_exc().splitlines(keepends=True)[-limit:])


def make_model_cfg(cfg: ExperimentConfig) -> SimpleNamespace:
    return SimpleNamespace(
        model_family="openvla",
        pretrained_checkpoint=cfg.checkpoint,
        load_in_8bit=False,
        load_in_4bit=False,
        center_crop=True,
        unnorm_key=cfg.unnorm_key or cfg.task_suite,
    )


def set_seed(seed: int) -> None:
    from experiments.robot.robot_utils import set_seed_everywhere

    set_seed_everywhere(seed)


def load_model_and_processor(cfg: ExperimentConfig) -> tuple[Any, Any, SimpleNamespace, str]:
    from experiments.robot.openvla_utils import get_processor
    from experiments.robot.robot_utils import get_model

    model_cfg = make_model_cfg(cfg)
    model = get_model(model_cfg)
    resolved = resolve_unnorm_key(model, model_cfg.unnorm_key)
    model_cfg.unnorm_key = resolved
    processor = get_processor(model_cfg)
    return model, processor, model_cfg, resolved


def resolve_unnorm_key(model: Any, requested_key: str) -> str:
    stats = getattr(model, "norm_stats", {}) or {}
    if requested_key in stats:
        return requested_key
    no_noops = f"{requested_key}_no_noops"
    if no_noops in stats:
        return no_noops
    available = sorted(str(k) for k in stats.keys())
    raise ValueError(f"missing unnorm key {requested_key!r}; available={available}")


def get_device_summary() -> dict[str, Any]:
    try:
        import torch

        if not torch.cuda.is_available():
            return {"cuda_available": False, "device": "cpu"}
        index = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(index)
        return {
            "cuda_available": True,
            "device": f"cuda:{index}",
            "name": props.name,
            "total_memory_gb": round(props.total_memory / (1024**3), 2),
            "allocated_gb": round(torch.cuda.memory_allocated(index) / (1024**3), 2),
            "reserved_gb": round(torch.cuda.memory_reserved(index) / (1024**3), 2),
        }
    except Exception as exc:  # pragma: no cover - defensive hardware reporting
        return {"cuda_available": False, "device": "unknown", "error": repr(exc)}


def unload_torch_model_refs() -> None:
    import gc

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def get_benchmark_suite(task_suite_name: str) -> Any:
    from libero.libero import benchmark

    suites = benchmark.get_benchmark_dict()
    if task_suite_name not in suites:
        raise ValueError(f"unknown task suite {task_suite_name!r}; available={sorted(suites)}")
    return suites[task_suite_name]()


def validate_task_and_trial(task_suite: Any, cfg: ExperimentConfig) -> list[Any]:
    if cfg.task_id >= int(task_suite.n_tasks):
        raise ValueError(f"task_id {cfg.task_id} is outside suite range 0..{int(task_suite.n_tasks) - 1}")
    initial_states = list(task_suite.get_task_init_states(cfg.task_id))
    if cfg.trial_id >= len(initial_states):
        raise ValueError(
            f"trial_id {cfg.trial_id} is outside available initial states 0..{len(initial_states) - 1}"
        )
    return initial_states


def create_libero_env(task: Any, cfg: ExperimentConfig) -> tuple[Any, str]:
    from experiments.robot.libero.libero_utils import get_libero_env

    return get_libero_env(task, "openvla", resolution=cfg.resolution)


def get_image_resize_size(model_cfg: Any) -> Any:
    from experiments.robot.robot_utils import get_image_resize_size as _get_image_resize_size

    return _get_image_resize_size(model_cfg)


def get_dummy_action(model_family: str = "openvla") -> Any:
    from experiments.robot.libero.libero_utils import get_libero_dummy_action

    return get_libero_dummy_action(model_family)


def sim_from_env(env: Any) -> Any:
    if hasattr(env, "env") and hasattr(env.env, "sim"):
        return env.env.sim
    if hasattr(env, "sim"):
        return env.sim
    raise ValueError("could not locate MuJoCo sim on env or env.env")


def tokenize(text: str) -> set[str]:
    return {tok for tok in re.split(r"[^a-z0-9]+", text.lower()) if len(tok) > 1}


def list_free_joints(env: Any, task_description: str | None = None) -> list[dict[str, Any]]:
    sim = sim_from_env(env)
    task_tokens = tokenize(task_description or "")
    joints: list[dict[str, Any]] = []
    for joint_id in range(int(sim.model.njnt)):
        name = sim.model.joint_id2name(joint_id)
        if not name or name.startswith("robot") or name.startswith("gripper"):
            continue
        if int(sim.model.jnt_type[joint_id]) != 0:
            continue
        object_name = name.replace("_joint0", "")
        object_tokens = tokenize(object_name)
        matched_tokens = sorted(task_tokens & object_tokens)
        score = len(matched_tokens)
        joints.append(
            {
                "name": name,
                "joint_id": int(joint_id),
                "qpos_addr": int(sim.model.jnt_qposadr[joint_id]),
                "object_name": object_name,
                "score": int(score),
                "candidate_tokens": sorted(object_tokens),
                "matched_task_tokens": matched_tokens,
                "score_reason": f"{score} overlapping task/object tokens",
            }
        )
    joints.sort(key=lambda x: (x["score"], -x["joint_id"], x["name"]), reverse=True)
    return joints


def select_target_joint(env: Any, task_description: str, requested: str = "auto") -> TargetSelection:
    joints = list_free_joints(env, task_description)
    if requested != "auto":
        validate_free_joint(env, requested)
        return TargetSelection(
            selected_joint=requested,
            candidates=joints,
            reason="explicit_target_joint",
            requested_joint=requested,
            ambiguous=False,
        )
    if not joints:
        raise ValueError("No movable non-robot free-joint object found for disturbance.")
    top_score = int(joints[0]["score"])
    if top_score <= 0:
        raise ValueError(
            "Auto target joint is ambiguous: all movable candidates scored 0. "
            "Pass --target-joint explicitly."
        )
    tied = [joint for joint in joints if int(joint["score"]) == top_score]
    if len(tied) > 1:
        names = ", ".join(str(joint["name"]) for joint in tied)
        raise ValueError(
            f"Auto target joint is ambiguous: {len(tied)} candidates tie at score {top_score}: {names}. "
            "Pass --target-joint explicitly."
        )
    return TargetSelection(
        selected_joint=str(joints[0]["name"]),
        candidates=joints,
        reason=f"unique_highest_token_overlap_score_{top_score}",
        requested_joint=requested,
        ambiguous=False,
    )


def choose_target_joint(env: Any, task_description: str, requested: str = "auto") -> str:
    selection = select_target_joint(env, task_description, requested)
    if selection.selected_joint is None:
        raise ValueError(f"target selection did not produce a joint: {selection.reason}")
    return selection.selected_joint


def validate_free_joint(env: Any, joint_name: str) -> tuple[Any, int, int]:
    sim = sim_from_env(env)
    try:
        joint_id = int(sim.model.joint_name2id(joint_name))
    except Exception as exc:
        raise ValueError(f"joint {joint_name!r} does not exist") from exc
    if joint_id < 0 or joint_id >= int(sim.model.njnt):
        raise ValueError(f"joint {joint_name!r} resolved to invalid id {joint_id}")
    if int(sim.model.jnt_type[joint_id]) != 0:
        raise ValueError(f"joint {joint_name!r} is not a free joint")
    qpos_addr = int(sim.model.jnt_qposadr[joint_id])
    qpos_size = int(np.asarray(sim.data.qpos).shape[0])
    if qpos_addr < 0 or qpos_addr + 7 > qpos_size:
        raise ValueError(
            f"joint {joint_name!r} has invalid qpos slice [{qpos_addr}:{qpos_addr + 7}] for qpos size {qpos_size}"
        )
    return sim, joint_id, qpos_addr


def move_free_joint_xy(env: Any, joint_name: str, dx: float, dy: float) -> dict[str, Any]:
    sim, joint_id, qpos_addr = validate_free_joint(env, joint_name)
    before = np.asarray(sim.data.qpos[qpos_addr : qpos_addr + 7], dtype=float).copy()
    sim.data.qpos[qpos_addr] += float(dx)
    sim.data.qpos[qpos_addr + 1] += float(dy)
    sim.forward()
    after = np.asarray(sim.data.qpos[qpos_addr : qpos_addr + 7], dtype=float).copy()
    return {
        "joint": joint_name,
        "joint_id": int(joint_id),
        "qpos_addr": int(qpos_addr),
        "before_qpos": before.tolist(),
        "after_qpos": after.tolist(),
        "delta_xy": [float(dx), float(dy)],
        "applied_at": iso_now(),
    }


def get_joint_qpos(env: Any, joint_name: str) -> list[float]:
    sim, _, qpos_addr = validate_free_joint(env, joint_name)
    return np.asarray(sim.data.qpos[qpos_addr : qpos_addr + 7], dtype=float).tolist()


def object_phrase_from_joint(joint_name: str) -> str:
    text = joint_name.replace("_joint0", "")
    text = text.replace("akita_", "").replace("_1", "")
    return text.replace("_", " ")


def infer_goal_phrase(task_description: str) -> str:
    if "plate" in task_description.lower():
        return "the plate"
    return "the target location"


def build_recovery_prompt(mode: str, original_task: str, joint_name: str) -> tuple[str, dict[str, Any] | None]:
    canonical = canonicalize_mode(mode)
    obj = object_phrase_from_joint(joint_name)
    if canonical == "structured_relocalize_prompt":
        prompt = f"relocalize the {obj} at its current position, then complete the original task: {original_task}"
        return prompt, {
            "type": "structured_relocalize_prompt",
            "affected_joint": joint_name,
            "affected_object": obj,
            "invalid_state": ["affected_object_pose", "grasp_validity"],
            "decision": "relocalize_affected_object_then_continue",
            "prompt_after_recovery": prompt,
            "has_selective_recovery_state": True,
        }
    if canonical == "stage_backtrack_subgoal":
        goal = infer_goal_phrase(original_task)
        prompt = f"pick up the {obj} from its current position and place it on {goal}"
        return prompt, {
            "type": "stage_backtrack_subgoal",
            "affected_joint": joint_name,
            "affected_object": obj,
            "goal": goal,
            "new_prompt": prompt,
            "progress_preserved": "unaffected_world_state_preserved_but_current_stage_restarted",
            "has_selective_recovery_state": True,
        }
    return original_task, None


def verifier_stop_state() -> dict[str, Any]:
    return {
        "type": "verifier_stop",
        "decision": "stop_or_full_replan",
        "has_selective_recovery_state": False,
    }


def refresh_observation_after_sim_change(env: Any, cfg: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    sim = sim_from_env(env)
    sim.forward()
    operations = ["sim.forward"]
    for label, obj, name in (
        ("env", env, "check_success"),
        ("env", env, "_post_process"),
        ("env", env, "_update_observables"),
        ("env.env", getattr(env, "env", None), "_post_process"),
        ("env.env", getattr(env, "env", None), "_update_observables"),
    ):
        if obj is None or not hasattr(obj, name):
            continue
        try:
            if name == "_update_observables":
                getattr(obj, name)(force=True)
            else:
                getattr(obj, name)()
            operations.append(f"{label}.{name}")
        except Exception as exc:
            operations.append(f"{label}.{name}_failed:{type(exc).__name__}")

    candidates: list[tuple[str, Any]] = []
    for label, obj in (("env", env), ("env.env", getattr(env, "env", None))):
        if obj is not None and hasattr(obj, "_get_observations"):
            candidates.append((f"{label}._get_observations", getattr(obj, "_get_observations")))

    errors: list[str] = []
    for label, getter in candidates:
        try:
            sig = inspect.signature(getter)
            if "force_update" in sig.parameters:
                obs = getter(force_update=True)
                return obs, {
                    "method": f"{label}(force_update=True)",
                    "operations": operations,
                    "consumed_noop_env_step": False,
                }
        except (TypeError, ValueError):
            try:
                obs = getter(force_update=True)
                return obs, {
                    "method": f"{label}(force_update=True)",
                    "operations": operations,
                    "consumed_noop_env_step": False,
                }
            except TypeError as exc:
                errors.append(f"{label}(force_update=True): {exc}")
        except Exception as exc:
            errors.append(f"{label}(force_update=True): {exc!r}")
        try:
            obs = getter()
            return obs, {
                "method": f"{label}()",
                "operations": operations,
                "consumed_noop_env_step": False,
            }
        except Exception as exc:
            errors.append(f"{label}(): {exc!r}")

    model_family = getattr(cfg, "model_family", "openvla")
    obs, reward, done, info = env.step(get_dummy_action(model_family))
    return obs, {
        "method": "env.step(dummy_noop)",
        "operations": operations,
        "consumed_noop_env_step": True,
        "fallback_errors": errors,
        "reward": float(reward),
        "done": bool(done),
        "info": json_safe(info),
    }


def frame_from_obs(obs: dict[str, Any], resize_size: Any) -> np.ndarray:
    from experiments.robot.libero.libero_utils import get_libero_image

    return np.asarray(get_libero_image(obs, resize_size), dtype=np.uint8)


def execute_policy_step(
    *,
    cfg: Any,
    model: Any,
    processor: Any,
    env: Any,
    obs: dict[str, Any],
    prompt: str,
    resize_size: Any,
) -> PolicyStepResult:
    from experiments.robot.libero.libero_utils import get_libero_image, quat2axisangle
    from experiments.robot.robot_utils import get_action, invert_gripper_action, normalize_gripper_action

    raw_frame = np.asarray(get_libero_image(obs, resize_size), dtype=np.uint8)
    observation = {
        "full_image": raw_frame,
        "state": np.concatenate(
            (
                obs["robot0_eef_pos"],
                quat2axisangle(obs["robot0_eef_quat"]),
                obs["robot0_gripper_qpos"],
            )
        ),
    }
    t0 = time.monotonic()
    action = get_action(cfg, model, observation, prompt, processor=processor)
    inference_seconds = time.monotonic() - t0
    raw_action = np.asarray(action, dtype=float).tolist()
    action = normalize_gripper_action(action, binarize=True)
    if getattr(cfg, "model_family", "openvla") == "openvla":
        action = invert_gripper_action(action)
    env_action = np.asarray(action, dtype=float).tolist()
    t1 = time.monotonic()
    next_obs, reward, done, info = env.step(env_action)
    env_step_seconds = time.monotonic() - t1
    return PolicyStepResult(
        raw_frame=raw_frame,
        raw_action=raw_action,
        env_action=env_action,
        next_obs=next_obs,
        reward=float(reward),
        done=bool(done),
        info=json_safe(info),
        inference_seconds=float(inference_seconds),
        env_step_seconds=float(env_step_seconds),
    )


def draw_overlay(frame: np.ndarray, fields: dict[str, Any]) -> np.ndarray:
    image = np.asarray(frame, dtype=np.uint8).copy()
    try:
        from PIL import Image, ImageDraw, ImageFont

        pil = Image.fromarray(image)
        draw = ImageDraw.Draw(pil, "RGBA")
        font = ImageFont.load_default()
        lines = [
            f"{fields.get('mode', '')} | task {fields.get('task_id', '')}/{fields.get('trial_id', '')}",
            f"{fields.get('state', '')} step {fields.get('policy_step', 0)} reward {fields.get('reward', 0.0):.3f}",
            f"target {fields.get('target_joint', '')}",
        ]
        if fields.get("recovery_prompt"):
            lines.append("recovery prompt active")
        width = max(draw.textlength(line, font=font) for line in lines) + 12
        height = 14 * len(lines) + 10
        draw.rectangle((4, 4, min(width, pil.width - 4), height), fill=(0, 0, 0, 155))
        y = 8
        for line in lines:
            draw.text((10, y), line, fill=(255, 255, 255, 245), font=font)
            y += 14
        return np.asarray(pil, dtype=np.uint8)
    except Exception:
        return image


class EpisodeRecorder:
    def __init__(self, run_dir: Path, cfg: ExperimentConfig) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.cfg = cfg
        self.events_path = self.run_dir / "events.jsonl"
        self.episode_path = self.run_dir / "episode.json"
        self.raw_video_path = self.run_dir / "raw.mp4"
        self.annotated_video_path = self.run_dir / "annotated.mp4"
        self.log_path = self.run_dir / "dashboard.log"
        self._events = self.events_path.open("a", encoding="utf-8", buffering=1)
        self._raw_writer = None
        self._annotated_writer = None
        self._video_warning: str | None = None
        self.start_time = time.monotonic()

    def event(self, event: str, policy_step: int, phase_policy_step: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        row = {
            "wall_time": round(time.monotonic() - self.start_time, 6),
            "timestamp": iso_now(),
            "event": event,
            "policy_step": int(policy_step),
            "phase_policy_step": int(phase_policy_step),
            "payload": json_safe(payload or {}),
        }
        self._events.write(json.dumps(row, ensure_ascii=True) + "\n")
        return row

    def log_exception(self, label: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{iso_now()}] {label}\n")
            f.write(traceback.format_exc())
            f.write("\n")

    def append_frames(self, raw_frame: np.ndarray, annotated_frame: np.ndarray) -> None:
        if self._video_warning:
            return
        try:
            import imageio.v2 as imageio

            if self._raw_writer is None:
                self._raw_writer = imageio.get_writer(self.raw_video_path, fps=30)
            if self._annotated_writer is None:
                self._annotated_writer = imageio.get_writer(self.annotated_video_path, fps=30)
            self._raw_writer.append_data(np.asarray(raw_frame, dtype=np.uint8))
            self._annotated_writer.append_data(np.asarray(annotated_frame, dtype=np.uint8))
        except Exception as exc:
            self._video_warning = f"video writer disabled: {exc!r}"
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(f"[{iso_now()}] {self._video_warning}\n")
            self.close_writers()

    def write_episode(self, payload: dict[str, Any]) -> None:
        tmp = self.episode_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(json_safe(payload), indent=2, ensure_ascii=True), encoding="utf-8")
        os.replace(tmp, self.episode_path)

    def close_writers(self) -> None:
        for attr in ("_raw_writer", "_annotated_writer"):
            writer = getattr(self, attr)
            if writer is not None:
                try:
                    writer.close()
                except Exception:
                    pass
                setattr(self, attr, None)

    def close(self) -> VideoStatus:
        self.close_writers()
        try:
            self._events.flush()
            self._events.close()
        except Exception:
            pass
        warnings = [self._video_warning] if self._video_warning else []
        return VideoStatus(str(self.raw_video_path), str(self.annotated_video_path), warnings)
