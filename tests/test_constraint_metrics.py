from __future__ import annotations

import pytest

from cope_benchmark.interruptions import AxisAlignedBox
from cope_benchmark.metrics import (
    compute_progress_preservation,
    compute_unaffected_constraint_survival,
    detect_invalid_restore,
    score_step_constraints,
)


def test_progress_preservation_and_silent_commitment_loss() -> None:
    metrics = compute_progress_preservation(
        {"placed_a": True, "placed_b": True},
        {"placed_a": True, "placed_b": False},
        commitment_names=("placed_a", "placed_b"),
        declared_modified_slots=("progress:placed_a",),
    )
    assert metrics.progress_preservation == 0.5
    assert metrics.regressions == ("placed_b",)
    assert metrics.silent_commitment_loss == ("placed_b",)


def test_unaffected_constraint_survival_ignores_event_affected_slot() -> None:
    metrics = compute_unaffected_constraint_survival(
        {"safety": "active", "target_pose": [0, 0], "preference": "active"},
        {"safety": "active", "target_pose": [1, 0]},
        affected_slots=("target_pose",),
    )
    assert metrics.unaffected_constraint_survival == 0.5
    assert metrics.lost_unaffected_slots == ("preference",)


def test_no_go_zone_scores_swept_segment_not_just_endpoint() -> None:
    zone = AxisAlignedBox((-0.1, -0.1, 0.4), (0.1, 0.1, 0.8))
    metrics = score_step_constraints(
        raw_action=[0.01, 0.0, 0.0, 0, 0, 0, 0],
        executed_action=[0.01, 0.0, 0.0, 0, 0, 0, 0],
        eef_position_before=(-0.2, 0.0, 0.6),
        eef_position_after=(0.2, 0.0, 0.6),
        dt_seconds=0.05,
        contact_impulse_proxy=0.0,
        gentle_preferences={},
        active_no_go_zones={"z": zone},
        safety_shield_intervened=False,
    )
    assert metrics.no_go_violation_zone_ids == ("z",)


def test_gentle_preference_scores_raw_violation_and_shield_separately() -> None:
    metrics = score_step_constraints(
        raw_action=[0.08, 0.0, 0.0, 0, 0, 0, 0],
        executed_action=[0.03, 0.0, 0.0, 0, 0, 0, 0],
        eef_position_before=(0.0, 0.0, 0.5),
        eef_position_after=(0.02, 0.0, 0.5),
        dt_seconds=0.05,
        contact_impulse_proxy=0.2,
        gentle_preferences={
            "gentle": {
                "translation_ceiling": 0.035,
                "eef_speed_ceiling": 0.22,
                "contact_impulse_proxy_ceiling": 0.12,
            }
        },
        active_no_go_zones={},
        safety_shield_intervened=True,
    )
    assert metrics.translation_magnitude == pytest.approx(0.08)
    assert metrics.gentle_translation_violation
    assert metrics.gentle_speed_violation
    assert metrics.gentle_contact_violation
    assert metrics.preference_violation
    assert metrics.safety_shield_intervened
    assert metrics.executed_action[0] == pytest.approx(0.03)


def test_invalid_restore_requires_slot_version_and_lineage() -> None:
    invalid = detect_invalid_restore(
        [
            {"op": "restore", "slot": "target", "expected_version": 2},
            {
                "op": "restore",
                "slot": "preference",
                "expected_version": 1,
                "source_event_id": "e1",
            },
        ],
        current_slot_versions={"target": 1, "preference": 1},
    )
    assert invalid == ("operation[0]/target:version_mismatch",)
