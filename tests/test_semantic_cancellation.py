from __future__ import annotations

import copy

import pytest

from cope.semantic_cancellation import (
    build_cancellation_event,
    build_oracle_cancellation_state,
    cancellation_compliance,
    compile_execution_directive,
    validate_oracle_cancellation_state,
)
from cope.semantic_replacement import (
    FullStateValidationError,
    MilestoneEvent,
    goal_commitment_id,
)


def valid_pair():
    event = build_cancellation_event(
        MilestoneEvent(
            policy_step=135,
            done_object="cream_cheese_1",
            pending_object="butter_1",
            stable_steps=5,
        ),
        pair_key="pair",
    )
    return event, build_oracle_cancellation_state(event)


def validate(event, state, *, true_objects=("cream_cheese_1",)) -> None:
    validate_oracle_cancellation_state(
        state,
        event,
        previous_state_version=0,
        physically_true_objects=true_objects,
    )


def test_valid_cancellation_satisfies_progress_and_compiles_to_halt() -> None:
    event, state = valid_pair()
    validate(event, state)
    assert state["plan"] == []
    assert compile_execution_directive(state) == "HALT"
    assert cancellation_compliance(
        event,
        {"cream_cheese_1": True, "butter_1": False},
    )


def test_stale_state_wrong_authority_and_wrong_target_are_rejected() -> None:
    event, state = valid_pair()
    broken = copy.deepcopy(state)
    broken["state_version"] = 0
    with pytest.raises(FullStateValidationError, match="stale"):
        validate(event, broken)
    broken_event = copy.deepcopy(event)
    broken_event["authority"] = 1
    with pytest.raises(FullStateValidationError, match="authorized"):
        validate(broken_event, state)
    broken_event = copy.deepcopy(event)
    broken_event["target_commitment_id"] = goal_commitment_id("cream_cheese_1")
    with pytest.raises(FullStateValidationError, match="wrong commitment"):
        validate(broken_event, state)


def test_false_progress_and_already_completed_pending_goal_are_rejected() -> None:
    event, state = valid_pair()
    with pytest.raises(FullStateValidationError, match="not physically true"):
        validate(event, state, true_objects=())
    with pytest.raises(FullStateValidationError, match="already physically satisfied"):
        validate(event, state, true_objects=("cream_cheese_1", "butter_1"))


def test_cancelled_commitment_cannot_remain_active_or_in_plan() -> None:
    event, state = valid_pair()
    broken = copy.deepcopy(state)
    broken["commitments"][1]["lifecycle_status"] = "active"
    with pytest.raises(FullStateValidationError, match="lifecycle"):
        validate(event, broken)
    broken = copy.deepcopy(state)
    broken["plan"] = [{"step_id": "stale-butter-action"}]
    with pytest.raises(FullStateValidationError, match="HALT"):
        validate(event, broken)


def test_cancellation_compliance_detects_stale_execution_and_progress_loss() -> None:
    event, _ = valid_pair()
    assert not cancellation_compliance(
        event,
        {"cream_cheese_1": True, "butter_1": True},
    )
    assert not cancellation_compliance(
        event,
        {"cream_cheese_1": False, "butter_1": False},
    )
