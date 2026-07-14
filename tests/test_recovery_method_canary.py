from __future__ import annotations

from recovery_method_canary import (
    CANARY_MODES,
    FORBIDDEN_MODES,
    PAIR_FIELDS,
    RecoveryCanaryConfig,
    make_pair_key,
    recovery_decision_for_mode,
    validate_records,
)


def test_canary_mode_whitelist_is_exact() -> None:
    assert CANARY_MODES == (
        "reactive_disturbed",
        "structured_relocalize_prompt",
        "stage_backtrack_subgoal",
    )
    assert "clean" in FORBIDDEN_MODES
    assert "verifier_stop" in FORBIDDEN_MODES
    assert "full_reset_replan" in FORBIDDEN_MODES
    assert "oracle_rollback" in FORBIDDEN_MODES


def test_pair_key_contains_strict_fairness_fields() -> None:
    cfg = RecoveryCanaryConfig()
    pair_key = make_pair_key(
        cfg=cfg,
        resolved_target_joint=cfg.target_joint,
        initial_state_digest="abc123",
        resolved_unnorm_key="libero_spatial",
    )
    for field in PAIR_FIELDS:
        assert field in pair_key
    assert pair_key["task_suite"] == "libero_spatial"
    assert pair_key["task_id"] == 0
    assert pair_key["initial_state_id"] == 0
    assert pair_key["seed"] == 7
    assert pair_key["disturbance_delta_xyz"] == [0.10, 0.05, 0.0]
    assert pair_key["max_policy_steps"] == 220
    assert pair_key["warmup_env_steps"] == 10


def test_recovery_decisions_are_prompt_only_for_recovery_modes() -> None:
    original = "put the black bowl on the plate"
    target_joint = "akita_black_bowl_1_joint0"
    reactive = recovery_decision_for_mode(
        mode="reactive_disturbed",
        original_prompt=original,
        current_prompt=original,
        target_joint=target_joint,
    )
    assert reactive["actual_recovery_action_prompt_only"] is False
    assert reactive["new_prompt"] == original

    structured = recovery_decision_for_mode(
        mode="structured_relocalize_prompt",
        original_prompt=original,
        current_prompt=original,
        target_joint=target_joint,
    )
    assert structured["actual_recovery_action_prompt_only"] is True
    assert structured["affected_object"] == "black bowl"
    assert "relocalize the black bowl" in structured["new_prompt"]

    backtrack = recovery_decision_for_mode(
        mode="stage_backtrack_subgoal",
        original_prompt=original,
        current_prompt=original,
        target_joint=target_joint,
    )
    assert backtrack["actual_recovery_action_prompt_only"] is True
    assert backtrack["requested_recovery_stage"] == "the plate"
    assert "pick up the black bowl" in backtrack["new_prompt"]


def _record(mode: str, prompt: str, switched: bool) -> dict:
    pair_key = {
        "checkpoint": "/ckpt",
        "task_suite": "libero_spatial",
        "task_id": 0,
        "initial_state_id": 0,
        "seed": 7,
        "initial_state_digest": "same",
        "target_joint": "akita_black_bowl_1_joint0",
        "disturbance_step": 70,
        "disturbance_delta_xyz": [0.1, 0.05, 0.0],
        "max_policy_steps": 220,
        "warmup_env_steps": 10,
        "camera_resolution": 256,
        "model_family": "openvla",
        "resolved_unnorm_key": "libero_spatial",
        "action_normalization": {
            "normalize_gripper_action": True,
            "binarize_gripper": True,
            "invert_openvla_gripper": True,
        },
    }
    original = "put the black bowl on the plate"
    actions = [
        {
            "policy_step": 70,
            "prompt": prompt,
            "fresh_observation": True,
            "observation_refresh_method": "env._get_observations(force_update=True)",
            "policy_budget_remaining": 149,
        }
    ]
    prompt_switch = None
    if switched:
        prompt_switch = {
            "prompt_switch_step": 70,
            "actual_recovery_action_prompt_only": True,
        }
    return {
        "mode": mode,
        "pair_key": pair_key,
        "policy_step_budget": 220,
        "warmup_simulator_steps": 10,
        "disturbance": {
            "delta_xyz_actual": [0.1, 0.05, 0.0],
            "refresh": {"consumed_noop_env_step": False},
        },
        "timeout": mode == "reactive_disturbed",
        "success": False,
        "manual_intervention": False,
        "original_prompt": original,
        "prompt_switch_event": prompt_switch,
        "actions": actions,
        "num_policy_steps": 1,
        "artifact_paths": {},
    }


def test_validate_records_accepts_fixed_three_mode_canary_without_videos() -> None:
    records = [
        _record("reactive_disturbed", "put the black bowl on the plate", False),
        _record("structured_relocalize_prompt", "relocalize the black bowl at its current position", True),
        _record("stage_backtrack_subgoal", "pick up the black bowl from its current position", True),
    ]
    validation = validate_records(records, check_videos=False)
    assert validation["passed"], validation


def test_validate_records_rejects_timeout_success_and_extra_refresh_step() -> None:
    records = [
        _record("reactive_disturbed", "put the black bowl on the plate", False),
        _record("structured_relocalize_prompt", "relocalize the black bowl at its current position", True),
        _record("stage_backtrack_subgoal", "pick up the black bowl from its current position", True),
    ]
    records[0]["success"] = True
    records[1]["disturbance"]["refresh"]["consumed_noop_env_step"] = True
    validation = validate_records(records, check_videos=False)
    assert not validation["passed"]
    assert any("timeout recorded as success" in error for error in validation["errors"])
    assert any("consumed an extra env noop step" in error for error in validation["errors"])
