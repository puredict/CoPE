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
    sim = sim_from_env(env)
    task_tokens = tokenize(task_description)
    candidates = []
    for joint_id in range(sim.model.njnt):
        name = sim.model.joint_id2name(joint_id)
        if not name or name.startswith("robot") or name.startswith("gripper"):
            continue
        if int(sim.model.jnt_type[joint_id]) != 0:
            continue
        object_name = name.replace("_joint0", "")
        object_tokens = tokenize(object_name)
        score = len(task_tokens & object_tokens)
        qpos_addr = int(sim.model.jnt_qposadr[joint_id])
        candidates.append((score, -joint_id, name, qpos_addr))
    if not candidates:
        raise ValueError("No movable free-joint object found for disturbance.")
    candidates.sort(reverse=True)
    return candidates[0][2]


def save_video(images: list[np.ndarray], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio.get_writer(path, fps=30)
    for image in images:
        writer.append_data(image)
    writer.close()


def rollout(
    *,
    cfg: SimpleNamespace,
    model,
    processor,
    task_suite,
    task_id: int,
    trial_id: int,
    condition: str,
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
    env, task_description = get_libero_env(task, cfg.model_family, resolution=256)
    resize_size = get_image_resize_size(cfg)

    env.reset()
    obs = env.set_init_state(initial_states[trial_id])
    resolved_target_joint = choose_target_joint(env, task_description) if target_joint == "auto" else target_joint

    replay_images: list[np.ndarray] = []
    action_trace = []
    disturbance_record = None
    done = False
    reward = 0.0

    for t in range(max_steps + num_steps_wait):
        if t < num_steps_wait:
            obs, reward, done, info = env.step(get_libero_dummy_action(cfg.model_family))
            continue

        policy_t = t - num_steps_wait
        if condition == "disturbed" and policy_t == disturbance_step:
            disturbance_record = move_free_joint_xy(env, resolved_target_joint, dx, dy)

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
            }
        )
        if done:
            break

    video_path = out_dir / f"{condition}_task{task_id}_trial{trial_id}_success{bool(done)}.mp4"
    save_video(replay_images, video_path)
    env.close()

    return {
        "condition": condition,
        "task_suite": cfg.unnorm_key,
        "task_id": task_id,
        "trial_id": trial_id,
        "task_description": task_description,
        "target_joint": resolved_target_joint,
        "success": bool(done),
        "final_reward": float(reward),
        "num_policy_steps": len(action_trace),
        "disturbance": disturbance_record,
        "video_path": str(video_path),
        "actions": action_trace,
    }


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
        for task_id in task_ids:
            for condition in ["clean", "disturbed"]:
                record = rollout(
                    cfg=cfg,
                    model=model,
                    processor=processor,
                    task_suite=task_suite,
                    task_id=task_id,
                    trial_id=trial_id,
                    condition=condition,
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
