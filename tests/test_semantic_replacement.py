from __future__ import annotations

import copy

import pytest

from cope.semantic_replacement import (
    FULL_STATE_SCHEMA,
    FullStateValidationError,
    MilestoneEvent,
    StableFirstMilestoneDetector,
    apply_oracle_replacement_patch,
    build_oracle_full_state,
    build_replacement_event,
    compile_controller_prompt,
    current_goal_success,
    goal_commitment_id,
    validate_oracle_full_state,
)


def milestone() -> MilestoneEvent:
    return MilestoneEvent(
        policy_step=120,
        done_object="cream_cheese_1",
        pending_object="butter_1",
        stable_steps=5,
    )


def valid_pair():
    event = build_replacement_event(milestone(), pair_key="pair")
    state = build_oracle_full_state(event)
    return event, state


def validate(event, state) -> None:
    validate_oracle_full_state(
        state,
        event,
        previous_state_version=0,
        physically_true_objects=("cream_cheese_1",),
    )


def test_milestone_requires_five_stable_samples_of_exactly_one_original_goal() -> None:
    detector = StableFirstMilestoneDetector(required_stable_steps=5, deadline=300)
    for step in range(4):
        assert detector.observe(step, {"cream_cheese_1": True, "butter_1": False}) is None
    event = detector.observe(4, {"cream_cheese_1": True, "butter_1": False})
    assert event is not None
    assert event.done_object == "cream_cheese_1"
    assert event.pending_object == "butter_1"
    assert detector.observe(5, {"cream_cheese_1": True, "butter_1": False}) is None


def test_milestone_stability_resets_on_regression_or_both_complete() -> None:
    detector = StableFirstMilestoneDetector(required_stable_steps=3)
    assert detector.observe(0, {"cream_cheese_1": True, "butter_1": False}) is None
    assert detector.observe(1, {"cream_cheese_1": False, "butter_1": False}) is None
    assert detector.observe(2, {"cream_cheese_1": True, "butter_1": True}) is None
    assert detector.observe(3, {"cream_cheese_1": False, "butter_1": True}) is None
    assert detector.observe(4, {"cream_cheese_1": False, "butter_1": True}) is None
    event = detector.observe(5, {"cream_cheese_1": False, "butter_1": True})
    assert event is not None and event.done_object == "butter_1"


def test_milestone_does_not_trigger_after_deadline() -> None:
    detector = StableFirstMilestoneDetector(required_stable_steps=1, deadline=10)
    assert detector.observe(11, {"cream_cheese_1": True, "butter_1": False}) is None


def test_valid_oracle_full_state_passes_and_compiles_from_state_not_diagnostic_prompt() -> None:
    event, state = valid_pair()
    state["controller_prompt"] = "malicious diagnostic prompt"
    validate(event, state)
    assert state["schema_version"] == FULL_STATE_SCHEMA
    assert compile_controller_prompt(state) == (
        "put both the alphabet soup and the cream cheese box in the basket"
    )


def test_duplicate_commitment_ids_are_rejected() -> None:
    event, state = valid_pair()
    state["commitments"][2]["id"] = state["commitments"][0]["id"]
    with pytest.raises(FullStateValidationError, match="duplicate"):
        validate(event, state)


def test_unauthorized_event_is_rejected() -> None:
    event, state = valid_pair()
    event["authority"] = 1
    with pytest.raises(FullStateValidationError, match="not authorized"):
        validate(event, state)


def test_stale_state_version_is_rejected() -> None:
    event, state = valid_pair()
    state["state_version"] = 0
    with pytest.raises(FullStateValidationError, match="stale"):
        validate(event, state)


def test_wrong_target_commitment_is_rejected() -> None:
    event, state = valid_pair()
    event["target_commitment_id"] = goal_commitment_id("cream_cheese_1")
    with pytest.raises(FullStateValidationError, match="wrong commitment"):
        validate(event, state)


def test_false_physical_progress_is_rejected() -> None:
    event, state = valid_pair()
    with pytest.raises(FullStateValidationError, match="not physically true"):
        validate_oracle_full_state(
            state,
            event,
            previous_state_version=0,
            physically_true_objects=(),
        )


def test_wrong_lifecycle_or_lineage_is_rejected() -> None:
    event, state = valid_pair()
    broken = copy.deepcopy(state)
    broken["commitments"][1]["lifecycle_status"] = "active"
    with pytest.raises(FullStateValidationError, match="lifecycle"):
        validate(event, broken)
    broken = copy.deepcopy(state)
    broken["commitments"][2]["supersession_links"] = []
    with pytest.raises(FullStateValidationError, match="lineage"):
        validate(event, broken)


def test_current_goal_success_requires_replacement_and_retained_progress() -> None:
    event, state = valid_pair()
    assert current_goal_success(
        state,
        {"cream_cheese_1": True, "alphabet_soup_1": True, "butter_1": False},
    )
    assert not current_goal_success(
        state,
        {"cream_cheese_1": False, "alphabet_soup_1": True, "butter_1": False},
    )
    assert not current_goal_success(
        state,
        {"cream_cheese_1": True, "alphabet_soup_1": False, "butter_1": True},
    )


def test_oracle_replacement_patch_uses_typed_override_and_preserves_progress() -> None:
    event, _ = valid_pair()
    receipt = apply_oracle_replacement_patch(
        event,
        physically_true_objects=("cream_cheese_1",),
    )
    assert receipt["method_label"] == "oracle_cope_patch_override"
    assert receipt["oracle_operation_selection"] is True
    assert receipt["provider_called"] is False
    assert receipt["patch"]["operation"] == "Override"
    assert receipt["transition"]["accepted"] is True
    before = {slot["slot_id"]: slot for slot in receipt["state_before"]["slots"]}
    after = {slot["slot_id"]: slot for slot in receipt["state_after"]["slots"]}
    assert before[goal_commitment_id("butter_1")]["mode"] == "active"
    assert after[goal_commitment_id("butter_1")]["mode"] == "overridden"
    assert after[goal_commitment_id("alphabet_soup_1")]["mode"] == "active"
    assert after[goal_commitment_id("cream_cheese_1")]["mode"] == "active"
