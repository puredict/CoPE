from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import imageio.v2 as imageio
import numpy as np

sys.path.insert(0, "/home/lijingsu/vla/src/openvla")
sys.path.insert(0, "/home/lijingsu/vla/src/LIBERO")
os.environ.setdefault("MUJOCO_GL", "osmesa")
os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")

from libero_experiment_core import (
    ExperimentConfig,
    create_libero_env,
    frame_from_obs,
    get_benchmark_suite,
    get_dummy_action,
    get_joint_qpos,
    json_safe,
    move_free_joint_xy,
    refresh_observation_after_sim_change,
    select_target_joint,
    validate_task_and_trial,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-suite", default="libero_spatial")
    parser.add_argument("--task-id", type=int, default=0)
    parser.add_argument("--trial-id", type=int, default=0)
    parser.add_argument("--target-joint", default="akita_black_bowl_1_joint0")
    parser.add_argument("--dx", type=float, default=0.20)
    parser.add_argument("--dy", type=float, default=0.00)
    parser.add_argument("--resolution", type=int, default=128)
    parser.add_argument("--out-dir", default="/home/lijingsu/vla/audit_outputs/correctness_gate_refresh")
    return parser.parse_args()


def image_delta(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    delta = np.abs(a.astype(np.int16) - b.astype(np.int16))
    return {
        "mean_abs": float(delta.mean()),
        "max_abs": float(delta.max()),
        "changed_pixels": int(np.count_nonzero(delta)),
    }


def main() -> None:
    args = parse_args()
    run_dir = Path(args.out_dir) / time.strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    cfg = ExperimentConfig(
        checkpoint="not_loaded",
        task_suite=args.task_suite,
        task_id=args.task_id,
        trial_id=args.trial_id,
        target_joint=args.target_joint,
        resolution=args.resolution,
    )
    suite = get_benchmark_suite(args.task_suite)
    initial_states = validate_task_and_trial(suite, cfg)
    task = suite.get_task(args.task_id)
    env, task_description = create_libero_env(task, cfg)
    try:
        env.reset()
        obs = env.set_init_state(initial_states[args.trial_id])

        step_result = env.step(get_dummy_action("openvla"))
        step_return_len = len(step_result)
        obs, reward, done, info = step_result

        selection = select_target_joint(env, task_description, args.target_joint)
        target_joint = selection.selected_joint
        if target_joint is None:
            raise ValueError(f"target selection did not produce a joint: {selection.reason}")

        before_qpos = get_joint_qpos(env, target_joint)
        before_img = frame_from_obs(obs, (args.resolution, args.resolution))

        disturbance = move_free_joint_xy(env, target_joint, args.dx, args.dy)
        stale_img = frame_from_obs(obs, (args.resolution, args.resolution))
        after_qpos = get_joint_qpos(env, target_joint)

        fresh_obs, refresh = refresh_observation_after_sim_change(env, cfg)
        fresh_img = frame_from_obs(fresh_obs, (args.resolution, args.resolution))
        fresh_qpos = get_joint_qpos(env, target_joint)

        imageio.imwrite(run_dir / "before.png", before_img)
        imageio.imwrite(run_dir / "stale_from_old_obs.png", stale_img)
        imageio.imwrite(run_dir / "fresh_after_refresh.png", fresh_img)

        stale_delta = image_delta(before_img, stale_img)
        fresh_delta = image_delta(before_img, fresh_img)
        qpos_delta = [
            float(fresh_qpos[0] - before_qpos[0]),
            float(fresh_qpos[1] - before_qpos[1]),
        ]
        qpos_reflects_mutation = np.allclose(qpos_delta, [args.dx, args.dy], atol=1e-7)
        old_obs_is_stale = stale_delta["changed_pixels"] == 0
        fresh_obs_is_new = bool(qpos_reflects_mutation or fresh_delta["changed_pixels"] > 0)
        passed = bool(step_return_len == 4 and old_obs_is_stale and fresh_obs_is_new)

        payload = {
            "passed": passed,
            "task_suite": args.task_suite,
            "task_id": args.task_id,
            "trial_id": args.trial_id,
            "task_description": task_description,
            "target_joint": target_joint,
            "target_selection": json_safe(selection),
            "step_return_len": step_return_len,
            "step_reward": float(reward),
            "step_done": bool(done),
            "step_info_keys": sorted((info or {}).keys()),
            "before_qpos": before_qpos,
            "after_qpos": after_qpos,
            "fresh_qpos": fresh_qpos,
            "qpos_delta_xy": qpos_delta,
            "qpos_reflects_mutation": bool(qpos_reflects_mutation),
            "old_obs_reused_pixel_delta": stale_delta,
            "fresh_obs_pixel_delta": fresh_delta,
            "old_obs_is_stale": old_obs_is_stale,
            "fresh_obs_is_new": fresh_obs_is_new,
            "refresh": json_safe(refresh),
            "disturbance": json_safe(disturbance),
            "images": {
                "before": str(run_dir / "before.png"),
                "stale_from_old_obs": str(run_dir / "stale_from_old_obs.png"),
                "fresh_after_refresh": str(run_dir / "fresh_after_refresh.png"),
            },
        }
        (run_dir / "observation_refresh_diagnostic.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        raise SystemExit(0 if passed else 1)
    finally:
        env.close()


if __name__ == "__main__":
    main()
