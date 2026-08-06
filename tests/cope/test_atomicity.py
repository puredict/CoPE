from __future__ import annotations

from cope import Insert, PatchContext, Suspend, apply_patch, serialize_state
from cope.errors import SLOT_NOT_FOUND

from conftest import make_patch, make_slot


def test_patch_rolls_back_when_middle_operation_fails(root_state) -> None:
    before_payload = serialize_state(root_state)
    inserted = make_slot("temporary", "event-2")
    patch = make_patch(
        root_state,
        2,
        [
            Insert("op-first-valid", inserted),
            Suspend("op-middle-invalid", "missing-slot", "must fail"),
            Suspend("op-never-reached", "alignment-1", "not reached"),
        ],
    )
    result = apply_patch(root_state, patch, PatchContext.trusted())
    assert not result.accepted
    assert result.rejection_code == SLOT_NOT_FOUND
    assert result.applied_operation_ids == ()
    assert result.before_hash == result.after_hash == root_state.state_hash
    assert serialize_state(result.state) == before_payload
    assert all(slot.slot_id != "temporary" for slot in result.state.slots)


def test_rejected_patch_does_not_advance_revision(root_state) -> None:
    patch = make_patch(root_state, 2, [Suspend("op-invalid", "missing", "invalid")])
    result = apply_patch(root_state, patch, PatchContext.trusted())
    assert not result.accepted
    assert result.state.revision == root_state.revision
    assert result.state.patch_history == root_state.patch_history
    assert result.state.event_history == root_state.event_history
