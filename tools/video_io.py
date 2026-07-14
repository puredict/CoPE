from __future__ import annotations

import json
import math
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont


UNKNOWN = "unknown"
SUPPORTED_MODES = {
    "clean",
    "reactive_disturbed",
    "reactive",
    "structured",
    "stage_backtrack",
}


def warn(warnings: list[str], message: str) -> None:
    warnings.append(message)


def print_warnings(warnings: Iterable[str]) -> None:
    for message in warnings:
        print(f"warning: {message}", file=sys.stderr)


def load_json(path: Path | None, warnings: list[str], label: str) -> dict[str, Any]:
    if path is None:
        warn(warnings, f"{label} path was not provided")
        return {}
    if not path.exists():
        warn(warnings, f"{label} missing: {path}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - exact parser error text is not important.
        warn(warnings, f"{label} could not be read as JSON: {path}: {exc}")
        return {}


def load_jsonl(path: Path | None, warnings: list[str], label: str) -> list[dict[str, Any]]:
    if path is None:
        warn(warnings, f"{label} path was not provided")
        return []
    if not path.exists():
        warn(warnings, f"{label} missing: {path}")
        return []
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception as exc:
            warn(warnings, f"{label} line {line_no} is not valid JSON: {exc}")
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            warn(warnings, f"{label} line {line_no} is not a JSON object")
    return rows


def nested_get(data: Any, *paths: str, default: Any = None) -> Any:
    for path in paths:
        cur = data
        ok = True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return default


def first_present(*values: Any, default: Any = UNKNOWN) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return default


def coerce_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def coerce_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def compact_value(value: Any, max_chars: int = 64) -> str:
    if value is None:
        return UNKNOWN
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, (int, bool)):
        return str(value)
    if isinstance(value, (list, tuple)):
        items = []
        for item in list(value)[:3]:
            if isinstance(item, (float, int)):
                items.append(f"{float(item):.4g}")
            else:
                items.append(str(item))
        suffix = ", ..." if len(value) > 3 else ""
        return "[" + ", ".join(items) + suffix + "]"
    text = str(value)
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text


def normalise_mode(mode: str | None, fallback: str = UNKNOWN) -> str:
    if not mode:
        return fallback
    mode = str(mode).strip()
    if mode == "disturbed":
        return "reactive_disturbed"
    return mode


@dataclass
class RolloutMetadata:
    source: str
    video_path: Path
    camera: str = "policy"
    run_config: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    mode: str = UNKNOWN
    title: str = UNKNOWN
    warnings: list[str] = field(default_factory=list)
    fps: float = 30.0
    frame_count: int = 0

    @property
    def action_by_frame(self) -> dict[int, dict[str, Any]]:
        by_frame: dict[int, dict[str, Any]] = {}
        for index, action in enumerate(self.actions):
            frame_index = coerce_int(
                first_present(
                    action.get("video_frame_index"),
                    action.get("frame_index"),
                    action.get("frame"),
                    default=index,
                ),
                index,
            )
            if frame_index is not None:
                by_frame[frame_index] = action
        return by_frame

    @property
    def action_by_policy_step(self) -> dict[int, dict[str, Any]]:
        by_step: dict[int, dict[str, Any]] = {}
        for index, action in enumerate(self.actions):
            step = coerce_int(
                first_present(
                    action.get("policy_step"),
                    action.get("t"),
                    action.get("step"),
                    default=index,
                ),
                index,
            )
            if step is not None:
                by_step[step] = action
        return by_step

    @property
    def min_policy_step(self) -> int:
        if self.action_by_policy_step:
            return min(self.action_by_policy_step)
        return 0

    @property
    def max_policy_step(self) -> int:
        if self.action_by_policy_step:
            return max(self.action_by_policy_step)
        return max(0, self.frame_count - 1)

    @property
    def disturbance_step(self) -> int | None:
        return infer_disturbance_step(self)


def default_path(directory: Path | None, name: str, explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit
    if directory is None:
        return None
    candidate = directory / name
    return candidate if candidate.exists() else None


def infer_video_path(source: Path | None, explicit: Path | None, warnings: list[str]) -> Path:
    if explicit is not None:
        return explicit
    if source is None:
        raise ValueError("--video or --episode-dir is required")
    if source.is_file():
        return source
    for name in ("raw.mp4", "annotated.mp4", "video.mp4"):
        candidate = source / name
        if candidate.exists():
            return candidate
    matches = sorted(source.glob("*.mp4"))
    if matches:
        warn(warnings, f"using first mp4 in {source}: {matches[0].name}")
        return matches[0]
    raise FileNotFoundError(f"no mp4 found in {source}")


def read_video(path: Path, warnings: list[str]) -> tuple[list[np.ndarray], float]:
    if not path.exists():
        raise FileNotFoundError(path)
    reader = imageio.get_reader(path)
    try:
        meta = reader.get_meta_data()
        fps = coerce_float(meta.get("fps"), 30.0) or 30.0
        frames = [ensure_rgb(frame) for frame in reader]
    finally:
        reader.close()
    if not frames:
        warn(warnings, f"video has no frames: {path}")
    if fps <= 0:
        warn(warnings, f"video fps was invalid for {path}; using render fps 30")
        fps = 30.0
    return frames, fps


def write_video(path: Path, frames: Iterable[np.ndarray], fps: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio.get_writer(path, fps=float(fps), macro_block_size=1)
    try:
        for frame in frames:
            writer.append_data(ensure_rgb(frame))
    finally:
        writer.close()


def ensure_rgb(frame: np.ndarray) -> np.ndarray:
    arr = np.asarray(frame)
    if arr.ndim == 2:
        arr = np.repeat(arr[:, :, None], 3, axis=2)
    if arr.shape[2] == 4:
        arr = arr[:, :, :3]
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    return arr


def load_rollout_metadata(
    *,
    source: Path | None = None,
    video: Path | None = None,
    run_config: Path | None = None,
    events: Path | None = None,
    actions: Path | None = None,
    episode_summary: Path | None = None,
    mode: str | None = None,
    title: str | None = None,
    camera: str = "policy",
    read_video_info: bool = True,
) -> tuple[RolloutMetadata, list[np.ndarray] | None]:
    warnings: list[str] = []
    episode_dir = source if source is not None and source.is_dir() else None
    video_path = infer_video_path(source, video, warnings)
    run_config_path = default_path(episode_dir, "run_config.json", run_config)
    events_path = default_path(episode_dir, "events.jsonl", events)
    actions_path = default_path(episode_dir, "actions.jsonl", actions)
    summary_path = default_path(episode_dir, "episode_summary.json", episode_summary)

    cfg = load_json(run_config_path, warnings, "run_config")
    event_rows = load_jsonl(events_path, warnings, "events")
    action_rows = load_jsonl(actions_path, warnings, "actions")
    summary = load_json(summary_path, warnings, "episode_summary")

    inferred_mode = normalise_mode(
        first_present(
            mode,
            summary.get("mode"),
            summary.get("condition"),
            cfg.get("mode"),
            cfg.get("condition"),
            default=UNKNOWN,
        )
    )
    if inferred_mode == UNKNOWN:
        path_text = str(source or video_path)
        for candidate in SUPPORTED_MODES:
            if candidate in path_text:
                inferred_mode = candidate
                break
    inferred_title = title or inferred_mode or video_path.stem
    if camera not in {"policy", "observer"}:
        warn(warnings, f"camera must be policy or observer; got {camera!r}; using policy")
        camera = "policy"

    frames: list[np.ndarray] | None = None
    fps = 30.0
    frame_count = 0
    if read_video_info:
        frames, fps = read_video(video_path, warnings)
        frame_count = len(frames)

    metadata = RolloutMetadata(
        source=str(source or video_path),
        video_path=video_path,
        camera=camera,
        run_config=cfg,
        events=event_rows,
        actions=action_rows,
        summary=summary,
        mode=inferred_mode,
        title=inferred_title,
        warnings=warnings,
        fps=fps,
        frame_count=frame_count,
    )
    required = {
        "task description": infer_task_description(metadata),
        "mode": metadata.mode,
        "initial state": infer_initial_state(metadata),
        "seed": infer_seed(metadata),
        "target joint": infer_target_joint(metadata),
        "episode status": infer_episode_status(metadata),
    }
    for label, value in required.items():
        if value == UNKNOWN or value is None:
            warn(metadata.warnings, f"{label} is missing; displaying unknown")
    if metadata.camera == "policy":
        warn(metadata.warnings, "camera is policy; output will not label it as observer or third-person")
    return metadata, frames


def infer_task_description(meta: RolloutMetadata) -> str:
    return str(
        first_present(
            meta.summary.get("task_description"),
            nested_get(meta.summary, "task.description"),
            nested_get(meta.run_config, "task_description"),
            nested_get(meta.run_config, "task.description"),
            default=UNKNOWN,
        )
    )


def infer_initial_state(meta: RolloutMetadata) -> Any:
    return first_present(
        meta.summary.get("initial_state_id"),
        nested_get(meta.summary, "pair_key.initial_state_id"),
        meta.run_config.get("initial_state_id"),
        nested_get(meta.run_config, "args.initial_state_id"),
        meta.summary.get("trial_id"),
        nested_get(meta.run_config, "args.trial_id"),
        default=UNKNOWN,
    )


def infer_seed(meta: RolloutMetadata) -> Any:
    return first_present(
        meta.summary.get("seed"),
        nested_get(meta.summary, "pair_key.seed"),
        meta.run_config.get("seed"),
        nested_get(meta.run_config, "args.seed"),
        default=UNKNOWN,
    )


def infer_target_joint(meta: RolloutMetadata) -> str:
    return str(
        first_present(
            meta.summary.get("target_joint"),
            nested_get(meta.summary, "pair_key.target_joint"),
            meta.run_config.get("target_joint"),
            nested_get(meta.run_config, "args.target_joint"),
            default=UNKNOWN,
        )
    )


def infer_policy_budget(meta: RolloutMetadata) -> int | None:
    return coerce_int(
        first_present(
            meta.summary.get("policy_step_budget"),
            nested_get(meta.summary, "budget.policy_step_budget"),
            nested_get(meta.summary, "pair_key.max_policy_steps"),
            meta.run_config.get("policy_step_budget"),
            nested_get(meta.run_config, "args.max_steps"),
            default=None,
        )
    )


def infer_warmup_steps(meta: RolloutMetadata) -> int:
    return coerce_int(
        first_present(
            meta.summary.get("warmup_simulator_steps"),
            nested_get(meta.summary, "budget.warmup_simulator_steps"),
            nested_get(meta.summary, "pair_key.warmup_env_steps"),
            nested_get(meta.run_config, "args.num_steps_wait"),
            default=0,
        ),
        0,
    ) or 0


def infer_episode_status(meta: RolloutMetadata) -> str:
    return str(
        first_present(
            meta.summary.get("status"),
            nested_get(meta.summary, "episode_status.status"),
            "success" if meta.summary.get("success") is True else None,
            "timeout" if meta.summary.get("timeout") is True else None,
            default=UNKNOWN,
        )
    )


def infer_formality(meta: RolloutMetadata) -> str:
    manual = first_present(
        meta.summary.get("manual_intervention"),
        meta.run_config.get("manual_intervention"),
        nested_get(meta.run_config, "args.manual_intervention"),
        default=None,
    )
    if manual is True:
        return "interactive"
    if manual is False:
        return "formal"
    return UNKNOWN


def infer_disturbance_step(meta: RolloutMetadata) -> int | None:
    value = first_present(
        meta.summary.get("disturbance_step"),
        nested_get(meta.summary, "pair_key.disturbance_step"),
        nested_get(meta.run_config, "args.disturbance_step"),
        meta.run_config.get("disturbance_step"),
        default=None,
    )
    step = coerce_int(value)
    if step is not None:
        return step
    for event in meta.events:
        name = str(first_present(event.get("event"), event.get("type"), event.get("name"), default=""))
        if "disturbance" in name:
            event_step = coerce_int(
                first_present(
                    event.get("policy_step"),
                    event.get("t"),
                    event.get("step"),
                    event.get("disturbance_step"),
                    default=None,
                )
            )
            if event_step is not None:
                return event_step
    disturbance = meta.summary.get("disturbance")
    if isinstance(disturbance, dict):
        return coerce_int(first_present(disturbance.get("policy_step"), disturbance.get("step"), default=None))
    return None


def infer_target_position(meta: RolloutMetadata, policy_step: int | None) -> Any:
    disturbance_step = meta.disturbance_step
    disturbance = meta.summary.get("disturbance")
    if isinstance(disturbance, dict) and disturbance_step is not None and policy_step is not None:
        if policy_step >= disturbance_step:
            after = first_present(
                disturbance.get("after_qpos"),
                disturbance.get("after_xyz"),
                disturbance.get("target_qpos_after"),
                default=None,
            )
            if after is not None:
                return after
        before = first_present(
            disturbance.get("before_qpos"),
            disturbance.get("before_xyz"),
            disturbance.get("target_qpos_before"),
            default=None,
        )
        if before is not None:
            return before
    return first_present(
        meta.summary.get("policy_start_target_qpos"),
        meta.summary.get("initial_target_qpos"),
        nested_get(meta.summary, "target_position"),
        nested_get(meta.run_config, "target_position"),
        default=UNKNOWN,
    )


def action_for_frame(meta: RolloutMetadata, frame_index: int) -> dict[str, Any]:
    action = meta.action_by_frame.get(frame_index)
    if action is not None:
        return action
    if 0 <= frame_index < len(meta.actions):
        return meta.actions[frame_index]
    return {}


def policy_step_for_frame(meta: RolloutMetadata, frame_index: int) -> int:
    action = action_for_frame(meta, frame_index)
    return coerce_int(
        first_present(action.get("policy_step"), action.get("t"), action.get("step"), default=frame_index),
        frame_index,
    ) or frame_index


def environment_step_for(meta: RolloutMetadata, action: dict[str, Any], policy_step: int) -> int | str:
    value = first_present(
        action.get("environment_step"),
        action.get("env_step"),
        action.get("sim_step"),
        default=None,
    )
    env_step = coerce_int(value)
    if env_step is not None:
        return env_step
    warmup = infer_warmup_steps(meta)
    return policy_step + warmup


def reward_for(meta: RolloutMetadata, action: dict[str, Any]) -> Any:
    return first_present(action.get("reward"), meta.summary.get("final_reward"), default=UNKNOWN)


def fresh_observation_for(action: dict[str, Any]) -> Any:
    return first_present(
        action.get("uses_post_disturbance_fresh_observation"),
        action.get("fresh_observation"),
        action.get("used_fresh_observation"),
        default=UNKNOWN,
    )


def frame_overlay_lines(meta: RolloutMetadata, frame_index: int) -> tuple[list[str], dict[str, Any]]:
    action = action_for_frame(meta, frame_index)
    policy_step = policy_step_for_frame(meta, frame_index)
    env_step = environment_step_for(meta, action, policy_step)
    budget = infer_policy_budget(meta)
    budget_remaining = UNKNOWN if budget is None else max(0, budget - policy_step - 1)
    disturbance_step = meta.disturbance_step
    target_position = infer_target_position(meta, policy_step)
    reward = reward_for(meta, action)
    fresh_observation = fresh_observation_for(action)
    status = infer_episode_status(meta)
    formality = infer_formality(meta)

    lines = [
        f"task: {infer_task_description(meta)}",
        f"mode: {meta.mode} | camera: {meta.camera} | run: {formality}",
        f"initial state: {compact_value(infer_initial_state(meta))} | seed: {compact_value(infer_seed(meta))}",
        f"policy step: {policy_step} | environment step: {compact_value(env_step)}",
        f"disturbance step: {compact_value(disturbance_step)}",
        f"target joint: {infer_target_joint(meta)}",
        f"target position: {compact_value(target_position)}",
        f"fresh observation: {compact_value(fresh_observation)}",
        f"policy budget remaining: {compact_value(budget_remaining)}",
        f"reward: {compact_value(reward)} | episode status: {status}",
    ]
    facts = {
        "policy_step": policy_step,
        "environment_step": env_step,
        "disturbance_step": disturbance_step,
        "fresh_observation": fresh_observation,
        "episode_status": status,
        "reward": reward,
    }
    return lines, facts


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=text_font)
    return box[2] - box[0], box[3] - box[1]


def wrap_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    text_font: ImageFont.ImageFont,
    width: int,
) -> list[str]:
    if text_size(draw, text, text_font)[0] <= width:
        return [text]
    approx = max(12, int(width / max(6, text_font.size * 0.58))) if hasattr(text_font, "size") else 36
    wrapped: list[str] = []
    for part in textwrap.wrap(text, width=approx, break_long_words=True, replace_whitespace=False):
        while text_size(draw, part, text_font)[0] > width and len(part) > 1:
            cut = max(1, int(len(part) * width / max(text_size(draw, part, text_font)[0], 1)) - 1)
            wrapped.append(part[:cut])
            part = part[cut:]
        wrapped.append(part)
    return wrapped or [text[:approx]]


def draw_translucent_rect(
    image: Image.Image,
    xy: tuple[int, int, int, int],
    fill: tuple[int, int, int, int],
) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle(xy, fill=fill)
    image.alpha_composite(overlay)


def draw_rollout_overlay(frame: np.ndarray, meta: RolloutMetadata, frame_index: int) -> np.ndarray:
    rgb = ensure_rgb(frame)
    image = Image.fromarray(rgb).convert("RGBA")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    scale = max(0.75, min(width, height) / 256.0)
    body_font = font(max(10, int(12 * scale)))
    title_font = font(max(11, int(14 * scale)), bold=True)
    line_h = max(text_size(draw, "Ag", body_font)[1] + 5, int(15 * scale))
    margin = max(6, int(8 * scale))
    panel_w = min(width - margin * 2, max(int(width * 0.45), min(560, width - margin * 2)))

    lines, facts = frame_overlay_lines(meta, frame_index)
    visible: list[str] = []
    for line in lines:
        visible.extend(wrap_to_width(draw, line, body_font, panel_w - margin * 2))
    max_lines = max(4, min(len(visible), int((height * 0.55) / line_h)))
    visible = visible[:max_lines]
    panel_h = margin * 2 + line_h * (len(visible) + 1)
    draw_translucent_rect(image, (margin, margin, margin + panel_w, margin + panel_h), (0, 0, 0, 150))
    draw.text((margin * 2, margin * 2), "LIBERO rollout", font=title_font, fill=(255, 255, 255, 255))
    y = margin * 2 + line_h
    for line in visible:
        draw.text((margin * 2, y), line, font=body_font, fill=(242, 245, 247, 255))
        y += line_h

    disturbance_step = facts["disturbance_step"]
    policy_step = facts["policy_step"]
    if disturbance_step is not None and abs(policy_step - disturbance_step) <= 1:
        border = max(4, int(5 * scale))
        color = (255, 88, 42, 230)
        for offset in range(border):
            draw.rectangle((offset, offset, width - 1 - offset, height - 1 - offset), outline=color)
        banner = "DISTURBANCE APPLIED" if policy_step == disturbance_step else "DISTURBANCE WINDOW"
        tw, th = text_size(draw, banner, title_font)
        bx2 = width - margin
        bx1 = max(margin, bx2 - tw - margin * 2)
        by1 = margin
        by2 = by1 + th + margin * 2
        draw_translucent_rect(image, (bx1, by1, bx2, by2), (255, 88, 42, 210))
        draw = ImageDraw.Draw(image)
        draw.text((bx1 + margin, by1 + margin), banner, font=title_font, fill=(255, 255, 255, 255))
    elif disturbance_step is not None and policy_step > disturbance_step:
        tag = "post-disturbance"
        tag_font = font(max(9, int(11 * scale)), bold=True)
        tw, th = text_size(draw, tag, tag_font)
        bx2 = width - margin
        bx1 = max(margin, bx2 - tw - margin * 2)
        by2 = height - margin
        by1 = max(margin, by2 - th - margin * 2)
        draw_translucent_rect(image, (bx1, by1, bx2, by2), (102, 48, 24, 160))
        draw = ImageDraw.Draw(image)
        draw.text((bx1 + margin, by1 + margin), tag, font=tag_font, fill=(255, 235, 220, 255))

    return np.asarray(image.convert("RGB"))


def annotate_video(
    *,
    source: Path | None,
    video: Path | None,
    run_config: Path | None,
    events: Path | None,
    actions: Path | None,
    episode_summary: Path | None,
    output: Path,
    fps: float | None = None,
    sidecar_json: Path | None = None,
    mode: str | None = None,
    title: str | None = None,
    camera: str = "policy",
) -> dict[str, Any]:
    meta, frames = load_rollout_metadata(
        source=source,
        video=video,
        run_config=run_config,
        events=events,
        actions=actions,
        episode_summary=episode_summary,
        mode=mode,
        title=title,
        camera=camera,
    )
    assert frames is not None
    render_fps = float(fps or meta.fps or 30.0)
    annotated = (draw_rollout_overlay(frame, meta, index) for index, frame in enumerate(frames))
    write_video(output, annotated, render_fps)
    sidecar = {
        "tool": "annotate_rollout_video",
        "source": meta.source,
        "video_path": str(meta.video_path),
        "output_path": str(output),
        "mode": meta.mode,
        "camera": meta.camera,
        "frame_count": len(frames),
        "source_fps_render_only": meta.fps,
        "output_fps_render_only": render_fps,
        "policy_step_range": [meta.min_policy_step, meta.max_policy_step],
        "disturbance_step": meta.disturbance_step,
        "warnings": meta.warnings,
    }
    if sidecar_json is not None:
        sidecar_json.parent.mkdir(parents=True, exist_ok=True)
        sidecar_json.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    return sidecar


@dataclass
class LoadedRollout:
    meta: RolloutMetadata
    frames: list[np.ndarray]
    anchor_step: int


def parse_labeled_source(value: str) -> tuple[str, Path]:
    if "=" not in value:
        path = Path(value)
        return path.stem, path
    label, path = value.split("=", 1)
    label = label.strip()
    if not label:
        raise ValueError(f"empty label in input spec: {value}")
    return normalise_mode(label), Path(path)


def load_comparison_inputs(inputs: list[str], camera: str) -> list[LoadedRollout]:
    loaded: list[LoadedRollout] = []
    for spec in inputs:
        label, source = parse_labeled_source(spec)
        meta, frames = load_rollout_metadata(source=source, mode=label, title=label, camera=camera)
        assert frames is not None
        anchor = meta.disturbance_step
        if anchor is None:
            anchor = coerce_int(
                first_present(
                    nested_get(meta.summary, "pair_key.disturbance_step"),
                    nested_get(meta.run_config, "args.disturbance_step"),
                    default=0,
                ),
                0,
            ) or 0
            warn(meta.warnings, f"disturbance anchor missing for {label}; using {anchor}")
        loaded.append(LoadedRollout(meta=meta, frames=frames, anchor_step=anchor))
    return loaded


def step_to_frame_index(meta: RolloutMetadata, source_step: int) -> int | None:
    action = meta.action_by_policy_step.get(source_step)
    if action is not None:
        return coerce_int(
            first_present(
                action.get("video_frame_index"),
                action.get("frame_index"),
                action.get("frame"),
                default=source_step,
            ),
            source_step,
        )
    if not meta.actions and 0 <= source_step < meta.frame_count:
        return source_step
    return None


def select_frame(
    loaded: LoadedRollout,
    shared_step: int,
    alignment: str,
    padding: str,
    cell_shape: tuple[int, int],
) -> tuple[np.ndarray, int | None]:
    source_step = shared_step if alignment == "policy_step" else shared_step + loaded.anchor_step
    frame_index = step_to_frame_index(loaded.meta, source_step)
    if frame_index is None or frame_index < 0 or frame_index >= len(loaded.frames):
        if padding == "black":
            cell_w, cell_h = cell_shape
            return np.zeros((cell_h, cell_w, 3), dtype=np.uint8), None
        if source_step < loaded.meta.min_policy_step:
            frame_index = 0
        else:
            frame_index = len(loaded.frames) - 1
    return loaded.frames[frame_index], frame_index


def resize_letterbox(
    frame: np.ndarray,
    target_w: int,
    target_h: int,
    fill: tuple[int, int, int] = (16, 18, 20),
) -> np.ndarray:
    rgb = ensure_rgb(frame)
    src_h, src_w = rgb.shape[:2]
    if src_w == 0 or src_h == 0:
        return np.full((target_h, target_w, 3), fill, dtype=np.uint8)
    scale = min(target_w / src_w, target_h / src_h)
    new_w = max(1, int(round(src_w * scale)))
    new_h = max(1, int(round(src_h * scale)))
    image = Image.fromarray(rgb).resize((new_w, new_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), fill)
    canvas.paste(image, ((target_w - new_w) // 2, (target_h - new_h) // 2))
    return np.asarray(canvas)


def draw_title(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str, camera: str) -> None:
    x1, y1, x2, y2 = box
    title_font = font(18, bold=True)
    body_font = font(12)
    label = title
    subtitle = f"{camera} camera"
    tw, th = text_size(draw, label, title_font)
    while tw > x2 - x1 - 16 and len(label) > 3:
        label = label[:-4] + "..."
        tw, th = text_size(draw, label, title_font)
    draw.text((x1 + 8, y1 + 6), label, font=title_font, fill=(246, 248, 250))
    draw.text((x1 + 8, y1 + 27), subtitle, font=body_font, fill=(174, 184, 194))


def draw_timeline(
    draw: ImageDraw.ImageDraw,
    *,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    shared_step: int,
    start_step: int,
    end_step: int,
    alignment: str,
) -> None:
    body_font = font(13)
    title_font = font(13, bold=True)
    label = (
        f"shared policy step {shared_step}"
        if alignment == "policy_step"
        else f"disturbance-aligned step {shared_step:+d} (0 = disturbance)"
    )
    draw.text((x1, y1), label, font=title_font, fill=(238, 242, 246))
    line_y = y1 + 28
    draw.line((x1, line_y, x2, line_y), fill=(90, 100, 110), width=2)
    denom = max(1, end_step - start_step)
    frac = (shared_step - start_step) / denom
    dot_x = int(x1 + frac * (x2 - x1))
    draw.ellipse((dot_x - 5, line_y - 5, dot_x + 5, line_y + 5), fill=(255, 190, 68))
    draw.text((x1, y2 - 18), str(start_step), font=body_font, fill=(174, 184, 194))
    end_text = str(end_step)
    ew, _ = text_size(draw, end_text, body_font)
    draw.text((x2 - ew, y2 - 18), end_text, font=body_font, fill=(174, 184, 194))


def compose_comparison(
    *,
    inputs: list[str],
    output: Path,
    sidecar_json: Path,
    alignment: str = "policy_step",
    padding: str = "freeze-last",
    fps: float | None = None,
    cell_width: int | None = None,
    cell_height: int | None = None,
    camera: str = "policy",
) -> dict[str, Any]:
    if len(inputs) < 2:
        raise ValueError("at least two --input entries are required")
    alignment = alignment.replace("-", "_")
    if alignment not in {"policy_step", "disturbance_step"}:
        raise ValueError("--align must be policy-step or disturbance-step")
    padding = padding.replace("_", "-")
    if padding not in {"freeze-last", "black"}:
        raise ValueError("--padding must be freeze-last or black")

    loaded = load_comparison_inputs(inputs, camera)
    render_fps = float(fps or loaded[0].meta.fps or 30.0)
    max_w = max(frame.shape[1] for item in loaded for frame in item.frames[:1])
    max_h = max(frame.shape[0] for item in loaded for frame in item.frames[:1])
    cell_w = int(cell_width or max_w)
    cell_h = int(cell_height or max_h)

    if alignment == "policy_step":
        start_step = min(0, *(item.meta.min_policy_step for item in loaded))
        end_step = max(item.meta.max_policy_step for item in loaded)
    else:
        start_step = min(item.meta.min_policy_step - item.anchor_step for item in loaded)
        end_step = max(item.meta.max_policy_step - item.anchor_step for item in loaded)

    margin = 10
    gap = 8
    header_h = 50
    timeline_h = 54
    canvas_w = margin * 2 + cell_w * len(loaded) + gap * (len(loaded) - 1)
    canvas_h = margin * 2 + header_h + cell_h + timeline_h
    frames_out: list[np.ndarray] = []
    timeline_steps = list(range(start_step, end_step + 1))

    for shared_step in timeline_steps:
        canvas = Image.new("RGB", (canvas_w, canvas_h), (11, 13, 16))
        draw = ImageDraw.Draw(canvas)
        x = margin
        for item in loaded:
            draw.rounded_rectangle((x, margin, x + cell_w, margin + header_h - 4), radius=4, fill=(25, 29, 34))
            draw_title(draw, (x, margin, x + cell_w, margin + header_h - 4), item.meta.title, item.meta.camera)
            frame, _ = select_frame(item, shared_step, alignment, padding, (cell_w, cell_h))
            cell = resize_letterbox(frame, cell_w, cell_h)
            canvas.paste(Image.fromarray(cell), (x, margin + header_h))
            x += cell_w + gap
        draw_timeline(
            draw,
            x1=margin,
            y1=margin + header_h + cell_h + 8,
            x2=canvas_w - margin,
            y2=canvas_h - margin,
            shared_step=shared_step,
            start_step=start_step,
            end_step=end_step,
            alignment=alignment,
        )
        frames_out.append(np.asarray(canvas))

    write_video(output, frames_out, render_fps)
    sidecar = {
        "tool": "compose_rollout_comparison",
        "inputs": [
            {
                "label": item.meta.title,
                "mode": item.meta.mode,
                "source": item.meta.source,
                "video_path": str(item.meta.video_path),
                "frame_count": len(item.frames),
                "source_fps_render_only": item.meta.fps,
                "policy_step_range": [item.meta.min_policy_step, item.meta.max_policy_step],
                "disturbance_step": item.meta.disturbance_step,
                "anchor_step": item.anchor_step,
                "camera": item.meta.camera,
                "warnings": item.meta.warnings,
            }
            for item in loaded
        ],
        "output_path": str(output),
        "sidecar_path": str(sidecar_json),
        "alignment": alignment,
        "padding": padding,
        "timeline_start": start_step,
        "timeline_end": end_step,
        "output_frames": len(frames_out),
        "output_fps_render_only": render_fps,
        "cell_width": cell_w,
        "cell_height": cell_h,
    }
    sidecar_json.parent.mkdir(parents=True, exist_ok=True)
    sidecar_json.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    return sidecar


def sidecar_default(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".json")
