import csv
from pathlib import Path
import subprocess
import sys

import pytest

from cope_benchmark.repeated_v2.calibration_v2_1 import (
    CALIBRATION_STATE_IDS,
    FORMAL_STATE_IDS,
    CalibrationV21Error,
    action_trajectory_sha256,
    calibration_grid,
    derive_clean_horizon,
    derive_interrupted_budget,
    group_duplicate_trajectories,
    summarize_task_calibration,
    validate_calibration_record,
    validate_initial_state_split,
    validate_state_inventory,
)


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "research/repeated_v2_formal_readiness_v2_1/LIBERO_INIT_STATE_INVENTORY.csv"


def _sha(label: int) -> str:
    return f"{label:064x}"


def _record(state, seed, digest, success, completion, **extra):
    return {
        "task_id": 1,
        "initial_state_id": state,
        "policy_seed": seed,
        "action_trajectory_sha256": digest,
        "success": success,
        "completion_policy_steps": completion,
        **extra,
    }


def _admission_record(state, *, success):
    digest = _sha(state + 1)
    return {
        "schema_version": "repeated_v2_1_clean_calibration_episode_v1",
        "task_id": 1,
        "initial_state_id": state,
        "policy_seed": 101,
        "success": success,
        "status": "success" if success else "timeout",
        "termination_reason": "exact_libero_goal" if success else "policy_budget_exhausted",
        "learned_policy": True,
        "uses_privileged_state": False,
        "clean_episode": True,
        "all_action_validations_pass": True,
        "manual_intervention": False,
        "provider_id": "openvla_native",
        "policy_model_id": "openvla-7b-finetuned-libero-10",
        "checkpoint_sha256": "d36eaa2a334cd52f4a3a94558cf90d82584743ea772fabf76f9e4372e7076076",
        "adapter_source_sha256": _sha(20),
        "runtime_client_sha256": _sha(21),
        "runtime_inference_sha256": _sha(22),
        "protocol_sha256": _sha(23),
        "initial_state_sha256": _sha(100 + state),
        "evidence_ref": f"measured/task1/state{state}/TERMINAL.txt",
        "evidence_sha256": _sha(30 + state),
        "full_trace_sha256": _sha(40 + state),
        "raw_policy_action_sequence_sha256": _sha(50 + state),
        "environment_policy_action_sequence_sha256": digest,
        "action_trajectory_sha256": digest,
        "collection_ceiling_policy_steps": 520,
        "policy_steps_consumed": 240 + state if success else 520,
        "completion_policy_steps": 240 + state if success else None,
        "inference_seconds": 10.0,
        "wall_seconds": 12.0,
    }


def test_enumerated_inventory_and_frozen_state_split_are_complete_and_disjoint():
    with INVENTORY.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    validate_state_inventory(rows)
    assert len(rows) == 500
    assert set(CALIBRATION_STATE_IDS).isdisjoint(FORMAL_STATE_IDS)
    assert len(calibration_grid()) == 100
    assert len({(r["task_id"], r["initial_state_id"]) for r in calibration_grid()}) == 100


def test_any_calibration_formal_state_overlap_is_rejected():
    with pytest.raises(CalibrationV21Error, match="calibration/formal.*overlap"):
        validate_initial_state_split(
            calibration_state_ids=range(10),
            formal_state_ids=(9, 10, 11, 12, 13),
            development_state_ids=range(14, 20),
            reserve_state_ids=range(20, 50),
        )


def test_exact_action_hash_and_duplicate_grouping_ignore_nominal_seed():
    actions = [[0, 0, 0, 0, 0, 0, 1], [0.25, -0.5, 0, 0, 0, 0, -1]]
    digest = action_trajectory_sha256(actions)
    rows = [
        _record(0, 101, digest, True, 250),
        _record(0, 131, digest, True, 250),
        _record(1, 101, _sha(2), False, None),
    ]
    groups = group_duplicate_trajectories(rows)
    assert len(groups) == 2
    duplicate = next(group for group in groups if group["action_trajectory_sha256"] == digest)
    assert duplicate["nominal_run_count"] == 2
    assert duplicate["members"] == ((0, 101), (0, 131))


def test_conflicting_outcomes_for_identical_actions_are_rejected():
    rows = [_record(0, 101, _sha(1), True, 250), _record(0, 131, _sha(1), False, None)]
    with pytest.raises(CalibrationV21Error, match="conflicting outcomes"):
        group_duplicate_trajectories(rows)


def test_clean_horizon_is_deterministic_counts_only_unique_successes():
    rows = [
        _record(0, 101, _sha(1), True, 242),
        _record(0, 131, _sha(1), True, 242),
        _record(1, 101, _sha(2), True, 250),
        _record(2, 101, _sha(3), True, 323),
        _record(3, 101, _sha(4), False, None),
    ]
    first = derive_clean_horizon(rows)
    second = derive_clean_horizon(reversed(rows))
    assert first == second
    assert first.successful_unique_trajectories == 3
    assert first.q95_nearest_rank == 323
    assert first.horizon == 388


def test_clean_horizon_is_unestimable_below_three_unique_successes():
    rows = [
        _record(0, 101, _sha(1), True, 230),
        _record(0, 131, _sha(1), True, 230),
        _record(1, 101, _sha(2), True, 208),
    ]
    decision = derive_clean_horizon(rows)
    assert decision.status == "HORIZON_UNESTIMABLE"
    assert decision.horizon is None


def test_horizon_rule_is_independent_of_method_identity():
    base = [
        _record(0, 101, _sha(1), True, 240),
        _record(1, 101, _sha(2), True, 260),
        _record(2, 101, _sha(3), True, 300),
    ]
    cope = derive_clean_horizon([{**row, "method": "cope_typed_edit"} for row in base])
    baseline = derive_clean_horizon([{**row, "method": "full_state_regeneration"} for row in base])
    assert cope == baseline


def test_interrupted_budget_deduplicates_and_ignores_method_identity():
    records = [
        {"event_family": "displacement", "action_trajectory_sha256": _sha(1),
         "overhead_policy_steps": 20, "paired_success": True, "method": "cope_typed_edit"},
        {"event_family": "displacement", "action_trajectory_sha256": _sha(1),
         "overhead_policy_steps": 20, "paired_success": True, "method": "other"},
        {"event_family": "temporary", "action_trajectory_sha256": _sha(2),
         "overhead_policy_steps": 40, "paired_success": True},
        {"event_family": "temporary", "action_trajectory_sha256": _sha(3),
         "overhead_policy_steps": 100, "paired_success": True},
    ]
    decision = derive_interrupted_budget(388, 4, records)
    assert decision.unique_overhead_measurements == 3
    assert decision.event_allowance == 120
    assert decision.horizon == 868


def test_v21_admission_records_require_real_policy_identity_and_complete_grid():
    records = [_admission_record(state, success=state < 4) for state in range(10)]
    for record in records:
        validate_calibration_record(record)
    summary = summarize_task_calibration(1, records)
    assert summary["nominal_trajectories"] == 10
    assert summary["unique_trajectories"] == 10
    assert summary["horizon"] == 320
    assert summary["clean_success_rate"] == 0.4
    assert summary["eligible_success_rate"] is True
    poisoned = {**records[0], "uses_privileged_state": True}
    with pytest.raises(CalibrationV21Error, match="uses_privileged_state"):
        validate_calibration_record(poisoned)


def test_calibration_driver_self_check_imports_no_model_or_simulator():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_repeated_v2_1_clean_calibration.py"), "--self-check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "no model, simulator, GPU" in result.stdout


@pytest.mark.parametrize("bad", ([[1] * 6], [[0, 0, 0, 0, 0, 0, float("nan")]]))
def test_action_hash_rejects_invalid_chunks(bad):
    with pytest.raises(CalibrationV21Error):
        action_trajectory_sha256(bad)
