from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import imageio.v2 as imageio
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def moving_video(path: Path, *, size: tuple[int, int], frames: int, fps: int = 10) -> None:
    width, height = size
    writer = imageio.get_writer(path, fps=fps, macro_block_size=1)
    try:
        for index in range(frames):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            frame[:, :, 0] = 24
            frame[:, :, 1] = 32 + index
            x = min(width - 12, 2 + index * 3)
            y = min(height - 12, 3 + index * 2)
            frame[y : y + 10, x : x + 10] = np.array([220, 70, 30], dtype=np.uint8)
            writer.append_data(frame)
    finally:
        writer.close()


def make_episode(
    base: Path,
    name: str,
    *,
    mode: str,
    size: tuple[int, int] = (96, 72),
    frames: int = 12,
    disturbance_step: int = 5,
    missing_fields: bool = False,
) -> Path:
    episode_dir = base / name
    episode_dir.mkdir()
    moving_video(episode_dir / "raw.mp4", size=size, frames=frames)
    write_json(
        episode_dir / "run_config.json",
        {
            "args": {
                "disturbance_step": disturbance_step,
                "max_steps": 20,
                "num_steps_wait": 2,
                "seed": 7,
                "target_joint": "akita_black_bowl_1_joint0",
            }
        },
    )
    events = []
    if mode != "clean":
        events.append({"event": "disturbance_applied", "policy_step": disturbance_step})
    write_jsonl(episode_dir / "events.jsonl", events)
    actions = []
    for index in range(frames):
        actions.append(
            {
                "t": index,
                "video_frame_index": index,
                "reward": 1.0 if index == frames - 1 else 0.0,
                "uses_post_disturbance_fresh_observation": index == disturbance_step and mode != "clean",
            }
        )
    write_jsonl(episode_dir / "actions.jsonl", actions)
    summary = {
        "mode": mode,
        "initial_state_id": 0,
        "seed": 7,
        "task_description": "pick up the black bowl and place it on the plate",
        "target_joint": "akita_black_bowl_1_joint0",
        "policy_start_target_qpos": [0.1, 0.2, 0.9, 1, 0, 0, 0],
        "disturbance_step": disturbance_step,
        "disturbance": {
            "before_qpos": [0.1, 0.2, 0.9],
            "after_qpos": [0.2, 0.25, 0.9],
        }
        if mode != "clean"
        else None,
        "status": "timeout" if mode != "clean" else "success",
        "success": mode == "clean",
        "timeout": mode != "clean",
        "policy_step_budget": 20,
        "warmup_simulator_steps": 2,
        "manual_intervention": False,
    }
    if missing_fields:
        summary.pop("task_description")
        summary.pop("target_joint")
        summary.pop("seed")
    write_json(episode_dir / "episode_summary.json", summary)
    return episode_dir


def run_tool(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )


def test_annotate_rollout_video_handles_missing_fields(tmp_path: Path) -> None:
    episode = make_episode(
        tmp_path,
        "reactive_missing",
        mode="reactive_disturbed",
        frames=9,
        disturbance_step=4,
        missing_fields=True,
    )
    output = tmp_path / "annotated.mp4"
    sidecar = tmp_path / "annotated.json"

    result = run_tool(
        [
            "tools/annotate_rollout_video.py",
            "--episode-dir",
            str(episode),
            "--output",
            str(output),
            "--sidecar-json",
            str(sidecar),
        ]
    )

    assert output.exists()
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["frame_count"] == 9
    assert data["camera"] == "policy"
    assert data["disturbance_step"] == 4
    assert "policy" in result.stderr
    assert any("task description" in warning for warning in data["warnings"])


def test_compose_rollout_comparison_aligns_and_pads_different_videos(tmp_path: Path) -> None:
    clean = make_episode(tmp_path, "clean", mode="clean", size=(80, 60), frames=8, disturbance_step=4)
    reactive = make_episode(
        tmp_path,
        "reactive",
        mode="reactive_disturbed",
        size=(120, 70),
        frames=12,
        disturbance_step=5,
    )
    output = tmp_path / "comparison.mp4"
    sidecar = tmp_path / "comparison.json"

    run_tool(
        [
            "tools/compose_rollout_comparison.py",
            "--input",
            f"clean={clean}",
            "--input",
            f"reactive_disturbed={reactive}",
            "--align",
            "disturbance-step",
            "--padding",
            "black",
            "--output",
            str(output),
            "--sidecar-json",
            str(sidecar),
        ]
    )

    assert output.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["alignment"] == "disturbance_step"
    assert data["padding"] == "black"
    assert data["timeline_start"] == -5
    assert data["timeline_end"] == 6
    assert data["output_frames"] == 12
    assert [item["mode"] for item in data["inputs"]] == ["clean", "reactive_disturbed"]


def test_compose_rollout_comparison_policy_step_freeze_last(tmp_path: Path) -> None:
    clean = make_episode(tmp_path, "clean_short", mode="clean", frames=5, disturbance_step=3)
    reactive = make_episode(tmp_path, "reactive_long", mode="reactive_disturbed", frames=7, disturbance_step=3)
    output = tmp_path / "policy.mp4"
    sidecar = tmp_path / "policy.json"

    run_tool(
        [
            "tools/compose_rollout_comparison.py",
            "--input",
            f"clean={clean}",
            "--input",
            f"reactive_disturbed={reactive}",
            "--align",
            "policy-step",
            "--padding",
            "freeze-last",
            "--output",
            str(output),
            "--sidecar-json",
            str(sidecar),
        ]
    )

    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["timeline_start"] == 0
    assert data["timeline_end"] == 6
    assert data["output_frames"] == 7
