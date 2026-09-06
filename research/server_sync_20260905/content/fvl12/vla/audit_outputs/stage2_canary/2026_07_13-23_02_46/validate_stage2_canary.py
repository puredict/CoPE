from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def close_list(a, b, tol=1e-9):
    return len(a) == len(b) and all(abs(float(x) - float(y)) <= tol for x, y in zip(a, b))


def close_state(a, b, tol=1e-9):
    return all(close_list(a[key], b[key], tol) for key in ("eef_pos", "eef_quat", "gripper_qpos"))


def check(condition, message, failures):
    if not condition:
        failures.append(message)


def main() -> int:
    run_dir = Path(sys.argv[1])
    summary_path = run_dir / "summary.json"
    episodes_path = run_dir / "episodes.jsonl"
    summary = json.loads(summary_path.read_text())
    records = [json.loads(line) for line in episodes_path.read_text().splitlines() if line.strip()]
    failures = []

    check(len(records) == 2, f"expected 2 records, found {len(records)}", failures)
    by_condition = {record["condition"]: record for record in records}
    check(set(by_condition) == {"clean", "disturbed"}, f"unexpected conditions: {sorted(by_condition)}", failures)
    if failures:
        print(json.dumps({"passed": False, "failures": failures}, indent=2))
        return 1

    clean = by_condition["clean"]
    disturbed = by_condition["disturbed"]
    args = summary["args"]

    expected_args = {
        "checkpoint": "/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial",
        "task_suite": "libero_spatial",
        "task_id": 0,
        "trials": 1,
        "max_steps": 220,
        "num_steps_wait": 10,
        "disturbance_step": 70,
        "target_joint": "akita_black_bowl_1_joint0",
        "dx": 0.1,
        "dy": 0.05,
        "seed": 7,
    }
    for key, expected in expected_args.items():
        check(args.get(key) == expected, f"arg {key} mismatch: {args.get(key)!r} != {expected!r}", failures)

    pair_fields = [
        "pair_key",
        "checkpoint",
        "seed",
        "task_suite",
        "task_id",
        "trial_id",
        "initial_state_id",
        "task_description",
        "target_joint",
        "policy_step_budget",
        "warmup_simulator_steps",
        "reset_count",
        "rollback_count",
    ]
    for field in pair_fields:
        check(clean.get(field) == disturbed.get(field), f"pair field {field} differs", failures)

    check(clean["mode"] == "clean", "clean mode mismatch", failures)
    check(disturbed["mode"] == "reactive_disturbed", "disturbed mode mismatch", failures)
    check(clean["manual_intervention"] is False, "clean manual_intervention not false", failures)
    check(disturbed["manual_intervention"] is False, "disturbed manual_intervention not false", failures)
    check(clean["disturbance"] is None, "clean has disturbance record", failures)
    check(isinstance(disturbed["disturbance"], dict), "disturbed missing disturbance record", failures)

    check(close_state(clean["initial_robot_state"], disturbed["initial_robot_state"]), "initial robot state differs", failures)
    check(close_list(clean["initial_target_qpos"], disturbed["initial_target_qpos"]), "initial target qpos differs", failures)
    check(close_state(clean["policy_start_robot_state"], disturbed["policy_start_robot_state"]), "policy-start robot state differs", failures)
    check(close_list(clean["policy_start_target_qpos"], disturbed["policy_start_target_qpos"]), "policy-start target qpos differs", failures)

    disturbance = disturbed["disturbance"]
    actual_delta = disturbance["delta_xyz_actual"]
    check(close_list(actual_delta, [0.1, 0.05, 0.0], tol=1e-8), f"disturbance delta mismatch: {actual_delta}", failures)
    refresh = disturbance["refresh"]
    check(refresh["method"] == "env.env._get_observations(force_update=True)", f"refresh method mismatch: {refresh['method']}", failures)
    check(refresh["consumed_noop_env_step"] is False, "refresh consumed noop/env step", failures)
    check(disturbed["environment_control_steps"] == disturbed["warmup_simulator_steps"] + disturbed["policy_inference_steps"], "disturbed env steps include extra step", failures)
    check(clean["environment_control_steps"] == clean["warmup_simulator_steps"] + clean["policy_inference_steps"], "clean env steps include extra step", failures)

    disturbed_actions = disturbed["actions"]
    clean_actions = clean["actions"]
    check(len(clean_actions) == clean["num_policy_steps"], "clean action count != num_policy_steps", failures)
    check(len(disturbed_actions) == disturbed["num_policy_steps"], "disturbed action count != num_policy_steps", failures)
    for name, record, actions in (("clean", clean, clean_actions), ("disturbed", disturbed, disturbed_actions)):
        for idx, action in enumerate(actions):
            check(action["t"] == idx, f"{name} action t/index mismatch at {idx}", failures)
            check(action["video_frame_index"] == idx, f"{name} video frame/action mismatch at {idx}", failures)
        if record["timeout"]:
            check(record["success"] is False, f"{name} timeout counted as success", failures)

    fresh_actions = [a for a in disturbed_actions if a["t"] == args["disturbance_step"]]
    check(len(fresh_actions) == 1, f"expected one disturbed action at disturbance step, found {len(fresh_actions)}", failures)
    if fresh_actions:
        check(fresh_actions[0]["uses_post_disturbance_fresh_observation"] is True, "post-disturbance action not marked fresh", failures)

    for record in records:
        video = Path(record["video_path"])
        check(video.exists(), f"missing video: {video}", failures)
        if video.exists():
            check(video.stat().st_size > 0, f"empty video: {video}", failures)
            check(video.parent == run_dir, f"video outside run dir: {video}", failures)

    result = {
        "passed": not failures,
        "failures": failures,
        "run_dir": str(run_dir),
        "summary_path": str(summary_path),
        "episodes_path": str(episodes_path),
        "records": len(records),
        "conditions": sorted(by_condition),
        "clean_status": clean["status"],
        "clean_success": clean["success"],
        "clean_policy_steps": clean["num_policy_steps"],
        "disturbed_status": disturbed["status"],
        "disturbed_success": disturbed["success"],
        "disturbed_timeout": disturbed["timeout"],
        "disturbed_policy_steps": disturbed["num_policy_steps"],
        "disturbance_delta_xyz_actual": actual_delta,
        "refresh_method": refresh["method"],
        "refresh_consumed_noop_env_step": refresh["consumed_noop_env_step"],
        "pair_key": clean["pair_key"],
        "video_files": [record["video_path"] for record in records],
    }
    (run_dir / "stage2_canary_validation.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
