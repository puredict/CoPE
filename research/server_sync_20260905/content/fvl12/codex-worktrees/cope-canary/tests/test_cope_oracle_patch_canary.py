from __future__ import annotations

from cope_oracle_patch_canary import (
    COPE_CANARY_MODES,
    FORBIDDEN_REALISM_MIXED_MODES,
    PAIR_FIELDS,
    CoPEOracleCanaryConfig,
    build_dry_run_records,
    make_pair_key,
    validate_cope_canary_records,
)


def test_cope_canary_mode_boundary_is_current_world_only() -> None:
    assert COPE_CANARY_MODES == ("reactive_disturbed", "cope_oracle_patch_prompt")
    assert "full_reset_replan" in FORBIDDEN_REALISM_MIXED_MODES
    assert "oracle_rollback" in FORBIDDEN_REALISM_MIXED_MODES
    assert "verifier_stop" in FORBIDDEN_REALISM_MIXED_MODES


def test_pair_key_contains_strict_existing_fairness_fields() -> None:
    pair_key = make_pair_key(CoPEOracleCanaryConfig())
    for field in PAIR_FIELDS:
        assert field in pair_key
    assert pair_key["target_joint"] == "akita_black_bowl_1_joint0"
    assert pair_key["disturbance_step"] == 70
    assert pair_key["disturbance_delta_xyz"] == [0.10, 0.05, 0.0]
    assert pair_key["max_policy_steps"] == 220


def test_dry_run_records_validate_cope_patch_trace() -> None:
    records = build_dry_run_records(CoPEOracleCanaryConfig())
    validation = validate_cope_canary_records(records)

    assert validation["passed"], validation
    assert [record["mode"] for record in records] == list(COPE_CANARY_MODES)
    cope = records[1]["cope"]
    assert [event["op"] for event in cope["patch_history"]] == [
        "Revalidate",
        "Expire",
        "Insert",
        "Suspend",
        "Inherit",
        "Inherit",
    ]
    assert cope["detector_source"] == "sim_gt_oracle_dry_run"
    assert cope["not_empirical_model_measurement"] is True
    assert cope["policy_adapter"]["decision"] == "relocalize_regrasp_then_continue"
    assert records[1]["reset_count"] == 0
    assert records[1]["rollback_count"] == 0


def test_validator_rejects_missing_fresh_obs_or_reset_privilege() -> None:
    records = build_dry_run_records(CoPEOracleCanaryConfig())
    records[0]["disturbance"]["refresh"]["fresh_observation"] = False
    records[1]["reset_count"] = 1

    validation = validate_cope_canary_records(records)

    assert not validation["passed"]
    assert any("missing fresh observation marker" in error for error in validation["errors"])
    assert any("used reset/rollback" in error for error in validation["errors"])


def test_validator_rejects_unmarked_model_measurement_claim() -> None:
    records = build_dry_run_records(CoPEOracleCanaryConfig())
    records[1]["cope"]["not_empirical_model_measurement"] = False

    validation = validate_cope_canary_records(records)

    assert not validation["passed"]
    assert any("not_empirical_model_measurement" in error for error in validation["errors"])
