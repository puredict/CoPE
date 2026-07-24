from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from cope import (
    ConstraintMode,
    ConstraintSlot,
    ConstraintState,
    Demote,
    Expire,
    Insert,
    Override,
    PatchContext,
    Suspend,
    apply_patch,
    validate_state,
)

from conftest import apply_ok, make_patch, make_slot


def test_insert_preserves_typed_identity_source_priority_and_lineage() -> None:
    state = ConstraintState.empty("operations")
    slot = make_slot(
        "preference-1",
        "event-1",
        constraint_type="user_preference",
        content={"object_id": "cup-1", "preferred_grasp": "handle"},
        source="user",
        priority=80,
    )
    result = apply_patch(
        state,
        make_patch(state, 1, [Insert("op-1", slot)]),
        PatchContext.trusted("test"),
    )
    assert result.accepted
    inserted = result.state.get_slot("preference-1")
    assert inserted.source.value == "user"
    assert inserted.priority == 80
    assert inserted.lineage == ("preference-1",)
    assert result.state.revision == 1
    assert validate_state(result.state).valid


def test_suspend_keeps_identity_and_appends_history(root_state) -> None:
    before = root_state
    state = apply_ok(before, 2, [Suspend("op-suspend", "alignment-1", "hand absent")])
    slot = state.get_slot("alignment-1")
    assert slot.slot_id == before.get_slot("alignment-1").slot_id
    assert slot.mode is ConstraintMode.SUSPENDED
    assert state.event_history[:1] == before.event_history
    assert state.patch_history[:1] == before.patch_history
    assert state.revision == before.revision + 1


def test_override_preserves_old_slot_and_creates_auditable_edge(root_state) -> None:
    old = root_state.get_slot("alignment-1")
    replacement = make_slot(
        "alignment-2",
        "event-2",
        priority=60,
        parent=old,
        overrides=("alignment-1",),
        content={"object_id": "cup-1", "relation": "aligned", "pose": [0.2, 0.1, 0.0]},
    )
    state = apply_ok(
        root_state,
        2,
        [Override("op-override", "alignment-1", replacement, "fresh perception")],
    )
    assert state.get_slot("alignment-1").mode is ConstraintMode.OVERRIDDEN
    assert state.get_slot("alignment-2").overrides_slot_ids == ("alignment-1",)
    assert state.get_slot("alignment-2").lineage == ("alignment-1", "alignment-2")
    assert validate_state(state).valid


def test_demote_retains_constraint_with_lower_priority(root_state) -> None:
    state = apply_ok(root_state, 2, [Demote("op-demote", "alignment-1", 30, "weaker evidence")])
    slot = state.get_slot("alignment-1")
    assert slot.mode is ConstraintMode.DEMOTED
    assert slot.priority == 30
    assert slot.content["object_id"] == "cup-1"


def test_expire_is_a_tombstone_not_deletion(root_state) -> None:
    state = apply_ok(root_state, 2, [Expire("op-expire", "alignment-1", "cup moved")])
    slot = state.get_slot("alignment-1")
    assert slot.mode is ConstraintMode.EXPIRED
    assert len(state.slots) == len(root_state.slots)
    assert slot.created_event_id == root_state.get_slot("alignment-1").created_event_id


def test_state_and_nested_content_are_immutable(root_state) -> None:
    slot = root_state.get_slot("alignment-1")
    with pytest.raises(FrozenInstanceError):
        slot.priority = 1  # type: ignore[misc]
    with pytest.raises(TypeError):
        slot.content["object_id"] = "other"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        root_state.slots = ()  # type: ignore[misc]


def test_user_source_survives_planner_override(root_state) -> None:
    state = ConstraintState.empty("source-preservation")
    user = make_slot("preference", "event-1", source="user", priority=80)
    state = apply_ok(state, 1, [Insert("op-user", user)])
    replacement = make_slot(
        "safe-preference",
        "event-2",
        source="safety",
        priority=100,
        parent=user,
        overrides=("preference",),
    )
    state = apply_ok(state, 2, [Override("op-safe", "preference", replacement, "safety conflict")])
    assert state.get_slot("preference").source.value == "user"
    assert state.get_slot("preference").mode is ConstraintMode.OVERRIDDEN
    assert state.get_slot("safe-preference").source.value == "safety"
