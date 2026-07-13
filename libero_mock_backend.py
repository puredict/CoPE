"""CPU-only mock backend for the LIBERO dashboard.

This module intentionally avoids importing OpenVLA, LIBERO, robosuite, MuJoCo,
or torch.  It models the backend interface the dashboard controller will later
use for a real runtime, while remaining deterministic and cheap enough for unit
tests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import time
from typing import Any, Iterable

import numpy as np

try:  # Pillow is present in the target venv; keep a fallback for portability.
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - exercised only when Pillow is absent.
    Image = None
    ImageDraw = None
    ImageFont = None


MOCK_EXPERIMENT_MODES = (
    "clean",
    "reactive_disturbed",
    "verifier_stop",
    "structured_relocalize_prompt",
    "stage_backtrack_subgoal",
    "full_reset_replan",
    "oracle_rollback",
)

MOCK_OUTCOMES = ("success", "failure", "timeout", "exception")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_mode(mode: str) -> str:
    aliases = {
        "structured_reprompt_recovery": "structured_relocalize_prompt",
        "disturbed": "reactive_disturbed",
        "completed": "succeeded",
    }
    return aliases.get(str(mode), str(mode))


@dataclass(frozen=True)
class MockRunConfig:
    task_id: int = 0
    trial_id: int = 0
    task_suite: str = "libero_spatial"
    mode: str = "reactive_disturbed"
    max_steps: int = 30
    disturbance_step: int = 5
    enable_auto_disturbance: bool = True
    allow_multiple_disturbances: bool = False
    target_joint: str = "auto"
    dx: float = 0.10
    dy: float = 0.05
    seed: int = 7
    output_dir: str = "/tmp/libero_mock_dashboard"
    frame_size: int = 256
    action_dim: int = 7
    step_delay: float = 0.02
    success_step: int = 12
    failure_step: int = 10
    exception_step: int = 4
    mock_outcome: str = "success"

    def validated(self) -> "MockRunConfig":
        mode = canonical_mode(self.mode)
        if mode not in MOCK_EXPERIMENT_MODES:
            raise ValueError(f"Unsupported mock mode: {self.mode}")
        if self.mock_outcome not in MOCK_OUTCOMES:
            raise ValueError(f"Unsupported mock outcome: {self.mock_outcome}")
        if self.max_steps <= 0:
            raise ValueError("max_steps must be > 0")
        if self.disturbance_step < 0:
            raise ValueError("disturbance_step must be >= 0")
        if self.frame_size < 96:
            raise ValueError("frame_size must be at least 96")
        if self.action_dim <= 0:
            raise ValueError("action_dim must be > 0")
        if self.success_step <= 0:
            raise ValueError("success_step must be > 0")
        if self.failure_step <= 0:
            raise ValueError("failure_step must be > 0")
        return MockRunConfig(**{**asdict(self), "mode": mode})


@dataclass(frozen=True)
class MockStepResult:
    policy_step: int
    raw_frame: np.ndarray
    annotated_frame: np.ndarray
    raw_action: list[float]
    env_action: list[float]
    reward: float
    done: bool
    success: bool
    termination_reason: str | None
    current_prompt: str
    object_position: list[float]
    inference_seconds: float
    env_step_seconds: float
    info: dict[str, Any]


def json_safe(value: Any) -> Any:
    """Convert common scientific Python values into JSON-safe structures."""

    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, set):
        return sorted(json_safe(v) for v in value)
    return value


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True) + "\n")


def _default_font(size: int = 12):
    if ImageFont is None:
        return None
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=size)
    except Exception:
        return ImageFont.load_default()


def _draw_text_fallback(frame: np.ndarray, lines: Iterable[str]) -> np.ndarray:
    """Very small fallback when Pillow is missing.

    It does not attempt to draw real glyphs, but it creates stable line markers
    derived from the text.  The target environment has Pillow, so normal runs
    draw readable text.
    """

    out = frame.copy()
    y = 6
    for line in lines:
        digest = sum(ord(ch) for ch in line)
        color = np.array([(digest * 3) % 255, (digest * 7) % 255, (digest * 11) % 255], dtype=np.uint8)
        out[y : y + 8, 6 : min(out.shape[1] - 6, 6 + len(line) * 4), :] = color
        y += 13
    return out


def draw_text_panel(frame: np.ndarray, lines: Iterable[str], *, fill=(255, 255, 255)) -> np.ndarray:
    lines = [str(line) for line in lines]
    if Image is None or ImageDraw is None:
        return _draw_text_fallback(frame, lines)
    image = Image.fromarray(frame)
    draw = ImageDraw.Draw(image, "RGBA")
    font = _default_font(12)
    line_height = 15
    panel_height = min(frame.shape[0] - 8, 10 + line_height * len(lines))
    draw.rectangle((4, 4, frame.shape[1] - 4, panel_height), fill=(0, 0, 0, 150))
    y = 8
    for line in lines:
        draw.text((9, y), line[:56], font=font, fill=fill)
        y += line_height
    return np.asarray(image, dtype=np.uint8)


class SimpleVideoRecorder:
    """Best-effort RGB video writer with a deterministic fallback file."""

    def __init__(self, raw_path: str | Path, annotated_path: str | Path, fps: int = 10) -> None:
        self.raw_path = Path(raw_path)
        self.annotated_path = Path(annotated_path)
        self.fps = fps
        self.frame_count = 0
        self.warnings: list[str] = []
        self._raw_writer = None
        self._annotated_writer = None
        self.raw_path.parent.mkdir(parents=True, exist_ok=True)
        self.annotated_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import imageio.v2 as imageio

            self._raw_writer = imageio.get_writer(str(self.raw_path), fps=fps, macro_block_size=1)
            self._annotated_writer = imageio.get_writer(str(self.annotated_path), fps=fps, macro_block_size=1)
        except Exception as exc:  # pragma: no cover - depends on optional codecs.
            self.warnings.append(f"imageio video writer unavailable: {type(exc).__name__}: {exc}")
            self._raw_writer = None
            self._annotated_writer = None

    def append(self, raw_frame: np.ndarray, annotated_frame: np.ndarray) -> None:
        raw_frame = np.asarray(raw_frame, dtype=np.uint8)
        annotated_frame = np.asarray(annotated_frame, dtype=np.uint8)
        if self._raw_writer is not None and self._annotated_writer is not None:
            try:
                self._raw_writer.append_data(raw_frame)
                self._annotated_writer.append_data(annotated_frame)
            except Exception as exc:  # pragma: no cover - depends on optional codecs.
                self.warnings.append(f"video append failed: {type(exc).__name__}: {exc}")
                self._close_writers()
                self._raw_writer = None
                self._annotated_writer = None
        self.frame_count += 1

    def _close_writers(self) -> None:
        for writer_name in ("_raw_writer", "_annotated_writer"):
            writer = getattr(self, writer_name)
            if writer is not None:
                try:
                    writer.close()
                except Exception as exc:  # pragma: no cover - codec dependent.
                    self.warnings.append(f"video close failed: {type(exc).__name__}: {exc}")
                setattr(self, writer_name, None)

    def close(self) -> dict[str, Any]:
        self._close_writers()
        for path in (self.raw_path, self.annotated_path):
            if not path.exists() or path.stat().st_size == 0:
                payload = {
                    "fallback": True,
                    "frame_count": self.frame_count,
                    "fps": self.fps,
                    "warnings": self.warnings,
                    "note": "The requested mp4 path is a fallback marker because no video codec was available.",
                }
                path.write_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))
        return {
            "raw_video_path": str(self.raw_path),
            "annotated_video_path": str(self.annotated_path),
            "frame_count": self.frame_count,
            "warnings": list(self.warnings),
        }


class MockBackend:
    """Deterministic dashboard backend that simulates one robot episode."""

    def __init__(self, *, load_delay: float = 0.05) -> None:
        self.load_delay = load_delay
        self.loaded = False
        self.checkpoint = "mock://libero-dashboard"
        self.resolved_unnorm_key = "mock_unnorm_key"
        self.device = "cpu"
        self._rng = random.Random(0)
        self._config: MockRunConfig | None = None
        self._task_text = ""
        self._original_prompt = ""
        self._current_prompt = ""
        self._resolved_target_joint = ""
        self._object_position = [0.42, 0.54]
        self._disturbance_count = 0
        self._disturbed = False
        self._manual_disturbance_count = 0
        self._auto_disturbance_count = 0
        self._last_disturbance: dict[str, Any] | None = None

    @property
    def current_prompt(self) -> str:
        return self._current_prompt

    @property
    def original_prompt(self) -> str:
        return self._original_prompt

    @property
    def task_text(self) -> str:
        return self._task_text

    @property
    def object_position(self) -> list[float]:
        return list(self._object_position)

    @property
    def disturbance_count(self) -> int:
        return self._disturbance_count

    @property
    def last_disturbance(self) -> dict[str, Any] | None:
        return json_safe(self._last_disturbance) if self._last_disturbance else None

    @property
    def resolved_target_joint(self) -> str:
        return self._resolved_target_joint

    def load_model(self, checkpoint: str = "mock://libero-dashboard") -> dict[str, Any]:
        time.sleep(max(0.0, self.load_delay))
        self.loaded = True
        self.checkpoint = checkpoint or "mock://libero-dashboard"
        return {
            "checkpoint": self.checkpoint,
            "resolved_unnorm_key": self.resolved_unnorm_key,
            "device": self.device,
            "backend": "mock",
        }

    def unload_model(self) -> None:
        self.loaded = False

    def inspect_task(self, config: MockRunConfig) -> dict[str, Any]:
        cfg = config.validated()
        task_text = self._task_text_for(cfg.task_id)
        joints = self._target_joints_for(cfg.task_id)
        return {
            "task_text": task_text,
            "available_trials": 10,
            "available_target_joints": joints,
            "resolved_target_joint": self._resolve_target_joint(cfg.target_joint, joints),
            "preview_frame": self.render_frame(
                cfg,
                policy_step=0,
                paused=False,
                state_label="READY",
                task_text=task_text,
                prompt=task_text,
                object_position=[0.42, 0.54],
                disturbed=False,
                disturbance_count=0,
            ),
        }

    def start_episode(self, config: MockRunConfig) -> dict[str, Any]:
        if not self.loaded:
            raise RuntimeError("Mock backend must be loaded before start_episode().")
        cfg = config.validated()
        self._config = cfg
        self._rng = random.Random(cfg.seed + cfg.task_id * 31 + cfg.trial_id)
        self._task_text = self._task_text_for(cfg.task_id)
        self._original_prompt = self._task_text
        self._current_prompt = self._original_prompt
        self._resolved_target_joint = self._resolve_target_joint(cfg.target_joint, self._target_joints_for(cfg.task_id))
        self._object_position = [0.38 + 0.03 * (cfg.task_id % 4), 0.52 + 0.02 * (cfg.trial_id % 5)]
        self._disturbance_count = 0
        self._manual_disturbance_count = 0
        self._auto_disturbance_count = 0
        self._disturbed = False
        self._last_disturbance = None
        frame = self.render_frame(
            cfg,
            policy_step=0,
            paused=False,
            state_label="RUNNING",
            task_text=self._task_text,
            prompt=self._current_prompt,
            object_position=self._object_position,
            disturbed=False,
            disturbance_count=0,
        )
        return {
            "task_text": self._task_text,
            "original_prompt": self._original_prompt,
            "current_prompt": self._current_prompt,
            "resolved_target_joint": self._resolved_target_joint,
            "available_target_joints": self._target_joints_for(cfg.task_id),
            "object_position": list(self._object_position),
            "frame": frame,
        }

    def should_auto_disturb(self, config: MockRunConfig, policy_step: int) -> bool:
        cfg = config.validated()
        if cfg.mode == "clean":
            return False
        if not cfg.enable_auto_disturbance:
            return False
        if policy_step != cfg.disturbance_step:
            return False
        if self._auto_disturbance_count > 0:
            return False
        return True

    def apply_disturbance(
        self,
        config: MockRunConfig,
        *,
        policy_step: int,
        source: str,
        target_joint: str | None = None,
        dx: float | None = None,
        dy: float | None = None,
    ) -> dict[str, Any]:
        cfg = config.validated()
        if self._disturbance_count > 0 and not cfg.allow_multiple_disturbances:
            return {
                "applied": False,
                "reason": "disturbance_already_applied",
                "source": source,
                "policy_step": policy_step,
                "disturbance_count": self._disturbance_count,
            }

        requested_joint = target_joint or cfg.target_joint
        joint = self._resolved_target_joint if requested_joint == "auto" else requested_joint
        if joint not in self._target_joints_for(cfg.task_id):
            raise ValueError(f"Unknown mock target joint: {joint}")
        delta_x = float(cfg.dx if dx is None else dx)
        delta_y = float(cfg.dy if dy is None else dy)
        before = list(self._object_position)
        self._object_position[0] = min(0.92, max(0.08, self._object_position[0] + delta_x))
        self._object_position[1] = min(0.92, max(0.08, self._object_position[1] + delta_y))
        after = list(self._object_position)
        self._disturbance_count += 1
        self._disturbed = True
        if source == "manual_ui":
            self._manual_disturbance_count += 1
        else:
            self._auto_disturbance_count += 1
        old_prompt = self._current_prompt
        prompt_changed = False
        if cfg.mode == "structured_relocalize_prompt":
            obj = self.object_phrase_from_joint(joint)
            self._current_prompt = f"relocalize the {obj} at its current position, then complete the original task: {self._original_prompt}"
            prompt_changed = self._current_prompt != old_prompt
        elif cfg.mode == "stage_backtrack_subgoal":
            obj = self.object_phrase_from_joint(joint)
            self._current_prompt = f"pick up the {obj} from its current position and place it on {self.infer_goal_phrase()}"
            prompt_changed = self._current_prompt != old_prompt
        disturbance = {
            "applied": True,
            "timestamp": utc_now_iso(),
            "source": source,
            "policy_step": policy_step,
            "requested_target_joint": requested_joint,
            "joint": joint,
            "dx": delta_x,
            "dy": delta_y,
            "before_object_position": before,
            "after_object_position": after,
            "disturbance_count": self._disturbance_count,
            "prompt_changed": prompt_changed,
            "current_prompt": self._current_prompt,
        }
        self._last_disturbance = disturbance
        return json_safe(disturbance)

    def step(self, config: MockRunConfig, *, policy_step: int, paused: bool = False) -> MockStepResult:
        cfg = config.validated()
        if cfg.mock_outcome == "exception" and policy_step >= cfg.exception_step:
            raise RuntimeError(f"Mock worker exception at policy step {policy_step}")

        inference_start = time.perf_counter()
        time.sleep(max(0.0, cfg.step_delay) * 0.45)
        raw_action = self._make_action(cfg, policy_step)
        inference_seconds = time.perf_counter() - inference_start

        env_start = time.perf_counter()
        time.sleep(max(0.0, cfg.step_delay) * 0.55)
        self._advance_object_toward_goal(cfg)
        env_step_seconds = time.perf_counter() - env_start

        new_step = policy_step + 1
        reward = self._reward_for(cfg, new_step)
        done = False
        success = False
        termination_reason: str | None = None
        if cfg.mode == "verifier_stop" and self._disturbed:
            done = True
            success = False
            termination_reason = "verifier_stop"
        elif cfg.mock_outcome == "failure" and new_step >= cfg.failure_step:
            done = True
            success = False
            termination_reason = "mock_failure"
        elif cfg.mock_outcome == "timeout" and new_step >= cfg.max_steps:
            done = True
            success = False
            termination_reason = "timeout"
        elif cfg.mock_outcome == "success" and new_step >= min(cfg.success_step, cfg.max_steps):
            done = True
            success = True
            termination_reason = "success"
        elif new_step >= cfg.max_steps:
            done = True
            success = False
            termination_reason = "timeout"

        raw_frame = self.render_frame(
            cfg,
            policy_step=new_step,
            paused=paused,
            state_label="RUNNING",
            task_text=self._task_text,
            prompt=self._current_prompt,
            object_position=self._object_position,
            disturbed=self._disturbed,
            disturbance_count=self._disturbance_count,
        )
        annotated = draw_text_panel(
            raw_frame.copy(),
            [
                f"reward={reward:.3f} done={done} success={success}",
                f"raw={np.round(raw_action[:3], 3).tolist()}",
                f"env={np.round(np.clip(raw_action, -1, 1)[:3], 3).tolist()}",
            ],
            fill=(220, 255, 220),
        )
        return MockStepResult(
            policy_step=new_step,
            raw_frame=raw_frame,
            annotated_frame=annotated,
            raw_action=[float(x) for x in raw_action],
            env_action=[float(np.clip(x, -1.0, 1.0)) for x in raw_action],
            reward=float(reward),
            done=done,
            success=success,
            termination_reason=termination_reason,
            current_prompt=self._current_prompt,
            object_position=list(self._object_position),
            inference_seconds=float(inference_seconds),
            env_step_seconds=float(env_step_seconds),
            info={
                "mock": True,
                "disturbed": self._disturbed,
                "disturbance_count": self._disturbance_count,
                "object_position": list(self._object_position),
            },
        )

    def render_frame(
        self,
        config: MockRunConfig,
        *,
        policy_step: int,
        paused: bool,
        state_label: str,
        task_text: str,
        prompt: str,
        object_position: list[float],
        disturbed: bool,
        disturbance_count: int,
    ) -> np.ndarray:
        cfg = config.validated()
        size = int(cfg.frame_size)
        yy, xx = np.mgrid[0:size, 0:size]
        base_r = (xx * 0.55 + policy_step * 6 + cfg.task_id * 15) % 255
        base_g = (yy * 0.70 + cfg.trial_id * 19 + (80 if disturbed else 20)) % 255
        base_b = ((xx + yy) * 0.22 + len(cfg.mode) * 9) % 255
        frame = np.stack([base_r, base_g, base_b], axis=-1).astype(np.uint8)

        obj_x = int(np.clip(object_position[0], 0.0, 1.0) * (size - 1))
        obj_y = int(np.clip(object_position[1], 0.0, 1.0) * (size - 1))
        radius = max(8, size // 18)
        mask = (xx - obj_x) ** 2 + (yy - obj_y) ** 2 <= radius**2
        frame[mask] = np.array([255, 218 if disturbed else 86, 45 if disturbed else 90], dtype=np.uint8)
        frame[max(0, obj_y - 1) : min(size, obj_y + 2), :, :] = np.array([40, 40, 40], dtype=np.uint8)
        frame[:, max(0, obj_x - 1) : min(size, obj_x + 2), :] = np.array([40, 40, 40], dtype=np.uint8)

        prompt_flag = "recovery" if prompt != task_text else "original"
        lines = [
            f"task: {task_text}",
            f"step: {policy_step}/{cfg.max_steps}   state: {state_label}",
            f"mode: {cfg.mode}   prompt: {prompt_flag}",
            f"disturbed: {disturbed} count={disturbance_count} paused={paused}",
            f"object: x={object_position[0]:.2f} y={object_position[1]:.2f}",
        ]
        return draw_text_panel(frame, lines)

    def _task_text_for(self, task_id: int) -> str:
        templates = [
            "pick up the red mug and place it on the plate",
            "move the yellow bowl into the drawer",
            "put the tomato sauce on the basket",
            "place the kettle next to the cup",
        ]
        return templates[task_id % len(templates)]

    def _target_joints_for(self, task_id: int) -> list[str]:
        base = [
            "red_mug_main_joint0",
            "yellow_bowl_main_joint0",
            "tomato_sauce_1_joint0",
            "kettle_main_joint0",
        ]
        preferred = base[task_id % len(base)]
        return [preferred] + [joint for joint in base if joint != preferred]

    def _resolve_target_joint(self, target_joint: str, candidates: list[str]) -> str:
        if not candidates:
            raise ValueError("No mock target joints are available.")
        if target_joint == "auto":
            return candidates[0]
        if target_joint not in candidates:
            raise ValueError(f"Requested target joint is not available: {target_joint}")
        return target_joint

    def object_phrase_from_joint(self, joint: str | None = None) -> str:
        joint = joint or self._resolved_target_joint
        phrase = joint.replace("_main_joint0", "").replace("_joint0", "").replace("_", " ")
        return phrase.strip() or "object"

    def infer_goal_phrase(self) -> str:
        if "plate" in self._task_text:
            return "the plate"
        if "drawer" in self._task_text:
            return "the drawer"
        if "basket" in self._task_text:
            return "the basket"
        if "cup" in self._task_text:
            return "next to the cup"
        return "the original goal location"

    def _make_action(self, config: MockRunConfig, policy_step: int) -> list[float]:
        phase = policy_step / max(1, config.max_steps)
        values = [
            math.sin(policy_step * 0.37),
            math.cos(policy_step * 0.31),
            self._object_position[0] * 2 - 1,
            self._object_position[1] * 2 - 1,
            1.0 if self._disturbed else -1.0,
            phase * 2 - 1,
            -1.0 if policy_step % 2 else 1.0,
        ]
        while len(values) < config.action_dim:
            values.append(self._rng.uniform(-0.5, 0.5))
        return [float(v) for v in values[: config.action_dim]]

    def _advance_object_toward_goal(self, config: MockRunConfig) -> None:
        if config.mode == "verifier_stop" and self._disturbed:
            return
        goal = [0.78, 0.74]
        speed = 0.012 if self._disturbed and config.mode == "reactive_disturbed" else 0.018
        if config.mode in {"structured_relocalize_prompt", "stage_backtrack_subgoal"} and self._disturbed:
            speed = 0.026
        self._object_position[0] += (goal[0] - self._object_position[0]) * speed
        self._object_position[1] += (goal[1] - self._object_position[1]) * speed

    def _reward_for(self, config: MockRunConfig, policy_step: int) -> float:
        progress = min(1.0, policy_step / max(1, min(config.success_step, config.max_steps)))
        disturbance_penalty = 0.10 if self._disturbed and config.mode == "reactive_disturbed" else 0.0
        recovery_bonus = 0.08 if self._disturbed and config.mode in {"structured_relocalize_prompt", "stage_backtrack_subgoal"} else 0.0
        return max(0.0, min(1.0, progress - disturbance_penalty + recovery_bonus))
