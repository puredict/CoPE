from __future__ import annotations

import copy

import pytest

from cope.governed_delta import (
    GovernedDeltaError,
    governed_oracle_proposal,
    materialize_governed_delta,
)
from cope.sequential_semantics import (
    build_expected_next_state,
    build_initial_sequence_state,
    build_sequence_event,
)
from cope.types import canonical_json


def fixture():
    initial = build_initial_sequence_state(
        sequence_id="governed-unit",
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
    event = build_sequence_event(
        initial,
        sequence_id="governed-unit",
        step_index=1,
        done_object="alphabet_soup_1",
        event_type="replace_pending_goal",
        replacement_object="cream_cheese_1",
        world_version=11,
    )
    expected = build_expected_next_state(initial, event)
    return initial, event, expected


def test_governed_delta_materializes_oracle_state_without_cope_patch_fields():
    initial, event, expected = fixture()
    proposal = governed_oracle_proposal(initial, expected, event)
    assert not (set(proposal) & {"operation", "patch_id", "receipt", "hash"})
    serialized = canonical_json(proposal)
    assert "Override" not in serialized and "Expire" not in serialized
    candidate, receipt, directive = materialize_governed_delta(
        proposal, initial, event, ("alphabet_soup_1",)
    )
    assert candidate == expected
    assert receipt["read_revision"] == 1
    assert receipt["published_revision"] == 2
    assert receipt["common_validator_calls"] == 1
    assert directive == "place_in(cream_cheese_1, basket_1_contain_region)"


@pytest.mark.parametrize(
    "fault,match",
    [
        ("stale", "stale"),
        ("event", "event"),
        ("scope", "scope"),
        ("mutate_done", "shared verifier"),
        ("omit_changed", "scope"),
    ],
)
def test_governed_delta_rejects_faults_without_mutating_caller(fault, match):
    initial, event, expected = fixture()
    proposal = governed_oracle_proposal(initial, expected, event)
    before = copy.deepcopy(initial)
    if fault == "stale":
        proposal["read_revision"] = 0
    elif fault == "event":
        proposal["event_id"] = "wrong-event"
    elif fault == "scope":
        proposal["affected_scope"].append("goal:alphabet_soup_1")
    elif fault == "mutate_done":
        done = next(
            row for row in expected["commitments"]
            if row["grounding"][0] == "alphabet_soup_1"
        )
        proposal["affected_scope"].append(done["id"])
        proposal["forest_delta"].append(
            {"node_id": done["id"], "after": {**done, "lifecycle_status": "active"}}
        )
    else:
        proposal["forest_delta"] = proposal["forest_delta"][:-1]
    with pytest.raises(GovernedDeltaError, match=match):
        materialize_governed_delta(
            proposal, initial, event, ("alphabet_soup_1",)
        )
    assert initial == before


def test_governed_delta_second_event_consumes_first_published_state():
    initial, event1, middle = fixture()
    first, receipt1, _ = materialize_governed_delta(
        governed_oracle_proposal(initial, middle, event1),
        initial,
        event1,
        ("alphabet_soup_1",),
    )
    event2 = build_sequence_event(
        first,
        sequence_id="governed-unit",
        step_index=2,
        done_object="alphabet_soup_1",
        event_type="cancel_pending_goal",
        replacement_object=None,
        world_version=12,
    )
    expected = build_expected_next_state(first, event2)
    final, receipt2, directive = materialize_governed_delta(
        governed_oracle_proposal(first, expected, event2),
        first,
        event2,
        ("alphabet_soup_1",),
    )
    assert receipt1["after_hash"] == receipt2["before_hash"]
    assert final["state_version"] == 3
    assert directive == "HALT"
