from __future__ import annotations

from cope_real_canary import (
    REAL_CANARY_MODES,
    CoPERealCanaryConfig,
    build_plan,
    build_cope_trace,
    core_mode_for,
    make_pair_key,
    validate_real_canary_records,
)


def test_plan_only_requires_explicit_real_run_confirmation() -> None:
    cfg = CoPERealCanaryConfig()
    plan = build_plan(cfg)

    assert plan["requires_explicit_flag"] == "--confirm-real-run"
    assert plan["will_run_modes"] == list(REAL_CANARY_MODES)
    assert plan["safety_guards"]["target_joint_explicit"] is True
    assert plan["safety_guards"]["uses_existing_success_status_helper"] == "extract_episode_status"
    assert plan["safety_guards"]["uses_existing_fresh_observation_helper"] == "refresh_observation_after_sim_change"
    assert plan["safety_guards"]["uses_existing_budget_helper"] == "make_budget_report"
    assert plan["safety_guards"]["uses_existing_target_helper"] == "select_target_joint"


def test_pair_key_matches_fixed_single_condition_canary() -> None:
    pair_key = make_pair_key(CoPERealCanaryConfig())

    assert pair_key["checkpoint"].endswith("openvla-7b-finetuned-libero-spatial")
    assert pair_key["task_suite"] == "libero_spatial"
    assert pair_key["task_id"] == 0
    assert pair_key["initial_state_id"] == 0
    assert pair_key["seed"] == 7
    assert pair_key["target_joint"] == "akita_black_bowl_1_joint0"
    assert pair_key["disturbance_step"] == 70
    assert pair_key["disturbance_delta_xyz"] == [0.10, 0.05, 0.0]
    assert pair_key["max_policy_steps"] == 220


def test_core_mode_mapping_does_not_add_new_experiment_core_mode() -> None:
    assert core_mode_for("clean") == "clean"
    assert core_mode_for("reactive_disturbed") == "reactive_disturbed"
    assert core_mode_for("cope_oracle_patch_prompt") == "reactive_disturbed"


def test_runtime_cope_trace_uses_oracle_label_and_prompt_adapter() -> None:
    cfg = CoPERealCanaryConfig()
    disturbance = {
        "before_qpos": [0.0, 0.1, 0.9, 1.0, 0.0, 0.0, 0.0],
        "after_qpos": [0.1, 0.15, 0.9, 1.0, 0.0, 0.0, 0.0],
    }
    trace = build_cope_trace(
        cfg=cfg,
        task_description=cfg.affected_object,
        disturbance=disturbance,
    )

    assert trace["detector_source"] == "sim_gt_oracle_runtime"
    assert trace["not_empirical_model_measurement"] is True
    assert [event["op"] for event in trace["patch_history"]] == [
        "Revalidate",
        "Expire",
        "Insert",
        "Suspend",
        "Inherit",
        "Inherit",
    ]
    assert trace["state_invariant_errors"] == []
    assert trace["policy_adapter"]["decision"] == "relocalize_regrasp_then_continue"


def _record(mode: str) -> dict:
    cfg = CoPERealCanaryConfig()
    disturbance = None
    cope = None
    if mode != "clean":
        disturbance = {
            "refresh": {
                "fresh_observation": True,
                "consumed_noop_env_step": False,
            }
        }
    if mode == "cope_oracle_patch_prompt":
        cope = {
            "detector_source": "sim_gt_oracle_runtime",
            "patch_history": [{"op": op} for op in ["Revalidate", "Expire", "Insert", "Suspend", "Inherit", "Inherit"]],
            "state_invariant_errors": [],
            "not_empirical_model_measurement": True,
        }
    return {
        "mode": mode,
        "pair_key": make_pair_key(cfg),
        "manual_intervention": False,
        "target_joint": cfg.target_joint,
        "disturbance": disturbance,
        "cope": cope,
        "reset_count": 0,
        "rollback_count": 0,
    }


def test_validate_real_canary_records_accepts_expected_three_modes() -> None:
    records = [_record("clean"), _record("reactive_disturbed"), _record("cope_oracle_patch_prompt")]
    validation = validate_real_canary_records(records)

    assert validation["passed"], validation


def test_validate_real_canary_records_rejects_reset_and_missing_fresh_obs() -> None:
    records = [_record("clean"), _record("reactive_disturbed"), _record("cope_oracle_patch_prompt")]
    records[1]["disturbance"]["refresh"]["fresh_observation"] = False
    records[2]["reset_count"] = 1
    validation = validate_real_canary_records(records)

    assert not validation["passed"]
    assert any("missing fresh observation" in error for error in validation["errors"])
    assert any("used reset or rollback" in error for error in validation["errors"])
