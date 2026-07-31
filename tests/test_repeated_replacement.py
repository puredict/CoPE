from __future__ import annotations

import pytest

from cope.repeated_replacement import (
    apply_oracle_replacement_chain,
    build_chained_replacement_event,
)
from cope.semantic_replacement import FullStateValidationError, goal_commitment_id


def events():
    first = build_chained_replacement_event(
        pair_key="pair",
        step_index=1,
        source_object="butter_1",
        replacement_object="alphabet_soup_1",
        expected_state_revision=1,
        world_version=100,
    )
    second = build_chained_replacement_event(
        pair_key="pair",
        step_index=2,
        source_object="alphabet_soup_1",
        replacement_object="tomato_sauce_1",
        expected_state_revision=2,
        world_version=101,
    )
    return first, second


def apply_chain(raw_events):
    return apply_oracle_replacement_chain(
        raw_events,
        done_object="cream_cheese_1",
        initial_pending_object="butter_1",
        physically_true_objects=("cream_cheese_1",),
        pair_key="pair",
    )


def test_two_overrides_accumulate_revision_hash_and_lineage():
    result = apply_chain(events())
    assert result["final_active_object"] == "tomato_sauce_1"
    assert result["provider_called"] is False
    assert len(result["receipts"]) == 2
    first, second = result["receipts"]
    assert first["transition"]["revision_before"] == 1
    assert first["transition"]["revision_after"] == 2
    assert second["transition"]["revision_before"] == 2
    assert second["transition"]["revision_after"] == 3
    assert first["transition"]["after_hash"] == second["transition"]["before_hash"]

    slots = {slot["slot_id"]: slot for slot in result["final_state"]["slots"]}
    butter = goal_commitment_id("butter_1")
    soup = goal_commitment_id("alphabet_soup_1")
    tomato = goal_commitment_id("tomato_sauce_1")
    cream = goal_commitment_id("cream_cheese_1")
    assert slots[butter]["mode"] == "overridden"
    assert slots[soup]["mode"] == "overridden"
    assert slots[tomato]["mode"] == "active"
    assert slots[cream]["mode"] == "active"
    assert slots[tomato]["lineage"] == [butter, soup, tomato]


def test_stale_second_event_revision_is_rejected():
    first, second = events()
    second["expected_state_revision"] = 1
    with pytest.raises(FullStateValidationError, match="revision"):
        apply_chain((first, second))


def test_second_event_must_target_active_chain_tip():
    first, second = events()
    second["source_object"] = "butter_1"
    second["target_commitment_id"] = goal_commitment_id("butter_1")
    with pytest.raises(FullStateValidationError, match="chain tip"):
        apply_chain((first, second))


def test_replacement_cannot_reuse_earlier_chain_object():
    first, second = events()
    second["replacement_object"] = "butter_1"
    with pytest.raises(FullStateValidationError, match="reuses"):
        apply_chain((first, second))


def test_completed_progress_must_be_physically_true():
    first, _ = events()
    with pytest.raises(FullStateValidationError, match="physically true"):
        apply_oracle_replacement_chain(
            (first,),
            done_object="cream_cheese_1",
            initial_pending_object="butter_1",
            physically_true_objects=(),
            pair_key="pair",
        )
