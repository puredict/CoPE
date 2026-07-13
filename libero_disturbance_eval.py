from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace

import imageio
import numpy as np

from libero.libero import benchmark, get_libero_path
from libero_experiment_core import (
    extract_episode_status,
    get_joint_qpos,
    json_safe,
    make_budget_report,
    move_free_joint_xy as audited_move_free_joint_xy,
    refresh_observation_after_sim_change,
    select_target_joint,
)

from experiments.robot.libero.libero_utils import (
    get_libero_dummy_action,
    get_libero_env,
    get_libero_image,
    quat2axisangle,
)
from experiments.robot.openvla_utils import get_processor
from experiments.robot.robot_utils import (
    get_action,
    get_image_resize_size,
    get_model,
    invert_gripper_action,
    normalize_gripper_action,
    set_seed_everywhere,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--task-suite", default="libero_spatial")
    parser.add_argument("--task-id", type=int, default=0, help="Use -1 to run all tasks in the suite.")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=220)
    parser.add_argument("--num-steps-wait", type=int, default=10)
    parser.add_argument("--disturbance-step", type=int, default=70)
    parser.add_argument("--target-joint", default="akita_black_bowl_1_joint0", help="Use 'auto' to choose a task-relevant free joint.")
    parser.add_argument("--unnorm-key", default=None, help="Override action un-normalization key; default is task suite.")
    parser.add_argument("--dx", type=float, default=0.10)
    parser.add_argument("--dy", type=float, default=0.05)
    parser.add_argument("--out-dir", default="/home/lijingsu/vla/disturbance_outputs")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--seed-rule",
        choices=["fixed", "base_plus_initial_state"],
        default="fixed",
        help="fixed uses --seed for every episode; base_plus_initial_state uses --seed + initial_state_id.",
    )
    return parser.parse_args()


def make_cfg(args: argparse.Namespace) -> SimpleNamespace:
    cfg = SimpleNamespace()
    cfg.model_family = "openvla"
    cfg.pretrained_checkpoint = args.checkpoint
    cfg.load_in_8bit = False
    cfg.load_in_4bit = False
    cfg.center_crop = True
    cfg.unnorm_key = args.unnorm_key or args.task_suite
    return cfg


def sim_from_env(env):
    return env.env.sim if hasattr(env, "env") else env.sim


def body_pose(sim, body_name: str) -> dict:
    body_id = sim.model.body_name2id(body_name)
    return {
        "body": body_name,
        "xyz": sim.data.body_xpos[body_id].astype(float).tolist(),
    }


def move_free_joint_xy(env, joint_name: str, dx: float, dy: float) -> dict:
    sim = sim_from_env(env)
    joint_id = sim.model.joint_name2id(joint_name)
    qpos_addr = sim.model.jnt_qposadr[joint_id]
    before = sim.data.qpos[qpos_addr : qpos_addr + 7].copy()
    sim.data.qpos[qpos_addr] += dx
    sim.data.qpos[qpos_addr + 1] += dy
    sim.forward()
    after = sim.data.qpos[qpos_addr : qpos_addr + 7].copy()
    return {
        "joint": joint_name,
        "qpos_addr": int(qpos_addr),
        "before_qpos": before.astype(float).tolist(),
        "after_qpos": after.astype(float).tolist(),
        "delta_xy": [dx, dy],
    }


def tokenize(text: str) -> set[str]:
    return {tok for tok in re.split(r"[^a-z0-9]+", text.lower()) if len(tok) > 1}


def choose_target_joint(env, task_description: str) -> str:
    selection = select_target_joint(env, task_description, "auto")
    if selection.selected_joint is None:
        raise ValueError(f"target selection did not produce a joint: {selection.reason}")
    return selection.selected_joint


def save_video(images: list[np.ndarray], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio.get_writer(path, fps=30)
    for image in images:
        writer.append_data(image)
    writer.close()


def robot_state_from_obs(obs: dict) -> dict:
    return {
        "eef_pos": np.asarray(obs["robot0_eef_pos"], dtype=float).tolist(),
        "eef_quat": np.asarray(obs["robot0_eef_quat"], dtype=float).tolist(),
        "gripper_qpos": np.asarray(obs["robot0_gripper_qpos"], dtype=float).tolist(),
    }


def target_body_pose_from_joint(env, joint_name: str) -> dict | None:
    body_name = re.sub(r"_joint\d+$", "", joint_name)
    try:
        return body_pose(sim_from_env(env), body_name)
    except Exception:
        return None


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(json_safe(record)) + "\n")


def episode_dir_name(*, task_id: int, trial_id: int, seed: int, mode: str) -> str:
    return f"task{task_id}_initial_state{trial_id}_seed{seed}_{mode}"


def event_records(record: dict) -> list[dict]:
    events = [
        {
            "event": "episode_start",
            "task_id": record["task_id"],
            "initial_state_id": record["initial_state_id"],
            "seed": record["seed"],
            "mode": record["mode"],
            "manual_intervention": record["manual_intervention"],
        }
    ]
    disturbance = record.get("disturbance")
    if disturbance is not None:
        events.append(
            {
                "event": "disturbance_applied",
                "policy_step": record["pair_key"]["disturbance_step"],
                "target_joint": disturbance["joint"],
                "before_qpos": disturbance["before_qpos"],
                "after_qpos": disturbance["after_qpos"],
                "delta_xyz_actual": disturbance["delta_xyz_actual"],
                "refresh": disturbance.get("refresh"),
            }
        )
    for action in record["actions"]:
        events.append(
            {
                "event": "policy_step",
                "policy_step": action["t"],
                "video_frame_index": action["video_frame_index"],
                "reward": action["reward"],
                "done": action["done"],
                "uses_post_disturbance_fresh_observation": action[
                    "uses_post_disturbance_fresh_observation"
                ],
            }
        )
    events.append(
        {
            "event": "episode_end",
            "status": record["status"],
            "success": record["success"],
            "timeout": record["timeout"],
            "num_policy_steps": record["num_policy_steps"],
        }
    )
    return events


def write_episode_artifacts(record: dict, episode_dir: Path) -> dict:
    paths = {
        "episode_dir": str(episode_dir),
        "run_config": str(episode_dir / "run_config.json"),
        "events": str(episode_dir / "events.jsonl"),
        "episode_summary": str(episode_dir / "episode_summary.json"),
        "actions": str(episode_dir / "actions.jsonl"),
        "raw_video": str(episode_dir / "raw.mp4"),
    }
    run_config = {
        "checkpoint": record["checkpoint"],
        "task_suite": record["task_suite"],
        "task_id": record["task_id"],
        "initial_state_id": record["initial_state_id"],
        "seed": record["seed"],
        "seed_rule": record["seed_rule"],
        "mode": record["mode"],
        "target_joint": record["target_joint"],
        "disturbance_step": record["pair_key"]["disturbance_step"],
        "disturbance_delta_xyz": record["pair_key"]["disturbance_delta_xyz"],
        "warmup_env_steps": record["warmup_simulator_steps"],
        "max_policy_steps": record["policy_step_budget"],
        "manual_intervention": record["manual_intervention"],
        "disabled_modes": [
            "structured_recovery",
            "stage_backtrack",
            "verifier_stop",
            "full_reset",
            "oracle_rollback",
        ],
    }
    summary = {k: v for k, v in record.items() if k != "actions"}
    summary["artifact_paths"] = paths
    write_json(Path(paths["run_config"]), run_config)
    write_jsonl(Path(paths["events"]), event_records(record))
    write_json(Path(paths["episode_summary"]), summary)
    write_jsonl(Path(paths["actions"]), record["actions"])
    return paths


def canary_pair_key(
    *,
    checkpoint: str,
    task_suite_name: str,
    task_id: int,
    trial_id: int,
    seed: int,
    target_joint: str,
    disturbance_step: int,
    dx: float,
    dy: float,
    max_steps: int,
    num_steps_wait: int,
) -> dict:
    return {
        "checkpoint": checkpoint,
        "suite": task_suite_name,
        "task_id": int(task_id),
        "initial_state_id": int(trial_id),
        "seed": int(seed),
        "target_joint": target_joint,
        "disturbance_step": int(disturbance_step),
        "disturbance_delta_xyz": [float(dx), float(dy), 0.0],
        "max_policy_steps": int(max_steps),
        "warmup_env_steps": int(num_steps_wait),
    }


def rollout(
    *,
    cfg: SimpleNamespace,
    model,
    processor,
    task_suite,
    task_suite_name: str,
    task_id: int,
    trial_id: int,
    condition: str,
    checkpoint: str,
    seed: int,
    seed_rule: str,
    disturbance_step: int,
    target_joint: str,
    dx: float,
    dy: float,
    max_steps: int,
    num_steps_wait: int,
    out_dir: Path,
) -> dict:
    task = task_suite.get_task(task_id)
    initial_states = task_suite.get_task_init_states(task_id)
    if trial_id >= len(initial_states):
        raise ValueError(f"initial state {trial_id} is unavailable; only {len(initial_states)} states found")
    set_seed_everywhere(seed)
    env, task_description = get_libero_env(task, cfg.model_family, resolution=256)
    resize_size = get_image_resize_size(cfg)

    env.reset()
    obs = env.set_init_state(initial_states[trial_id])
    target_selection = select_target_joint(env, task_description, target_joint)
    resolved_target_joint = target_selection.selected_joint
    if resolved_target_joint is None:
        raise ValueError(f"target selection did not produce a joint: {target_selection.reason}")
    pair_key = canary_pair_key(
        checkpoint=checkpoint,
        task_suite_name=task_suite_name,
        task_id=task_id,
        trial_id=trial_id,
        seed=seed,
        target_joint=resolved_target_joint,
        disturbance_step=disturbance_step,
        dx=dx,
        dy=dy,
        max_steps=max_steps,
        num_steps_wait=num_steps_wait,
    )
    initial_robot_state = robot_state_from_obs(obs)
    initial_target_qpos = get_joint_qpos(env, resolved_target_joint)
    initial_target_body_pose = target_body_pose_from_joint(env, resolved_target_joint)
    policy_start_robot_state = None
    policy_start_target_qpos = None
    policy_start_target_body_pose = None

    replay_images: list[np.ndarray] = []
    action_trace = []
    disturbance_record = None
    done = False
    reward = 0.0
    info = {}
    extra_env_steps = 0

    for t in range(max_steps + num_steps_wait):
        if t < num_steps_wait:
            obs, reward, done, info = env.step(get_libero_dummy_action(cfg.model_family))
            continue

        policy_t = t - num_steps_wait
        if policy_t == 0:
            policy_start_robot_state = robot_state_from_obs(obs)
            policy_start_target_qpos = get_joint_qpos(env, resolved_target_joint)
            policy_start_target_body_pose = target_body_pose_from_joint(env, resolved_target_joint)
        if condition == "disturbed" and policy_t == disturbance_step:
            target_body_pose_before = target_body_pose_from_joint(env, resolved_target_joint)
            disturbance_record = audited_move_free_joint_xy(env, resolved_target_joint, dx, dy)
            disturbance_record["target_body_pose_before"] = target_body_pose_before
            disturbance_record["target_body_pose_after"] = target_body_pose_from_joint(env, resolved_target_joint)
            disturbance_record["delta_xyz_actual"] = [
                float(disturbance_record["after_qpos"][i] - disturbance_record["before_qpos"][i])
                for i in range(3)
            ]
            obs, refresh = refresh_observation_after_sim_change(env, cfg)
            disturbance_record["refresh"] = refresh
            extra_env_steps += int(bool(refresh.get("consumed_noop_env_step")))

        img = get_libero_image(obs, resize_size)
        replay_images.append(img)
        observation = {
            "full_image": img,
            "state": np.concatenate(
                (
                    obs["robot0_eef_pos"],
                    quat2axisangle(obs["robot0_eef_quat"]),
                    obs["robot0_gripper_qpos"],
                )
            ),
        }
        action = get_action(cfg, model, observation, task_description, processor=processor)
        raw_action = action.astype(float).tolist()
        action = normalize_gripper_action(action, binarize=True)
        if cfg.model_family == "openvla":
            action = invert_gripper_action(action)

        obs, reward, done, info = env.step(action.tolist())
        action_trace.append(
            {
                "t": int(policy_t),
                "raw_action": raw_action,
                "env_action": np.asarray(action, dtype=float).tolist(),
                "reward": float(reward),
                "done": bool(done),
                "video_frame_index": len(replay_images) - 1,
                "uses_post_disturbance_fresh_observation": bool(
                    condition == "disturbed" and policy_t == disturbance_step and disturbance_record is not None
                ),
            }
        )
        if done:
            break

    episode_status = extract_episode_status(reward, done, info, len(action_trace), max_steps)
    pre_steps = min(len(action_trace), disturbance_step) if disturbance_record else len(action_trace)
    budget = make_budget_report(
        policy_step_budget=max_steps,
        warmup_simulator_steps=num_steps_wait,
        policy_inference_steps=len(action_trace),
        extra_environment_steps=extra_env_steps,
        pre_disturbance_policy_steps=pre_steps,
        reset_count=0,
        rollback_count=0,
        success=episode_status.success,
    )

    mode = "reactive_disturbed" if condition == "disturbed" else "clean"
    episode_dir = out_dir / episode_dir_name(task_id=task_id, trial_id=trial_id, seed=seed, mode=mode)
    video_path = episode_dir / "raw.mp4"
    save_video(replay_images, video_path)
    env.close()

    record = {
        "condition": condition,
        "mode": mode,
        "pair_key": pair_key,
        "manual_intervention": False,
        "checkpoint": checkpoint,
        "seed": int(seed),
        "seed_rule": seed_rule,
        "task_suite": task_suite_name,
        "unnorm_key": cfg.unnorm_key,
        "task_id": task_id,
        "trial_id": trial_id,
        "initial_state_id": trial_id,
        "task_description": task_description,
        "target_joint": resolved_target_joint,
        "target_selection": json_safe(target_selection),
        "initial_robot_state": initial_robot_state,
        "initial_target_qpos": initial_target_qpos,
        "initial_target_body_pose": initial_target_body_pose,
        "policy_start_robot_state": policy_start_robot_state,
        "policy_start_target_qpos": policy_start_target_qpos,
        "policy_start_target_body_pose": policy_start_target_body_pose,
        "status": episode_status.status,
        "episode_status": json_safe(episode_status),
        "success": episode_status.success,
        "timeout": episode_status.timeout,
        "stopped": episode_status.stopped,
        "simulator_error": episode_status.simulator_error,
        "success_source": episode_status.source if episode_status.success else None,
        "final_reward": float(reward),
        "num_policy_steps": len(action_trace),
        "policy_step_budget": budget.policy_step_budget,
        "warmup_simulator_steps": budget.warmup_simulator_steps,
        "policy_inference_steps": budget.policy_inference_steps,
        "environment_control_steps": budget.environment_control_steps,
        "pre_disturbance_policy_steps": budget.pre_disturbance_policy_steps,
        "recovery_policy_steps": budget.recovery_policy_steps,
        "success_within_original_budget": budget.success_within_original_budget,
        "total_policy_steps_consumed": budget.total_policy_steps_consumed,
        "reset_count": budget.reset_count,
        "rollback_count": budget.rollback_count,
        "budget": json_safe(budget),
        "disturbance": disturbance_record,
        "video_path": str(video_path),
        "actions": action_trace,
    }
    record["artifact_paths"] = write_episode_artifacts(record, episode_dir)
    return record


def main() -> None:
    args = parse_args()
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    set_seed_everywhere(args.seed)

    out_dir = Path(args.out_dir) / time.strftime("%Y_%m_%d-%H_%M_%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = make_cfg(args)
    model = get_model(cfg)
    if cfg.unnorm_key not in model.norm_stats and f"{cfg.unnorm_key}_no_noops" in model.norm_stats:
        cfg.unnorm_key = f"{cfg.unnorm_key}_no_noops"
    if cfg.unnorm_key not in model.norm_stats:
        raise ValueError(f"missing unnorm key {cfg.unnorm_key}; available={list(model.norm_stats.keys())}")
    processor = get_processor(cfg)

    task_suite = benchmark.get_benchmark_dict()[args.task_suite]()

    records = []
    task_ids = range(task_suite.n_tasks) if args.task_id < 0 else [args.task_id]
    jsonl_path = out_dir / "episodes.jsonl"
    for trial_id in range(args.trials):
        episode_seed = args.seed + trial_id if args.seed_rule == "base_plus_initial_state" else args.seed
        for task_id in task_ids:
            for condition in ["clean", "disturbed"]:
                record = rollout(
                    cfg=cfg,
                    model=model,
                    processor=processor,
                    task_suite=task_suite,
                    task_suite_name=args.task_suite,
                    task_id=task_id,
                    trial_id=trial_id,
                    condition=condition,
                    checkpoint=args.checkpoint,
                    seed=episode_seed,
                    seed_rule=args.seed_rule,
                    disturbance_step=args.disturbance_step,
                    target_joint=args.target_joint,
                    dx=args.dx,
                    dy=args.dy,
                    max_steps=args.max_steps,
                    num_steps_wait=args.num_steps_wait,
                    out_dir=out_dir,
                )
                records.append(record)
                with jsonl_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")
                print(
                    record["condition"],
                    "task=", record["task_id"],
                    "target=", record["target_joint"],
                    "success=", record["success"],
                    "steps=", record["num_policy_steps"],
                    "video=", record["video_path"],
                    flush=True,
                )

    summary = {
        "checkpoint": args.checkpoint,
        "args": vars(args),
        "records": records,
        "clean_success_rate": float(np.mean([r["success"] for r in records if r["condition"] == "clean"])),
        "disturbed_success_rate": float(np.mean([r["success"] for r in records if r["condition"] == "disturbed"])),
        "jsonl_path": str(jsonl_path),
    }
    task_ids_done = sorted({r["task_id"] for r in records})
    per_task = {}
    for task_id in task_ids_done:
        per_task[str(task_id)] = {}
        for condition in ["clean", "disturbed"]:
            xs = [r["success"] for r in records if r["task_id"] == task_id and r["condition"] == condition]
            per_task[str(task_id)][condition] = {
                "n": len(xs),
                "successes": int(sum(xs)),
                "success_rate": float(np.mean(xs)) if xs else None,
            }
    summary["per_task"] = per_task
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "records"}, indent=2))
    print("summary", summary_path)


if __name__ == "__main__":
    main()
