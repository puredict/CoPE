from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import imageio


EXPECTED_CHECKPOINT = "/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial"
EXPECTED_DELTA = [0.10, 0.05, 0.0]
EXPECTED_STATES = [0, 1, 2]
EXPECTED_SEEDS = {0: 7, 1: 8, 2: 9}
EXPECTED_MODES = {"clean", "reactive_disturbed"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def close_seq(a, b, tol: float = 1e-9) -> bool:
    if a is None or b is None:
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(close_seq(a[k], b[k], tol) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close_seq(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=tol)
    return a == b


def video_frame_count(path: Path) -> int:
    reader = imageio.get_reader(path)
    try:
        try:
            count = reader.count_frames()
            if count != float("inf"):
                return int(count)
        except Exception:
            pass
        return sum(1 for _ in reader)
    finally:
        reader.close()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_stage2_1.py <run_dir>")

    run_dir = Path(sys.argv[1])
    failures: list[str] = []
    summary_path = run_dir / "summary.json"
    episodes_path = run_dir / "episodes.jsonl"

    if not summary_path.exists():
        failures.append(f"missing {summary_path}")
        summary = {}
    else:
        summary = load_json(summary_path)
    if not episodes_path.exists():
        failures.append(f"missing {episodes_path}")
        records = []
    else:
        records = load_jsonl(episodes_path)

    if len(records) != 6:
        failures.append(f"expected 6 records, got {len(records)}")

    by_state: dict[int, dict[str, dict]] = {state: {} for state in EXPECTED_STATES}
    artifact_sizes = {}
    video_frames = {}

    for idx, record in enumerate(records):
        label = f"record[{idx}]"
        mode = record.get("mode")
        state = record.get("initial_state_id")
        seed = record.get("seed")
        condition = record.get("condition")
        if mode not in EXPECTED_MODES:
            failures.append(f"{label}: unexpected mode {mode}")
        if condition not in {"clean", "disturbed"}:
            failures.append(f"{label}: unexpected condition {condition}")
        if state not in EXPECTED_STATES:
            failures.append(f"{label}: unexpected initial_state_id {state}")
        else:
            by_state[state][mode] = record
            if seed != EXPECTED_SEEDS[state]:
                failures.append(f"{label}: expected seed {EXPECTED_SEEDS[state]} for state {state}, got {seed}")
        if record.get("seed_rule") != "base_plus_initial_state":
            failures.append(f"{label}: unexpected seed_rule {record.get('seed_rule')}")
        if record.get("task_suite") != "libero_spatial":
            failures.append(f"{label}: unexpected suite {record.get('task_suite')}")
        if record.get("task_id") != 0:
            failures.append(f"{label}: unexpected task_id {record.get('task_id')}")
        if record.get("checkpoint") != EXPECTED_CHECKPOINT:
            failures.append(f"{label}: unexpected checkpoint {record.get('checkpoint')}")
        if record.get("target_joint") != "akita_black_bowl_1_joint0":
            failures.append(f"{label}: unexpected target_joint {record.get('target_joint')}")
        if record.get("policy_step_budget") != 220:
            failures.append(f"{label}: unexpected policy_step_budget {record.get('policy_step_budget')}")
        if record.get("warmup_simulator_steps") != 10:
            failures.append(f"{label}: unexpected warmup {record.get('warmup_simulator_steps')}")
        if record.get("manual_intervention") is not False:
            failures.append(f"{label}: manual_intervention is not false")
        if record.get("reset_count") != 0 or record.get("rollback_count") != 0:
            failures.append(f"{label}: reset/rollback count is not zero")
        if record.get("timeout") and record.get("success"):
            failures.append(f"{label}: timeout recorded as success")

        pair_key = record.get("pair_key", {})
        if pair_key.get("disturbance_step") != 70:
            failures.append(f"{label}: unexpected disturbance_step {pair_key.get('disturbance_step')}")
        if not close_seq(pair_key.get("disturbance_delta_xyz"), EXPECTED_DELTA):
            failures.append(f"{label}: unexpected configured delta {pair_key.get('disturbance_delta_xyz')}")

        actions = record.get("actions", [])
        if len(actions) != record.get("num_policy_steps"):
            failures.append(f"{label}: action count mismatch")
        for action_index, action in enumerate(actions):
            if action.get("t") != action_index:
                failures.append(f"{label}: action t mismatch at index {action_index}")
                break
            if action.get("video_frame_index") != action_index:
                failures.append(f"{label}: video_frame_index mismatch at action {action_index}")
                break

        paths = record.get("artifact_paths", {})
        for key in ["run_config", "events", "episode_summary", "actions", "raw_video"]:
            path = Path(paths.get(key, ""))
            if not path.exists():
                failures.append(f"{label}: missing artifact {key}: {path}")
            elif path.stat().st_size <= 0:
                failures.append(f"{label}: empty artifact {key}: {path}")
            else:
                artifact_sizes[str(path)] = path.stat().st_size
        if Path(paths.get("raw_video", "")).exists():
            try:
                frame_count = video_frame_count(Path(paths["raw_video"]))
                video_frames[str(paths["raw_video"])] = frame_count
                if frame_count != len(actions):
                    failures.append(f"{label}: video frame count {frame_count} != actions {len(actions)}")
            except Exception as exc:
                failures.append(f"{label}: could not count video frames: {exc}")

        events_path = Path(paths.get("events", ""))
        actions_path = Path(paths.get("actions", ""))
        run_config_path = Path(paths.get("run_config", ""))
        episode_summary_path = Path(paths.get("episode_summary", ""))
        if events_path.exists():
            events = load_jsonl(events_path)
            policy_events = [event for event in events if event.get("event") == "policy_step"]
            if len(policy_events) != len(actions):
                failures.append(f"{label}: policy event count mismatch")
            for event_index, event in enumerate(policy_events):
                if event.get("policy_step") != event_index or event.get("video_frame_index") != event_index:
                    failures.append(f"{label}: event/action step mismatch at {event_index}")
                    break
        if actions_path.exists() and len(load_jsonl(actions_path)) != len(actions):
            failures.append(f"{label}: actions.jsonl count mismatch")
        if run_config_path.exists():
            run_config = load_json(run_config_path)
            for key in ["checkpoint", "task_id", "initial_state_id", "seed", "mode", "target_joint"]:
                if run_config.get(key) != record.get(key):
                    failures.append(f"{label}: run_config {key} mismatch")
        if episode_summary_path.exists():
            episode_summary = load_json(episode_summary_path)
            if episode_summary.get("num_policy_steps") != record.get("num_policy_steps"):
                failures.append(f"{label}: episode_summary step mismatch")

    for state, modes in by_state.items():
        if set(modes) != EXPECTED_MODES:
            failures.append(f"state {state}: expected modes {sorted(EXPECTED_MODES)}, got {sorted(modes)}")
            continue
        clean = modes["clean"]
        disturbed = modes["reactive_disturbed"]
        for key in [
            "task_suite",
            "task_id",
            "initial_state_id",
            "seed",
            "checkpoint",
            "target_joint",
            "policy_step_budget",
            "warmup_simulator_steps",
        ]:
            if clean.get(key) != disturbed.get(key):
                failures.append(f"state {state}: pair mismatch for {key}")
        for key in [
            "initial_robot_state",
            "initial_target_qpos",
            "initial_target_body_pose",
            "policy_start_robot_state",
            "policy_start_target_qpos",
            "policy_start_target_body_pose",
        ]:
            if not close_seq(clean.get(key), disturbed.get(key)):
                failures.append(f"state {state}: pair state mismatch for {key}")
        disturbance = disturbed.get("disturbance")
        if disturbance is None:
            failures.append(f"state {state}: missing disturbance record")
        else:
            if disturbance.get("joint") != "akita_black_bowl_1_joint0":
                failures.append(f"state {state}: wrong disturbed joint {disturbance.get('joint')}")
            if not close_seq(disturbance.get("delta_xyz_actual"), EXPECTED_DELTA):
                failures.append(f"state {state}: wrong actual delta {disturbance.get('delta_xyz_actual')}")
            refresh = disturbance.get("refresh", {})
            if refresh.get("method") != "env.env._get_observations(force_update=True)":
                failures.append(f"state {state}: unexpected refresh method {refresh.get('method')}")
            if refresh.get("consumed_noop_env_step") is not False:
                failures.append(f"state {state}: refresh consumed noop env step")
        fresh_actions = [
            action
            for action in disturbed.get("actions", [])
            if action.get("t") == 70 and action.get("uses_post_disturbance_fresh_observation")
        ]
        if len(fresh_actions) != 1:
            failures.append(f"state {state}: missing fresh observation action at step 70")

    episode_dirs = [Path(record["artifact_paths"]["episode_dir"]) for record in records if "artifact_paths" in record]
    if len(set(episode_dirs)) != len(episode_dirs):
        failures.append("episode directories are not unique")
    if any(run_dir not in path.parents for path in episode_dirs):
        failures.append("an episode directory is outside the run directory")

    result = {
        "passed": not failures,
        "failures": failures,
        "run_dir": str(run_dir),
        "records": len(records),
        "seed_rule": summary.get("args", {}).get("seed_rule"),
        "episode_outcomes": [
            {
                "mode": record.get("mode"),
                "task_id": record.get("task_id"),
                "initial_state_id": record.get("initial_state_id"),
                "seed": record.get("seed"),
                "status": record.get("status"),
                "success": record.get("success"),
                "timeout": record.get("timeout"),
                "num_policy_steps": record.get("num_policy_steps"),
                "video_path": record.get("video_path"),
            }
            for record in records
        ],
        "artifact_sizes": artifact_sizes,
        "video_frames": video_frames,
    }
    result_path = run_dir / "stage2_1_validation.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
