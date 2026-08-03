from __future__ import annotations

import copy

import pytest

from cope.sequential_semantics import (
    SequentialSemanticError,
    build_expected_next_state,
    build_initial_sequence_state,
    build_sequence_event,
    fsr_oracle_proposal,
    full_replan_oracle_proposal,
    materialize_fsr_proposal,
    materialize_full_replan_proposal,
    validate_sequence_transition,
)
from cope.semantic_replacement import goal_commitment_id


def fixture():
    initial = build_initial_sequence_state(
        sequence_id="unit",
        done_object="alphabet_soup_1",
        pending_object="tomato_sauce_1",
        available_objects=(
            "alphabet_soup_1",
            "tomato_sauce_1",
            "cream_cheese_1",
            "butter_1",
        ),
        world_version=10,
    )
    first = build_sequence_event(
        initial,
        sequence_id="unit",
        step_index=1,
        done_object="alphabet_soup_1",
        event_type="replace_pending_goal",
        replacement_object="cream_cheese_1",
        world_version=11,
    )
    middle = build_expected_next_state(initial, first)
    second = build_sequence_event(
        middle,
        sequence_id="unit",
        step_index=2,
        done_object="alphabet_soup_1",
        event_type="replace_pending_goal",
        replacement_object="butter_1",
        world_version=12,
    )
    return initial, first, middle, second


def test_second_event_consumes_first_committed_state_and_preserves_history():
    initial, first, middle, second = fixture()
    final = build_expected_next_state(middle, second)
    assert [initial["state_version"], middle["state_version"], final["state_version"]] == [1, 2, 3]
    by_id = {row["id"]: row["lifecycle_status"] for row in final["commitments"]}
    assert by_id == {
        goal_commitment_id("alphabet_soup_1"): "satisfied",
        goal_commitment_id("tomato_sauce_1"): "superseded",
        goal_commitment_id("cream_cheese_1"): "superseded",
        goal_commitment_id("butter_1"): "active",
    }
    assert validate_sequence_transition(
        middle, final, second, ("alphabet_soup_1",)
    ) == "place_in(butter_1, basket_1_contain_region)"


def test_replace_then_cancel_preserves_tombstones_and_halts():
    initial, first, middle, _ = fixture()
    second = build_sequence_event(
        middle,
        sequence_id="cancel",
        step_index=2,
        done_object="alphabet_soup_1",
        event_type="cancel_pending_goal",
        replacement_object=None,
        world_version=12,
    )
    final = build_expected_next_state(middle, second)
    statuses = {row["id"]: row["lifecycle_status"] for row in final["commitments"]}
    assert statuses[goal_commitment_id("tomato_sauce_1")] == "superseded"
    assert statuses[goal_commitment_id("cream_cheese_1")] == "cancelled"
    assert validate_sequence_transition(
        middle, final, second, ("alphabet_soup_1",)
    ) == "HALT"


def test_stale_second_event_is_rejected():
    _, _, middle, second = fixture()
    second["valid_from_state_version"] = 1
    with pytest.raises(SequentialSemanticError, match="stale"):
        build_expected_next_state(middle, second)


def test_second_event_cannot_retarget_inactive_first_source():
    _, _, middle, second = fixture()
    second["pending_object"] = "tomato_sauce_1"
    second["target_commitment_id"] = "goal:tomato_sauce_1"
    with pytest.raises(SequentialSemanticError, match="active chain tip"):
        build_expected_next_state(middle, second)


@pytest.mark.parametrize("fault", ["drop_done", "reactivate_old", "drop_history"])
def test_transition_validator_rejects_history_and_progress_faults(fault):
    _, _, middle, second = fixture()
    final = build_expected_next_state(middle, second)
    done_id = goal_commitment_id("alphabet_soup_1")
    old_id = goal_commitment_id("tomato_sauce_1")
    if fault == "drop_done":
        final["commitments"] = [
            row for row in final["commitments"] if row["id"] != done_id
        ]
    elif fault == "reactivate_old":
        next(row for row in final["commitments"] if row["id"] == old_id)["lifecycle_status"] = "active"
    else:
        final["commitments"] = [
            row for row in final["commitments"] if row["id"] != old_id
        ]
    with pytest.raises(SequentialSemanticError, match="canonical incremental"):
        validate_sequence_transition(middle, final, second, ("alphabet_soup_1",))


def test_fsr_and_full_replan_materialize_same_incremental_state():
    _, _, middle, second = fixture()
    expected = build_expected_next_state(middle, second)
    fsr, fsr_directive = materialize_fsr_proposal(
        fsr_oracle_proposal(expected), middle, second, ("alphabet_soup_1",)
    )
    replan, replan_directive = materialize_full_replan_proposal(
        full_replan_oracle_proposal(expected, second),
        middle,
        second,
        ("alphabet_soup_1",),
    )
    assert fsr == replan == expected
    assert fsr_directive == replan_directive


def test_fsr_cannot_omit_historical_commitment():
    _, _, middle, second = fixture()
    expected = build_expected_next_state(middle, second)
    proposal = fsr_oracle_proposal(expected)
    proposal["commitments"] = proposal["commitments"][1:]
    with pytest.raises(SequentialSemanticError, match="canonical incremental"):
        materialize_fsr_proposal(
            proposal, middle, second, ("alphabet_soup_1",)
        )


def test_full_replan_cannot_change_completed_fact():
    _, _, middle, second = fixture()
    expected = build_expected_next_state(middle, second)
    proposal = full_replan_oracle_proposal(expected, second)
    proposal["completed_facts"] = []
    with pytest.raises(SequentialSemanticError, match="canonical remaining task"):
        materialize_full_replan_proposal(
            proposal, middle, second, ("alphabet_soup_1",)
        )
