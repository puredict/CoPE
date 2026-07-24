from __future__ import annotations

import pytest

from cope.calibration import (
    CalibrationSeedScheme,
    build_calibration_entries,
    validate_openvla_action,
    wilson_interval,
)


def _scheme() -> CalibrationSeedScheme:
    return CalibrationSeedScheme(
        name="test",
        base_seed=20260724,
        task_stride=100,
        state_stride=1,
        forbidden_evaluation_seeds=(11, 29, 47),
    )


def test_calibration_entries_are_fixed_unique_and_disjoint_from_evaluation() -> None:
    entries = build_calibration_entries(
        task_ids=(0, 1, 4, 8),
        state_ids=range(5),
        seed_scheme=_scheme(),
    )
    seeds = {int(entry["seed"]) for entry in entries}
    assert len(entries) == 20
    assert len(seeds) == 20
    assert not seeds & {11, 29, 47}
    assert entries[0]["episode_id"] == "calibration__task00__state00__seed20260724"


def test_seed_scheme_rejects_evaluation_overlap() -> None:
    scheme = CalibrationSeedScheme(
        name="bad",
        base_seed=11,
        task_stride=100,
        state_stride=1,
        forbidden_evaluation_seeds=(11,),
    )
    with pytest.raises(ValueError, match="overlaps evaluation seed"):
        scheme.derive(task_ordinal=0, state_id=0)


def test_action_validation_checks_openvla_libero_gripper_transform() -> None:
    validation = validate_openvla_action(
        [0.1, -0.1, 0.2, 0.0, 0.0, 0.0, 0.0],
        [0.1, -0.1, 0.2, 0.0, 0.0, 0.0, 1.0],
        expected_dim=7,
        action_low=[-1.0] * 7,
        action_high=[1.0] * 7,
    )
    assert validation["passed"]
    assert validation["gates"]["gripper_normalize_binarize_invert"]


def test_action_validation_rejects_non_finite_and_non_binary_gripper() -> None:
    validation = validate_openvla_action(
        [float("nan"), 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        expected_dim=7,
        action_low=[-1.0] * 7,
        action_high=[1.0] * 7,
    )
    assert not validation["passed"]
    assert not validation["gates"]["finite"]
    assert not validation["gates"]["environment_gripper_binarized"]


def test_wilson_interval_has_expected_edge_behavior() -> None:
    assert wilson_interval(0, 0) == (0.0, 0.0)
    lower, upper = wilson_interval(3, 5)
    assert 0.2 < lower < 0.3
    assert 0.85 < upper < 0.9
