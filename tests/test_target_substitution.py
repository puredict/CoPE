from __future__ import annotations

import copy

import pytest

from cope.target_substitution import (
    BACK_REGION,
    FRONT_PROMPT,
    FRONT_REGION,
    LiftMilestone,
    StableLiftDetector,
    TargetStateValidationError,
    build_oracle_target_state,
    build_target_event,
    commitment_id,
    compile_target_prompt,
    current_goal_success,
    validate_oracle_target_state,
)


def valid_pair():
    event = build_target_event(
        LiftMilestone(policy_step=78, initial_z=0.88, current_z=0.92, stable_steps=5),
        pair_key="pair",
    )
    return event, build_oracle_target_state(event)


def validate(event, state, *, lifted=True) -> None:
    validate_oracle_target_state(
        state,
        event,
        previous_state_version=0,
        physically_lifted=lifted,
    )


def test_lift_detector_requires_stable_physical_lift_outside_both_targets() -> None:
    detector = StableLiftDetector(
        initial_z=0.88,
        minimum_lift=0.03,
        required_stable_steps=3,
    )
    assert detector.observe(0, book_z=0.92, in_back=False, in_front=False) is None
    assert detector.observe(1, book_z=0.90, in_back=False, in_front=False) is None
    assert detector.observe(2, book_z=0.92, in_back=False, in_front=False) is None
    assert detector.observe(3, book_z=0.92, in_back=False, in_front=False) is None
    milestone = detector.observe(4, book_z=0.92, in_back=False, in_front=False)
    assert milestone is not None
    assert milestone.policy_step == 4


def test_target_membership_prevents_false_lift_trigger() -> None:
    detector = StableLiftDetector(initial_z=0.88, required_stable_steps=1)
    assert detector.observe(0, book_z=1.0, in_back=True, in_front=False) is None
    assert detector.observe(1, book_z=1.0, in_back=False, in_front=True) is None


def test_valid_target_edit_preserves_lift_progress_and_compiles_from_state() -> None:
    event, state = valid_pair()
    state["controller_prompt"] = "malicious diagnostic prompt"
    validate(event, state)
    assert compile_target_prompt(state) == FRONT_PROMPT
    assert state["progress_ledger"][0]["still_goal_relevant"] is True


def test_wrong_authority_target_or_physical_evidence_is_rejected() -> None:
    event, state = valid_pair()
    broken = copy.deepcopy(event)
    broken["authority"] = 1
    with pytest.raises(TargetStateValidationError, match="authorized"):
        validate(broken, state)
    broken = copy.deepcopy(event)
    broken["target_commitment_id"] = commitment_id(FRONT_REGION)
    with pytest.raises(TargetStateValidationError, match="wrong commitment"):
        validate(broken, state)
    with pytest.raises(TargetStateValidationError, match="not physically true"):
        validate(event, state, lifted=False)


def test_stale_state_and_broken_lineage_are_rejected() -> None:
    event, state = valid_pair()
    broken = copy.deepcopy(state)
    broken["state_version"] = 0
    with pytest.raises(TargetStateValidationError, match="stale"):
        validate(event, broken)
    broken = copy.deepcopy(state)
    replacement = next(
        item for item in broken["commitments"] if item["id"] == commitment_id(FRONT_REGION)
    )
    replacement["supersession_links"] = []
    with pytest.raises(TargetStateValidationError, match="lineage"):
        validate(event, broken)


def test_success_uses_front_not_back_target() -> None:
    assert current_goal_success({"front": True, "back": False})
    assert not current_goal_success({"front": False, "back": True})
    event, state = valid_pair()
    assert state["commitments"][0]["id"] == commitment_id(BACK_REGION)
