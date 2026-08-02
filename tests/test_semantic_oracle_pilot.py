from __future__ import annotations

import copy
from pathlib import Path

import pytest

from experiments.semantic_oracle_pilot import (
    ARMS,
    audit_pairs,
    load_authorization,
    validate_pilot_manifest,
)


ROOT = Path(__file__).resolve().parents[1]


def test_repository_authorization_is_narrow_and_bound_to_x04() -> None:
    authorization = load_authorization(
        ROOT / "research/semantic_oracle_pilot_2026-08-02/01_AUTHORIZATION.csv",
        repo_root=ROOT,
    )
    assert {int(row["state_id"]) for row in authorization.cases} == {25, 26}
    assert authorization.row["state27_49_locked"] == "true"
    assert authorization.row["run_authorized"] == "true"


def test_manifest_rejects_any_state_outside_the_two_reserve_rows() -> None:
    rows = [
        {
            "pair_id": "replace",
            "state_id": "25",
            "event_type": "replace_pending_goal",
            "stable_steps": "5",
            "deadline": "300",
            "replacement_object": "alphabet_soup_1",
            "post_event_action_budget": "280",
            "hold_steps": "0",
            "status": "reserved_uninspected",
        },
        {
            "pair_id": "cancel",
            "state_id": "27",
            "event_type": "cancel_pending_goal",
            "stable_steps": "5",
            "deadline": "300",
            "replacement_object": "",
            "post_event_action_budget": "0",
            "hold_steps": "30",
            "status": "reserved_uninspected",
        },
    ]
    with pytest.raises(ValueError, match="state25/state26"):
        validate_pilot_manifest(rows)


def arm_row(arm: str) -> dict:
    return {
        "pair_id": "pilot_task01_state25_replace",
        "arm": arm,
        "state_id": 25,
        "event_type": "replace_pending_goal",
        "passed": True,
        "initial_state_sha256": "a",
        "prefix_action_sha256": "b",
        "prefix_action_count": 200,
        "event_policy_step": 200,
        "event_simulator_sha256": "c",
        "event_rgb_sha256": "d",
        "event_packet_sha256": "e",
        "event_recovery_input_sha256": "f",
        "checkpoint_pose_sha256": "g",
        "compiled_directive": "put both objects",
        "final_action_prefix_sha256": "h",
        "final_simulator_sha256": "i",
        "post_event_policy_actions": 150,
        "post_event_policy_action_budget": 280,
        "verification_hold_steps_observed": 0,
        "verification_hold_steps_required": 0,
    }


def test_pair_audit_requires_exact_independent_arm_evidence() -> None:
    rows = [arm_row(arm) for arm in ARMS]
    audit = audit_pairs(rows)
    assert len(audit) == 1
    assert audit[0]["pair_passed"] is True

    drifted = copy.deepcopy(rows)
    drifted[1]["checkpoint_pose_sha256"] = "changed"
    failed = audit_pairs(drifted)
    assert failed[0]["checkpoint_pose_equal"] is False
    assert failed[0]["pair_passed"] is False


def test_pair_audit_rejects_policy_budget_overrun() -> None:
    rows = [arm_row(arm) for arm in ARMS]
    rows[1]["post_event_policy_actions"] = 281
    audit = audit_pairs(rows)
    assert audit[0]["budgets_respected"] is False
    assert audit[0]["pair_passed"] is False
