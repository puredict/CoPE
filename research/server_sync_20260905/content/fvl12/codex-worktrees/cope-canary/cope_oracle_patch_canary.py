from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cope_state import (
    ConstraintState,
    apply_patch,
    build_policy_prompt_from_constraint_state,
    initial_libero_pick_place_state,
    make_object_displacement_patch,
    to_json_dict,
    validate_state_invariants,
)


COPE_CANARY_MODES: tuple[str, ...] = (
    "reactive_disturbed",
    "cope_oracle_patch_prompt",
)

FORBIDDEN_REALISM_MIXED_MODES: tuple[str, ...] = (
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
    "target_joint",
    "disturbance_step",
    "disturbance_delta_xyz",
    "max_policy_steps",
    "warmup_env_steps",
    "camera_resolution",
    "model_family",
    "resolved_unnorm_key",
)


@dataclass(frozen=True)
class CoPEOracleCanaryConfig:
    checkpoint: str = "/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial"
    task_suite: str = "libero_spatial"
    task_id: int = 0
    initial_state_id: int = 0
    seed: int = 7
    task_description: str = "pick up the black bowl between the plate and the ramekin and place it on the plate"
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
    out_dir: str = "/home/lijingsu/vla/cope_canary_outputs/dry_run"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and validate a dry-run CoPE oracle patch canary record.")
    parser.add_argument("--out-dir", default=CoPEOracleCanaryConfig.out_dir)
    parser.add_argument("--write", action="store_true", help="write dry-run summary files; no model or simulator is loaded")
    return parser.parse_args()


def make_pair_key(cfg: CoPEOracleCanaryConfig) -> dict[str, Any]:
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


def simulated_disturbance(cfg: CoPEOracleCanaryConfig) -> dict[str, Any]:
    before_qpos = [0.07051401944683737, 0.1957706591982865, 0.9500326696891234, 1.0, 0.0, 0.0, 0.0]
    after_qpos = [
        before_qpos[0] + cfg.dx,
        before_qpos[1] + cfg.dy,
        before_qpos[2],
        before_qpos[3],
        before_qpos[4],
        before_qpos[5],
        before_qpos[6],
    ]
    return {
        "joint": cfg.target_joint,
        "before_qpos": before_qpos,
        "after_qpos": after_qpos,
        "delta_xyz_actual": [after_qpos[i] - before_qpos[i] for i in range(3)],
        "refresh": {
            "fresh_observation": True,
            "method": "existing_refresh_observation_after_sim_change",
            "consumed_noop_env_step": False,
            "dry_run_no_simulator_loaded": True,
        },
    }


def _event(event: str, policy_step: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "policy_step": int(policy_step),
        "payload": to_json_dict(payload),
    }


def build_reactive_record(cfg: CoPEOracleCanaryConfig) -> dict[str, Any]:
    disturbance = simulated_disturbance(cfg)
    return {
        "mode": "reactive_disturbed",
        "pair_key": make_pair_key(cfg),
        "manual_intervention": False,
        "formal_run": False,
        "dry_run": True,
        "target_joint": cfg.target_joint,
        "disturbance": disturbance,
        "reset_count": 0,
        "rollback_count": 0,
        "policy_step_budget": cfg.max_steps,
        "warmup_simulator_steps": cfg.warmup_env_steps,
        "cope": None,
        "events": [
            _event("episode_start_dry_run", 0, {"mode": "reactive_disturbed"}),
            _event("disturbance_applied", cfg.disturbance_step, disturbance),
        ],
    }


def build_cope_record(cfg: CoPEOracleCanaryConfig) -> dict[str, Any]:
    disturbance = simulated_disturbance(cfg)
    initial_state = initial_libero_pick_place_state(
        task_description=cfg.task_description,
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
        detector_source="sim_gt_oracle_dry_run",
    )
    patched_state = apply_patch(initial_state, patch)
    prompt, adapter_metadata = build_policy_prompt_from_constraint_state(
        original_task=cfg.task_description,
        state=patched_state,
        affected_object=cfg.affected_object,
    )
    return {
        "mode": "cope_oracle_patch_prompt",
        "pair_key": make_pair_key(cfg),
        "manual_intervention": False,
        "formal_run": False,
        "dry_run": True,
        "target_joint": cfg.target_joint,
        "disturbance": disturbance,
        "reset_count": 0,
        "rollback_count": 0,
        "policy_step_budget": cfg.max_steps,
        "warmup_simulator_steps": cfg.warmup_env_steps,
        "cope": {
            "detector_source": "sim_gt_oracle_dry_run",
            "initial_state": to_json_dict(initial_state),
            "patch": [to_json_dict(op) for op in patch],
            "patched_state": to_json_dict(patched_state),
            "patch_history": to_json_dict(patched_state.history),
            "state_invariant_errors": validate_state_invariants(patched_state),
            "policy_prompt": prompt,
            "policy_adapter": to_json_dict(adapter_metadata),
            "not_empirical_model_measurement": True,
        },
        "events": [
            _event("episode_start_dry_run", 0, {"mode": "cope_oracle_patch_prompt"}),
            _event("disturbance_applied", cfg.disturbance_step, disturbance),
            _event(
                "cope_patch_applied",
                cfg.disturbance_step,
                {
                    "detector_source": "sim_gt_oracle_dry_run",
                    "patch_ops": [op.op for op in patch],
                    "state_revision": patched_state.revision,
                },
            ),
            _event(
                "cope_policy_prompt_ready",
                cfg.disturbance_step,
                {
                    "prompt": prompt,
                    "policy_adapter": adapter_metadata,
                },
            ),
        ],
    }


def build_dry_run_records(cfg: CoPEOracleCanaryConfig) -> list[dict[str, Any]]:
    return [build_reactive_record(cfg), build_cope_record(cfg)]


def validate_cope_canary_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    modes = [record.get("mode") for record in records]
    if modes != list(COPE_CANARY_MODES):
        errors.append(f"expected modes {list(COPE_CANARY_MODES)}, got {modes}")
    if any(mode in FORBIDDEN_REALISM_MIXED_MODES for mode in modes):
        errors.append("reset, rollback, or verifier-stop modes are forbidden in the CoPE current-world canary")

    pair_keys = [record.get("pair_key", {}) for record in records]
    for idx, pair_key in enumerate(pair_keys):
        for field in PAIR_FIELDS:
            if field not in pair_key:
                errors.append(f"record {idx} pair_key missing {field}")
    if len(pair_keys) >= 2:
        reference = {field: pair_keys[0].get(field) for field in PAIR_FIELDS}
        for idx, pair_key in enumerate(pair_keys[1:], start=1):
            comparable = {field: pair_key.get(field) for field in PAIR_FIELDS}
            if comparable != reference:
                errors.append(f"record {idx} pair_key differs from reference")

    for idx, record in enumerate(records):
        if record.get("manual_intervention"):
            errors.append(f"record {idx} has manual_intervention=true")
        if record.get("reset_count") != 0 or record.get("rollback_count") != 0:
            errors.append(f"record {idx} used reset/rollback")
        disturbance = record.get("disturbance") or {}
        refresh = disturbance.get("refresh") or {}
        if not refresh.get("fresh_observation"):
            errors.append(f"record {idx} missing fresh observation marker")
        if refresh.get("consumed_noop_env_step"):
            errors.append(f"record {idx} consumed a noop env step during refresh")

    cope_records = [record for record in records if record.get("mode") == "cope_oracle_patch_prompt"]
    if len(cope_records) != 1:
        errors.append("expected exactly one cope_oracle_patch_prompt record")
    else:
        cope = cope_records[0].get("cope") or {}
        patch_history = cope.get("patch_history") or []
        ops = [event.get("op") for event in patch_history]
        expected_prefix = ["Revalidate", "Expire", "Insert", "Suspend", "Inherit", "Inherit"]
        if ops != expected_prefix:
            errors.append(f"CoPE patch ops mismatch: expected {expected_prefix}, got {ops}")
        if cope.get("state_invariant_errors"):
            errors.append(f"CoPE state invariant errors: {cope.get('state_invariant_errors')}")
        if cope.get("detector_source") != "sim_gt_oracle_dry_run":
            errors.append("CoPE detector source must be explicitly oracle dry-run")
        if not cope.get("not_empirical_model_measurement"):
            errors.append("CoPE dry-run must be marked not_empirical_model_measurement")
        adapter = cope.get("policy_adapter") or {}
        if adapter.get("decision") != "relocalize_regrasp_then_continue":
            errors.append(f"unexpected policy adapter decision {adapter.get('decision')!r}")

    return {"passed": not errors, "errors": errors, "warnings": warnings, "records": len(records)}


def write_dry_run_outputs(records: list[dict[str, Any]], validation: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    episodes_path = out_dir / "episodes.jsonl"
    summary_path = out_dir / "summary.json"
    with episodes_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(to_json_dict(record), sort_keys=True, ensure_ascii=True) + "\n")
    summary = {
        "dry_run": True,
        "records": records,
        "validation": validation,
        "note": "No model, simulator, or LIBERO rollout was loaded.",
    }
    summary_path.write_text(json.dumps(to_json_dict(summary), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return {"episodes_jsonl": str(episodes_path), "summary_json": str(summary_path)}


def main() -> None:
    args = parse_args()
    cfg = CoPEOracleCanaryConfig(out_dir=args.out_dir)
    records = build_dry_run_records(cfg)
    validation = validate_cope_canary_records(records)
    output_paths = {}
    if args.write:
        output_paths = write_dry_run_outputs(records, validation, Path(cfg.out_dir))
    print(json.dumps({"validation": validation, "output_paths": output_paths}, indent=2, ensure_ascii=True))
    if not validation["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
