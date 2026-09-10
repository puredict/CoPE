import csv
from pathlib import Path

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


@pytest.mark.parametrize("bad", ([[1] * 6], [[0, 0, 0, 0, 0, 0, float("nan")]]))
def test_action_hash_rejects_invalid_chunks(bad):
    with pytest.raises(CalibrationV21Error):
        action_trajectory_sha256(bad)
