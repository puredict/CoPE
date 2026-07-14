from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from libero_experiment_core import (
    ExperimentConfig,
    build_recovery_prompt,
    canonicalize_mode,
    draw_overlay,
    execute_policy_step,
    extract_episode_status,
    get_benchmark_suite,
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
    sim_from_env,
    unload_torch_model_refs,
)


CANARY_MODES: tuple[str, ...] = (
    "reactive_disturbed",
    "structured_relocalize_prompt",
    "stage_backtrack_subgoal",
)

FORBIDDEN_MODES: tuple[str, ...] = (
    "clean",
    "verifier_stop",
    "full_reset_replan",
    "oracle_rollback",
)

PAIR_FIELDS: tuple[str, ...] = (
    "checkpoint",
    "task_suite",
    "task_id",
    "initial_state_id",
    "seed",
    "initial_state_digest",
    "target_joint",
    "disturbance_step",
    "disturbance_delta_xyz",
    "max_policy_steps",
    "warmup_env_steps",
    "camera_resolution",
    "model_family",
    "resolved_unnorm_key",
    "action_normalization",
)


@dataclass(frozen=True)
class RecoveryCanaryConfig:
    checkpoint: str = "/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial"
    task_suite: str = "libero_spatial"
    task_id: int = 0
    initial_state_id: int = 0
    seed: int = 7
    target_joint: str = "akita_black_bowl_1_joint0"
    disturbance_step: int = 70
    dx: float = 0.10
    dy: float = 0.05
    max_steps: int = 220
    num_steps_wait: int = 10
    resolution: int = 256
    out_dir: str = "/home/lijingsu/vla/recovery_canary_outputs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the fixed single-condition recovery method canary.")
    parser.add_argument("--out-dir", default=RecoveryCanaryConfig.out_dir)
    return parser.parse_args()


def ensure_fixed_runtime() -> None:
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if visible != "0":
        raise RuntimeError(f"CUDA_VISIBLE_DEVICES must be exactly '0' for this canary, got {visible!r}")


def state_digest(value: Any) -> str:
    arr = np.asarray(value, dtype=np.float64)
    return hashlib.sha256(arr.tobytes()).hexdigest()


def body_pose_from_joint(env: Any, joint_name: str) -> dict[str, Any] | None:
    body_name = joint_name.rsplit("_joint", 1)[0]
    try:
        sim = sim_from_env(env)
        body_id = int(sim.model.body_name2id(body_name))
        return {
            "body": body_name,
            "xyz": np.asarray(sim.data.body_xpos[body_id], dtype=float).tolist(),
        }
    except Exception as exc:
        return {"body": body_name, "error": f"{type(exc).__name__}: {exc}"}


def target_position(env: Any, joint_name: str) -> dict[str, Any]:
    return {
        "joint": joint_name,
        "qpos": get_joint_qpos(env, joint_name),
        "body_pose": body_pose_from_joint(env, joint_name),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(json_safe(record), sort_keys=True, ensure_ascii=True) + "\n")


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(json_safe(record), sort_keys=True, ensure_ascii=True) + "\n")


def save_video(frames: list[np.ndarray], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import imageio.v2 as imageio

    writer = imageio.get_writer(path, fps=30)
    try:
        for frame in frames:
            writer.append_data(np.asarray(frame, dtype=np.uint8))
    finally:
        writer.close()


def episode_dir_name(mode: str, cfg: RecoveryCanaryConfig) -> str:
    return f"task{cfg.task_id}_initial_state{cfg.initial_state_id}_seed{cfg.seed}_{mode}"


def make_pair_key(
    *,
    cfg: RecoveryCanaryConfig,
    resolved_target_joint: str,
    initial_state_digest: str,
    resolved_unnorm_key: str,
) -> dict[str, Any]:
    return {
        "checkpoint": cfg.checkpoint,
        "task_suite": cfg.task_suite,
        "task_id": cfg.task_id,
        "initial_state_id": cfg.initial_state_id,
        "seed": cfg.seed,
        "initial_state_digest": initial_state_digest,
        "target_joint": resolved_target_joint,
        "disturbance_step": cfg.disturbance_step,
        "disturbance_delta_xyz": [float(cfg.dx), float(cfg.dy), 0.0],
        "max_policy_steps": cfg.max_steps,
        "warmup_env_steps": cfg.num_steps_wait,
        "camera_resolution": cfg.resolution,
        "model_family": "openvla",
        "resolved_unnorm_key": resolved_unnorm_key,
        "action_normalization": {
            "normalize_gripper_action": True,
            "binarize_gripper": True,
            "invert_openvla_gripper": True,
        },
    }


def recovery_decision_for_mode(
    *,
    mode: str,
    original_prompt: str,
    current_prompt: str,
    target_joint: str,
) -> dict[str, Any]:
    if mode == "reactive_disturbed":
        return {
            "type": "reactive_disturbed",
            "decision": "continue_original_prompt_after_disturbance",
            "original_prompt": original_prompt,
            "prompt_switch_step": None,
            "new_prompt": current_prompt,
            "affected_joint": target_joint,
            "affected_object": None,
            "invalidated_state_or_subgoal": [],
            "requested_recovery_stage": None,
            "actual_recovery_action_prompt_only": False,
            "reset_count": 0,
            "rollback_count": 0,
        }

    new_prompt, state = build_recovery_prompt(mode, original_prompt, target_joint)
    state = dict(state or {})
    invalidated = state.get("invalid_state") or [state.get("progress_preserved", "current_subgoal")]
    return {
        "type": mode,
        "decision": state.get("decision", mode),
        "original_prompt": original_prompt,
        "prompt_switch_step": None,
        "new_prompt": new_prompt,
        "affected_joint": target_joint,
        "affected_object": state.get("affected_object"),
        "invalidated_state_or_subgoal": invalidated,
        "requested_recovery_stage": state.get("goal") or state.get("decision") or mode,
        "actual_recovery_action_prompt_only": True,
        "reset_count": 0,
        "rollback_count": 0,
        "builder_state": state,
    }


def event_base(
    *,
    event: str,
    mode: str,
    policy_step: int,
    environment_step: int,
    reward: float,
    done: bool,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "mode": mode,
        "policy_step": int(policy_step),
        "environment_step": int(environment_step),
        "reward": float(reward),
        "done": bool(done),
        "manual_intervention": False,
        "payload": json_safe(payload or {}),
    }


def run_episode(
    *,
    mode: str,
    cfg: RecoveryCanaryConfig,
    model: Any,
    processor: Any,
    model_cfg: Any,
    resolved_unnorm_key: str,
    task_suite: Any,
    run_root: Path,
) -> dict[str, Any]:
    mode = canonicalize_mode(mode)
    if mode not in CANARY_MODES:
        raise ValueError(f"mode {mode!r} is not allowed in this canary")

    task = task_suite.get_task(cfg.task_id)
    initial_states = list(task_suite.get_task_init_states(cfg.task_id))
    if cfg.initial_state_id >= len(initial_states):
        raise ValueError(f"initial state {cfg.initial_state_id} unavailable; found {len(initial_states)}")

    set_seed(cfg.seed)
    from libero_experiment_core import create_libero_env

    env, task_description = create_libero_env(task, ExperimentConfig(checkpoint=cfg.checkpoint, resolution=cfg.resolution))
    resize_size = get_image_resize_size(model_cfg)
    episode_dir = run_root / episode_dir_name(mode, cfg)
    events_path = episode_dir / "events.jsonl"
    actions_path = episode_dir / "actions.jsonl"
    run_config_path = episode_dir / "run_config.json"
    summary_path = episode_dir / "episode_summary.json"
    raw_video_path = episode_dir / "raw.mp4"
    annotated_video_path = episode_dir / "annotated.mp4"
    raw_frames: list[np.ndarray] = []
    annotated_frames: list[np.ndarray] = []
    actions: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    reward = 0.0
    done = False
    info: dict[str, Any] = {}
    environment_step = 0
    disturbance_record: dict[str, Any] | None = None
    prompt_switch_event: dict[str, Any] | None = None
    current_prompt = task_description
    original_prompt = task_description
    recovery_decision = recovery_decision_for_mode(
        mode=mode,
        original_prompt=original_prompt,
        current_prompt=current_prompt,
        target_joint=cfg.target_joint,
    )
    extra_env_steps = 0

    try:
        env.reset()
        obs = env.set_init_state(initial_states[cfg.initial_state_id])
        initial_digest = state_digest(initial_states[cfg.initial_state_id])
        target_selection = select_target_joint(env, task_description, cfg.target_joint)
        resolved_target_joint = target_selection.selected_joint
        if resolved_target_joint is None:
            raise ValueError(f"target selection did not produce a joint: {target_selection.reason}")
        recovery_decision = recovery_decision_for_mode(
            mode=mode,
            original_prompt=original_prompt,
            current_prompt=current_prompt,
            target_joint=resolved_target_joint,
        )
        pair_key = make_pair_key(
            cfg=cfg,
            resolved_target_joint=resolved_target_joint,
            initial_state_digest=initial_digest,
            resolved_unnorm_key=resolved_unnorm_key,
        )
        initial_target_position = target_position(env, resolved_target_joint)
        events.append(
            event_base(
                event="episode_start",
                mode=mode,
                policy_step=0,
                environment_step=0,
                reward=0.0,
                done=False,
                payload={
                    "task_description": task_description,
                    "pair_key": pair_key,
                    "target_selection": target_selection,
                },
            )
        )

        for _ in range(cfg.num_steps_wait):
            obs, reward, done, info = env.step(get_dummy_action("openvla"))
            environment_step += 1
        policy_start_target_position = target_position(env, resolved_target_joint)
        events.append(
            event_base(
                event="warmup_complete",
                mode=mode,
                policy_step=0,
                environment_step=environment_step,
                reward=reward,
                done=done,
                payload={"warmup_env_steps": cfg.num_steps_wait},
            )
        )

        for policy_step in range(cfg.max_steps):
            disturbance_applied = False
            fresh_observation = False
            observation_refresh_method: str | None = None
            refresh_payload: dict[str, Any] | None = None

            if policy_step == cfg.disturbance_step:
                before_position = target_position(env, resolved_target_joint)
                disturbance_record = move_free_joint_xy(env, resolved_target_joint, cfg.dx, cfg.dy)
                after_position = target_position(env, resolved_target_joint)
                disturbance_record.update(
                    {
                        "target_position_before": before_position,
                        "target_position_after": after_position,
                        "delta_xyz_actual": [
                            float(disturbance_record["after_qpos"][i] - disturbance_record["before_qpos"][i])
                            for i in range(3)
                        ],
                    }
                )
                obs, refresh_payload = refresh_observation_after_sim_change(env, model_cfg)
                observation_refresh_method = str(refresh_payload.get("method"))
                disturbance_record["refresh"] = refresh_payload
                extra_env_steps += int(bool(refresh_payload.get("consumed_noop_env_step")))
                environment_step += int(bool(refresh_payload.get("consumed_noop_env_step")))
                disturbance_applied = True
                fresh_observation = True
                events.append(
                    event_base(
                        event="disturbance_applied",
                        mode=mode,
                        policy_step=policy_step,
                        environment_step=environment_step,
                        reward=reward,
                        done=done,
                        payload=disturbance_record,
                    )
                )
                if mode != "reactive_disturbed":
                    new_prompt = str(recovery_decision["new_prompt"])
                    prompt_switch_event = {
                        "original_prompt": original_prompt,
                        "prompt_switch_step": policy_step,
                        "new_prompt": new_prompt,
                        "affected_joint": resolved_target_joint,
                        "affected_object": recovery_decision.get("affected_object"),
                        "invalidated_state_or_subgoal": recovery_decision.get("invalidated_state_or_subgoal"),
                        "requested_recovery_stage": recovery_decision.get("requested_recovery_stage"),
                        "actual_recovery_action_prompt_only": True,
                    }
                    current_prompt = new_prompt
                    recovery_decision = dict(recovery_decision)
                    recovery_decision["prompt_switch_step"] = policy_step
                    events.append(
                        event_base(
                            event="recovery_prompt_switched",
                            mode=mode,
                            policy_step=policy_step,
                            environment_step=environment_step,
                            reward=reward,
                            done=done,
                            payload=prompt_switch_event,
                        )
                    )

            step_result = execute_policy_step(
                cfg=model_cfg,
                model=model,
                processor=processor,
                env=env,
                obs=obs,
                prompt=current_prompt,
                resize_size=resize_size,
            )
            environment_step += 1
            obs = step_result.next_obs
            reward = step_result.reward
            done = step_result.done
            info = dict(step_result.info)
            step_status = "running"
            if done or policy_step + 1 >= cfg.max_steps:
                step_status = extract_episode_status(reward, done, info, policy_step + 1, cfg.max_steps).status

            action_record = {
                "policy_step": policy_step,
                "environment_step": environment_step,
                "prompt": current_prompt,
                "original_prompt": original_prompt,
                "action": step_result.env_action,
                "raw_action": step_result.raw_action,
                "env_action": step_result.env_action,
                "reward": reward,
                "done": done,
                "episode_status": step_status,
                "target_position": target_position(env, resolved_target_joint),
                "disturbance_applied": disturbance_applied,
                "fresh_observation": fresh_observation,
                "observation_refresh_method": observation_refresh_method,
                "observation_refresh": refresh_payload,
                "policy_budget_remaining": max(0, cfg.max_steps - policy_step - 1),
                "recovery_mode": mode,
                "recovery_decision": recovery_decision,
                "manual_intervention": False,
                "inference_seconds": step_result.inference_seconds,
                "env_step_seconds": step_result.env_step_seconds,
                "video_frame_index": len(raw_frames),
            }
            actions.append(action_record)
            append_jsonl(actions_path, action_record)
            raw_frames.append(step_result.raw_frame)
            annotated_frames.append(
                draw_overlay(
                    step_result.raw_frame,
                    {
                        "mode": mode,
                        "task_id": cfg.task_id,
                        "trial_id": cfg.initial_state_id,
                        "state": step_status,
                        "policy_step": policy_step,
                        "reward": reward,
                        "target_joint": resolved_target_joint,
                        "recovery_prompt": mode != "reactive_disturbed" and policy_step >= cfg.disturbance_step,
                    },
                )
            )
            events.append(
                event_base(
                    event="policy_step",
                    mode=mode,
                    policy_step=policy_step,
                    environment_step=environment_step,
                    reward=reward,
                    done=done,
                    payload={
                        "prompt": current_prompt,
                        "fresh_observation": fresh_observation,
                        "observation_refresh_method": observation_refresh_method,
                        "policy_budget_remaining": action_record["policy_budget_remaining"],
                        "episode_status": step_status,
                    },
                )
            )
            if done:
                break

        episode_status = extract_episode_status(reward, done, info, len(actions), cfg.max_steps)
        pre_steps = min(len(actions), cfg.disturbance_step) if disturbance_record else len(actions)
        budget = make_budget_report(
            policy_step_budget=cfg.max_steps,
            warmup_simulator_steps=cfg.num_steps_wait,
            policy_inference_steps=len(actions),
            extra_environment_steps=extra_env_steps,
            pre_disturbance_policy_steps=pre_steps,
            reset_count=0,
            rollback_count=0,
            success=episode_status.success,
        )
        video_status = {"raw_video_path": str(raw_video_path), "annotated_video_path": str(annotated_video_path)}
        save_video(raw_frames, raw_video_path)
        save_video(annotated_frames, annotated_video_path)

        summary = {
            "mode": mode,
            "pair_key": pair_key,
            "checkpoint": cfg.checkpoint,
            "task_suite": cfg.task_suite,
            "task_id": cfg.task_id,
            "initial_state_id": cfg.initial_state_id,
            "seed": cfg.seed,
            "manual_intervention": False,
            "task_description": task_description,
            "original_prompt": original_prompt,
            "final_prompt": current_prompt,
            "target_joint": resolved_target_joint,
            "target_selection": target_selection,
            "initial_target_position": initial_target_position,
            "policy_start_target_position": policy_start_target_position,
            "disturbance": disturbance_record,
            "recovery_decision": recovery_decision,
            "prompt_switch_event": prompt_switch_event,
            "status": episode_status.status,
            "success": episode_status.success,
            "timeout": episode_status.timeout,
            "stopped": episode_status.stopped,
            "simulator_error": episode_status.simulator_error,
            "episode_status": episode_status,
            "final_reward": reward,
            "num_policy_steps": len(actions),
            "policy_step_budget": cfg.max_steps,
            "warmup_simulator_steps": cfg.num_steps_wait,
            "policy_inference_steps": len(actions),
            "environment_control_steps": budget.environment_control_steps,
            "pre_disturbance_policy_steps": budget.pre_disturbance_policy_steps,
            "recovery_policy_steps": budget.recovery_policy_steps,
            "total_policy_steps_consumed": budget.total_policy_steps_consumed,
            "reset_count": 0,
            "rollback_count": 0,
            "success_within_original_budget": budget.success_within_original_budget,
            "budget": budget,
            "actions": actions,
            "events": events,
            "video_status": video_status,
            "artifact_paths": {
                "episode_dir": str(episode_dir),
                "run_config": str(run_config_path),
                "events": str(events_path),
                "actions": str(actions_path),
                "episode_summary": str(summary_path),
                "raw_video": str(raw_video_path),
                "annotated_video": str(annotated_video_path),
            },
        }
        run_config = {
            **asdict(cfg),
            "mode": mode,
            "resolved_target_joint": resolved_target_joint,
            "resolved_unnorm_key": resolved_unnorm_key,
            "pair_key": pair_key,
            "allowed_modes": CANARY_MODES,
            "disabled_modes": FORBIDDEN_MODES,
            "manual_intervention": False,
        }
        write_json(run_config_path, run_config)
        write_jsonl(events_path, events)
        write_json(summary_path, summary)
        return json_safe(summary)
    finally:
        try:
            env.close()
        except Exception:
            pass


def close_enough(xs: list[float], ys: list[float], tol: float = 1e-5) -> bool:
    return len(xs) == len(ys) and all(abs(float(x) - float(y)) <= tol for x, y in zip(xs, ys))


def video_frame_count(path: str) -> int | None:
    try:
        import imageio.v2 as imageio

        reader = imageio.get_reader(path)
        try:
            return int(reader.count_frames())
        finally:
            reader.close()
    except Exception:
        return None


def validate_records(records: list[dict[str, Any]], *, check_videos: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    modes = [record.get("mode") for record in records]
    if modes != list(CANARY_MODES):
        errors.append(f"expected modes {list(CANARY_MODES)}, got {modes}")
    if any(mode in FORBIDDEN_MODES for mode in modes):
        errors.append(f"forbidden mode present: {modes}")

    pair_keys = [record.get("pair_key") for record in records]
    if pair_keys:
        canonical = json.dumps(pair_keys[0], sort_keys=True)
        for index, pair_key in enumerate(pair_keys[1:], start=1):
            if json.dumps(pair_key, sort_keys=True) != canonical:
                errors.append(f"pair_key mismatch at record {index}")

    budgets = [(record.get("policy_step_budget"), record.get("warmup_simulator_steps")) for record in records]
    if len(set(json.dumps(budget) for budget in budgets)) > 1:
        errors.append(f"budget mismatch across modes: {budgets}")

    for record in records:
        mode = str(record.get("mode"))
        actions = list(record.get("actions") or [])
        disturbance = record.get("disturbance") or {}
        pair_key = record.get("pair_key") or {}
        disturbance_step = int(pair_key.get("disturbance_step", -1))
        expected_delta = list(pair_key.get("disturbance_delta_xyz") or [])
        actual_delta = list(disturbance.get("delta_xyz_actual") or [])
        if not close_enough(actual_delta, expected_delta, tol=1e-4):
            errors.append(f"{mode}: disturbance delta {actual_delta} != {expected_delta}")

        step_actions = [action for action in actions if int(action.get("policy_step", -1)) == disturbance_step]
        if len(step_actions) != 1:
            errors.append(f"{mode}: missing unique action at disturbance step {disturbance_step}")
            step_action = None
        else:
            step_action = step_actions[0]
            if step_action.get("fresh_observation") is not True:
                errors.append(f"{mode}: disturbance-step action did not use fresh observation")
            if not step_action.get("observation_refresh_method"):
                errors.append(f"{mode}: missing observation refresh method at disturbance step")
            if int(step_action.get("policy_budget_remaining", -1)) != int(pair_key.get("max_policy_steps", 0)) - disturbance_step - 1:
                errors.append(f"{mode}: policy budget remaining is not auditable at disturbance step")

        refresh = disturbance.get("refresh") or {}
        if refresh.get("consumed_noop_env_step") is not False:
            errors.append(f"{mode}: observation refresh consumed an extra env noop step")

        if record.get("timeout") and record.get("success"):
            errors.append(f"{mode}: timeout recorded as success")
        if record.get("manual_intervention") is not False:
            errors.append(f"{mode}: manual intervention was recorded")

        prompt_switch = record.get("prompt_switch_event")
        if mode == "reactive_disturbed":
            if prompt_switch is not None:
                errors.append("reactive_disturbed: unexpected prompt switch event")
        else:
            if not prompt_switch:
                errors.append(f"{mode}: missing prompt switch event")
            else:
                if int(prompt_switch.get("prompt_switch_step", -1)) != disturbance_step:
                    errors.append(f"{mode}: prompt switch step not aligned with disturbance")
                if prompt_switch.get("actual_recovery_action_prompt_only") is not True:
                    errors.append(f"{mode}: recovery action was not marked prompt-only")
            if step_action and step_action.get("prompt") == record.get("original_prompt"):
                errors.append(f"{mode}: disturbance-step prompt did not switch")

        if int(record.get("num_policy_steps", -1)) != len(actions):
            errors.append(f"{mode}: num_policy_steps does not match action records")

        if check_videos:
            paths = record.get("artifact_paths") or {}
            for label in ("raw_video", "annotated_video"):
                path = paths.get(label)
                count = video_frame_count(path) if path else None
                if count is None:
                    warnings.append(f"{mode}: could not count frames for {label}")
                elif count != len(actions):
                    errors.append(f"{mode}: {label} frames {count} != actions {len(actions)}")

    return {"passed": not errors, "errors": errors, "warnings": warnings}


def write_run_summary(run_root: Path, cfg: RecoveryCanaryConfig, records: list[dict[str, Any]], validation: dict[str, Any]) -> Path:
    summary = {
        "config": asdict(cfg),
        "allowed_modes": CANARY_MODES,
        "forbidden_modes": FORBIDDEN_MODES,
        "records": records,
        "validation": validation,
    }
    summary_path = run_root / "summary.json"
    write_json(summary_path, summary)
    return summary_path


def main() -> None:
    args = parse_args()
    ensure_fixed_runtime()
    cfg = RecoveryCanaryConfig(out_dir=args.out_dir)
    run_root = Path(cfg.out_dir) / time.strftime("%Y_%m_%d-%H_%M_%S")
    run_root.mkdir(parents=True, exist_ok=True)

    model_cfg = ExperimentConfig(
        checkpoint=cfg.checkpoint,
        task_suite=cfg.task_suite,
        task_id=cfg.task_id,
        trial_id=cfg.initial_state_id,
        mode="reactive_disturbed",
        max_steps=cfg.max_steps,
        num_steps_wait=cfg.num_steps_wait,
        disturbance_step=cfg.disturbance_step,
        target_joint=cfg.target_joint,
        dx=cfg.dx,
        dy=cfg.dy,
        seed=cfg.seed,
        resolution=cfg.resolution,
        out_dir=str(run_root),
    )
    set_seed(cfg.seed)
    model = None
    records: list[dict[str, Any]] = []
    try:
        model, processor, loaded_model_cfg, resolved_unnorm_key = load_model_and_processor(model_cfg)
        task_suite = get_benchmark_suite(cfg.task_suite)
        for mode in CANARY_MODES:
            record = run_episode(
                mode=mode,
                cfg=cfg,
                model=model,
                processor=processor,
                model_cfg=loaded_model_cfg,
                resolved_unnorm_key=resolved_unnorm_key,
                task_suite=task_suite,
                run_root=run_root,
            )
            records.append(record)
            print(
                json.dumps(
                    {
                        "mode": record["mode"],
                        "status": record["status"],
                        "success": record["success"],
                        "steps": record["num_policy_steps"],
                        "episode_dir": record["artifact_paths"]["episode_dir"],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        validation = validate_records(records, check_videos=True)
        summary_path = write_run_summary(run_root, cfg, records, validation)
        print(json.dumps({"summary": str(summary_path), "validation": validation}, indent=2), flush=True)
        if not validation["passed"]:
            raise SystemExit(3)
    finally:
        del model
        unload_torch_model_refs()


if __name__ == "__main__":
    main()
