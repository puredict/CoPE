from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from cope_oracle_patch_canary import PAIR_FIELDS
from cope_state import (
    apply_patch,
    build_policy_prompt_from_constraint_state,
    initial_libero_pick_place_state,
    make_object_displacement_patch,
    to_json_dict,
    validate_state_invariants,
)
from libero_experiment_core import (
    ExperimentConfig,
    create_libero_env,
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
    unload_torch_model_refs,
    validate_task_and_trial,
)


REAL_CANARY_MODES: tuple[str, ...] = (
    "clean",
    "reactive_disturbed",
    "cope_oracle_patch_prompt",
)


@dataclass(frozen=True)
class CoPERealCanaryConfig:
    checkpoint: str = "/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial"
    task_suite: str = "libero_spatial"
    task_id: int = 0
    initial_state_id: int = 0
    seed: int = 7
    affected_object: str = "black bowl"
    goal: str = "plate"
    target_joint: str = "akita_black_bowl_1_joint0"
    disturbance_step: int = 70
    dx: float = 0.10
    dy: float = 0.05
    max_steps: int = 220
    warmup_env_steps: int = 10
    camera_resolution: int = 256
    resolved_unnorm_key: str = "libero_spatial"
    out_dir: str = "/home/lijingsu/vla/cope_canary_outputs/real_single_condition"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the fixed single-condition CoPE real canary.")
    parser.add_argument("--confirm-real-run", action="store_true", help="actually load OpenVLA/LIBERO and run the canary")
    parser.add_argument("--out-dir", default=CoPERealCanaryConfig.out_dir)
    parser.add_argument("--checkpoint", default=CoPERealCanaryConfig.checkpoint)
    parser.add_argument("--max-steps", type=int, default=CoPERealCanaryConfig.max_steps)
    return parser.parse_args()


def make_pair_key(cfg: CoPERealCanaryConfig) -> dict[str, Any]:
    return {
        "checkpoint": cfg.checkpoint,
        "task_suite": cfg.task_suite,
        "task_id": cfg.task_id,
        "initial_state_id": cfg.initial_state_id,
        "seed": cfg.seed,
        "target_joint": cfg.target_joint,
        "disturbance_step": cfg.disturbance_step,
        "disturbance_delta_xyz": [cfg.dx, cfg.dy, 0.0],
        "max_policy_steps": cfg.max_steps,
        "warmup_env_steps": cfg.warmup_env_steps,
        "camera_resolution": cfg.camera_resolution,
        "model_family": "openvla",
        "resolved_unnorm_key": cfg.resolved_unnorm_key,
    }


def build_plan(cfg: CoPERealCanaryConfig) -> dict[str, Any]:
    return {
        "phase": "Phase C single-condition real canary",
        "requires_explicit_flag": "--confirm-real-run",
        "will_run_modes": list(REAL_CANARY_MODES),
        "will_not_run": ["large_experiment", "multi_task", "multi_seed", "reset_or_rollback_baseline"],
        "config": asdict(cfg),
        "pair_key": make_pair_key(cfg),
        "safety_guards": {
            "target_joint_explicit": cfg.target_joint != "auto",
            "uses_existing_success_status_helper": "extract_episode_status",
            "uses_existing_fresh_observation_helper": "refresh_observation_after_sim_change",
            "uses_existing_budget_helper": "make_budget_report",
            "uses_existing_target_helper": "select_target_joint",
            "manual_intervention": False,
        },
    }


def core_mode_for(mode: str) -> str:
    if mode == "clean":
        return "clean"
    if mode in {"reactive_disturbed", "cope_oracle_patch_prompt"}:
        return "reactive_disturbed"
    raise ValueError(f"unsupported CoPE real canary mode {mode!r}")


def event(event: str, policy_step: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "policy_step": int(policy_step),
        "payload": json_safe(payload or {}),
    }


def build_cope_trace(
    *,
    cfg: CoPERealCanaryConfig,
    task_description: str,
    disturbance: dict[str, Any],
) -> dict[str, Any]:
    initial_state = initial_libero_pick_place_state(
        task_description=task_description,
        affected_object=cfg.affected_object,
        target_joint=cfg.target_joint,
        goal=cfg.goal,
    )
    patch = make_object_displacement_patch(
        affected_object=cfg.affected_object,
        target_joint=cfg.target_joint,
        before_qpos=disturbance["before_qpos"],
        after_qpos=disturbance["after_qpos"],
        goal=cfg.goal,
        detector_source="sim_gt_oracle_runtime",
    )
    patched_state = apply_patch(initial_state, patch)
    prompt, adapter_metadata = build_policy_prompt_from_constraint_state(
        original_task=task_description,
        state=patched_state,
        affected_object=cfg.affected_object,
    )
    return {
        "detector_source": "sim_gt_oracle_runtime",
        "initial_state": to_json_dict(initial_state),
        "patch": [to_json_dict(op) for op in patch],
        "patched_state": to_json_dict(patched_state),
        "patch_history": to_json_dict(patched_state.history),
        "state_invariant_errors": validate_state_invariants(patched_state),
        "policy_prompt": prompt,
        "policy_adapter": to_json_dict(adapter_metadata),
        "not_empirical_model_measurement": True,
    }


def save_video(frames: list[np.ndarray], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import imageio.v2 as imageio

    writer = imageio.get_writer(path, fps=30)
    try:
        for frame in frames:
            writer.append_data(np.asarray(frame, dtype=np.uint8))
    finally:
        writer.close()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(json_safe(record), sort_keys=True, ensure_ascii=True) + "\n")


def episode_dir_name(cfg: CoPERealCanaryConfig, mode: str) -> str:
    return f"task{cfg.task_id}_initial_state{cfg.initial_state_id}_seed{cfg.seed}_{mode}"


def run_real_episode(
    *,
    mode: str,
    cfg: CoPERealCanaryConfig,
    model: Any,
    processor: Any,
    model_cfg: Any,
    task_suite: Any,
    run_root: Path,
) -> dict[str, Any]:
    if mode not in REAL_CANARY_MODES:
        raise ValueError(f"mode {mode!r} is not allowed")
    if cfg.target_joint == "auto":
        raise ValueError("CoPE real canary requires an explicit target_joint")

    exp_cfg = ExperimentConfig(
        checkpoint=cfg.checkpoint,
        task_suite=cfg.task_suite,
        task_id=cfg.task_id,
        trial_id=cfg.initial_state_id,
        mode=core_mode_for(mode),
        max_steps=cfg.max_steps,
        num_steps_wait=cfg.warmup_env_steps,
        disturbance_step=cfg.disturbance_step,
        target_joint=cfg.target_joint,
        dx=cfg.dx,
        dy=cfg.dy,
        seed=cfg.seed,
        resolution=cfg.camera_resolution,
        enable_auto_disturbance=False,
    )
    set_seed(cfg.seed)
    initial_states = validate_task_and_trial(task_suite, exp_cfg)
    task = task_suite.get_task(cfg.task_id)
    env, task_description = create_libero_env(task, exp_cfg)
    episode_dir = run_root / episode_dir_name(cfg, mode)
    raw_video_path = episode_dir / "raw.mp4"
    frames: list[np.ndarray] = []
    actions: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = [event("episode_start", 0, {"mode": mode, "pair_key": make_pair_key(cfg)})]
    disturbance_record: dict[str, Any] | None = None
    cope_trace: dict[str, Any] | None = None
    prompt = task_description
    reward = 0.0
    done = False
    info: dict[str, Any] = {}
    extra_env_steps = 0

    try:
        env.reset()
        obs = env.set_init_state(initial_states[cfg.initial_state_id])
        target_selection = select_target_joint(env, task_description, cfg.target_joint)
        resolved_target_joint = target_selection.selected_joint
        if resolved_target_joint != cfg.target_joint:
            raise ValueError(f"resolved target {resolved_target_joint!r} does not match expected {cfg.target_joint!r}")

        for _ in range(cfg.warmup_env_steps):
            obs, reward, done, info = env.step(get_dummy_action("openvla"))
        events.append(event("warmup_complete", 0, {"warmup_env_steps": cfg.warmup_env_steps}))

        resize_size = get_image_resize_size(model_cfg)
        for policy_step in range(cfg.max_steps):
            fresh_observation = False
            refresh = None
            if mode != "clean" and policy_step == cfg.disturbance_step:
                before_qpos = get_joint_qpos(env, cfg.target_joint)
                disturbance_record = move_free_joint_xy(env, cfg.target_joint, cfg.dx, cfg.dy)
                after_qpos = get_joint_qpos(env, cfg.target_joint)
                disturbance_record["before_qpos"] = before_qpos
                disturbance_record["after_qpos"] = after_qpos
                disturbance_record["delta_xyz_actual"] = [after_qpos[i] - before_qpos[i] for i in range(3)]
                obs, refresh = refresh_observation_after_sim_change(env, model_cfg)
                refresh = dict(refresh)
                refresh["fresh_observation"] = True
                disturbance_record["refresh"] = refresh
                extra_env_steps += int(bool(refresh.get("consumed_noop_env_step")))
                fresh_observation = True
                events.append(event("disturbance_applied", policy_step, disturbance_record))
                if mode == "cope_oracle_patch_prompt":
                    cope_trace = build_cope_trace(cfg=cfg, task_description=task_description, disturbance=disturbance_record)
                    prompt = str(cope_trace["policy_prompt"])
                    events.append(
                        event(
                            "cope_patch_applied",
                            policy_step,
                            {
                                "detector_source": cope_trace["detector_source"],
                                "patch_ops": [item["op"] for item in cope_trace["patch_history"]],
                                "policy_prompt": prompt,
                            },
                        )
                    )

            step = execute_policy_step(
                cfg=model_cfg,
                model=model,
                processor=processor,
                env=env,
                obs=obs,
                prompt=prompt,
                resize_size=resize_size,
            )
            obs = step.next_obs
            reward = step.reward
            done = step.done
            info = dict(step.info)
            frames.append(step.raw_frame)
            step_status = extract_episode_status(reward, done, info, policy_step + 1, cfg.max_steps)
            actions.append(
                {
                    "policy_step": policy_step,
                    "prompt": prompt,
                    "raw_action": step.raw_action,
                    "env_action": step.env_action,
                    "reward": reward,
                    "done": done,
                    "episode_status": step_status.status,
                    "fresh_observation": fresh_observation,
                    "observation_refresh": refresh,
                    "video_frame_index": len(frames) - 1,
                }
            )
            if step_status.success or step_status.timeout or step_status.simulator_error:
                break

        episode_status = extract_episode_status(reward, done, info, len(actions), cfg.max_steps)
        budget = make_budget_report(
            policy_step_budget=cfg.max_steps,
            warmup_simulator_steps=cfg.warmup_env_steps,
            policy_inference_steps=len(actions),
            extra_environment_steps=extra_env_steps,
            pre_disturbance_policy_steps=min(len(actions), cfg.disturbance_step) if disturbance_record else len(actions),
            reset_count=0,
            rollback_count=0,
            success=episode_status.success,
        )
        save_video(frames, raw_video_path)
        record = {
            "mode": mode,
            "pair_key": make_pair_key(cfg),
            "manual_intervention": False,
            "formal_run": True,
            "target_joint": cfg.target_joint,
            "target_selection": json_safe(target_selection),
            "task_description": task_description,
            "disturbance": disturbance_record,
            "cope": cope_trace,
            "status": episode_status.status,
            "success": episode_status.success,
            "timeout": episode_status.timeout,
            "stopped": episode_status.stopped,
            "simulator_error": episode_status.simulator_error,
            "episode_status": json_safe(episode_status),
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
            "video_path": str(raw_video_path),
            "actions": actions,
            "events": events,
        }
        write_json(episode_dir / "run_config.json", {"config": asdict(cfg), "mode": mode})
        write_jsonl(episode_dir / "events.jsonl", events)
        write_jsonl(episode_dir / "actions.jsonl", actions)
        write_json(episode_dir / "episode_summary.json", record)
        return record
    finally:
        try:
            env.close()
        except Exception:
            pass


def validate_real_canary_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    modes = [record.get("mode") for record in records]
    if modes != list(REAL_CANARY_MODES):
        errors.append(f"expected modes {list(REAL_CANARY_MODES)}, got {modes}")
    pair_keys = [record.get("pair_key", {}) for record in records]
    for idx, pair_key in enumerate(pair_keys):
        for field in PAIR_FIELDS:
            if field not in pair_key:
                errors.append(f"record {idx} pair_key missing {field}")
    if pair_keys:
        reference = {field: pair_keys[0].get(field) for field in PAIR_FIELDS}
        for idx, pair_key in enumerate(pair_keys[1:], start=1):
            comparable = {field: pair_key.get(field) for field in PAIR_FIELDS}
            if comparable != reference:
                errors.append(f"record {idx} pair key mismatch")
    for idx, record in enumerate(records):
        if record.get("manual_intervention"):
            errors.append(f"record {idx} has manual intervention")
        if record.get("reset_count") != 0 or record.get("rollback_count") != 0:
            errors.append(f"record {idx} used reset or rollback")
        if record.get("target_joint") == "auto":
            errors.append(f"record {idx} used auto target joint")
    clean = next((record for record in records if record.get("mode") == "clean"), None)
    if clean is not None and clean.get("disturbance") is not None:
        errors.append("clean record must not contain disturbance")
    for mode in ("reactive_disturbed", "cope_oracle_patch_prompt"):
        record = next((item for item in records if item.get("mode") == mode), None)
        if record is None:
            continue
        disturbance = record.get("disturbance") or {}
        refresh = disturbance.get("refresh") or {}
        if not refresh.get("fresh_observation"):
            errors.append(f"{mode} missing fresh observation marker")
        if refresh.get("consumed_noop_env_step"):
            errors.append(f"{mode} consumed noop env step during refresh")
    cope_record = next((record for record in records if record.get("mode") == "cope_oracle_patch_prompt"), None)
    if cope_record is not None:
        cope = cope_record.get("cope") or {}
        ops = [event.get("op") for event in cope.get("patch_history", [])]
        expected = ["Revalidate", "Expire", "Insert", "Suspend", "Inherit", "Inherit"]
        if ops != expected:
            errors.append(f"CoPE patch ops mismatch: {ops}")
        if cope.get("detector_source") != "sim_gt_oracle_runtime":
            errors.append("CoPE detector source must be sim_gt_oracle_runtime")
        if cope.get("state_invariant_errors"):
            errors.append(f"CoPE invariant errors: {cope.get('state_invariant_errors')}")
        if not cope.get("not_empirical_model_measurement"):
            errors.append("CoPE oracle trace must be marked not_empirical_model_measurement")
    return {"passed": not errors, "errors": errors, "records": len(records)}


def run_real_canary(cfg: CoPERealCanaryConfig) -> dict[str, Any]:
    task_suite = get_benchmark_suite(cfg.task_suite)
    exp_cfg = ExperimentConfig(
        checkpoint=cfg.checkpoint,
        task_suite=cfg.task_suite,
        task_id=cfg.task_id,
        trial_id=cfg.initial_state_id,
        mode="reactive_disturbed",
        max_steps=cfg.max_steps,
        num_steps_wait=cfg.warmup_env_steps,
        disturbance_step=cfg.disturbance_step,
        target_joint=cfg.target_joint,
        dx=cfg.dx,
        dy=cfg.dy,
        seed=cfg.seed,
        resolution=cfg.camera_resolution,
        enable_auto_disturbance=False,
    )
    run_root = Path(cfg.out_dir) / time.strftime("%Y_%m_%d-%H_%M_%S")
    model = processor = model_cfg = None
    records: list[dict[str, Any]] = []
    try:
        model, processor, model_cfg, resolved_unnorm_key = load_model_and_processor(exp_cfg)
        cfg = CoPERealCanaryConfig(**{**asdict(cfg), "resolved_unnorm_key": resolved_unnorm_key})
        for mode in REAL_CANARY_MODES:
            records.append(
                run_real_episode(
                    mode=mode,
                    cfg=cfg,
                    model=model,
                    processor=processor,
                    model_cfg=model_cfg,
                    task_suite=task_suite,
                    run_root=run_root,
                )
            )
        validation = validate_real_canary_records(records)
        summary = {"config": asdict(cfg), "records": records, "validation": validation}
        write_json(run_root / "summary.json", summary)
        with (run_root / "episodes.jsonl").open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(json_safe(record), sort_keys=True, ensure_ascii=True) + "\n")
        return {"run_root": str(run_root), "validation": validation}
    finally:
        if model is not None or processor is not None or model_cfg is not None:
            unload_torch_model_refs()


def main() -> None:
    args = parse_args()
    cfg = CoPERealCanaryConfig(checkpoint=args.checkpoint, max_steps=args.max_steps, out_dir=args.out_dir)
    if not args.confirm_real_run:
        print(json.dumps({"plan_only": True, "plan": build_plan(cfg)}, indent=2, ensure_ascii=True))
        return
    result = run_real_canary(cfg)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    if not result["validation"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
