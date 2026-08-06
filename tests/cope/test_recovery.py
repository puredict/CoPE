from __future__ import annotations

from cope import (
    ConstraintMode,
    ConstraintState,
    Expire,
    Insert,
    Override,
    PatchContext,
    Restore,
    Suspend,
    apply_patch,
    revalidate_slot,
)
from cope.errors import (
    BLIND_RESTORE,
    CONFLICTING_OVERRIDE,
    EXPIRED_RESTORE,
    VALIDATION_FAILED,
    VALIDATION_NOT_FOUND,
    VALIDATION_STALE,
    VALIDATOR_ERROR,
)

from conftest import apply_ok, make_patch, make_slot


def _present(slot, evidence) -> bool:
    return evidence["object_id"] == slot.content["object_id"] and evidence["pose_unchanged"] is True


def test_successful_revalidate_and_restore_keeps_slot_id(root_state) -> None:
    suspended = apply_ok(root_state, 2, [Suspend("op-suspend", "alignment-1", "hand left")])
    guarded = revalidate_slot(
        suspended,
        "alignment-1",
        {"object_id": "cup-1", "pose_unchanged": True, "frame": "obs-7"},
        _present,
    )
    assert guarded.success
    revalidated = apply_ok(suspended, 3, [guarded.operation])
    restored = apply_ok(
        revalidated,
        4,
        [Restore("op-restore", "alignment-1", guarded.validation_id, "guard passed")],
    )
    slot = restored.get_slot("alignment-1")
    assert slot.mode is ConstraintMode.ACTIVE
    assert slot.slot_id == "alignment-1"
    assert guarded.validation_id in slot.evidence_refs
    assert restored.validation_history[-1].validator_id == "_present"


def test_blind_restore_is_rejected(root_state) -> None:
    suspended = apply_ok(root_state, 2, [Suspend("op-suspend", "alignment-1", "uncertain")])
    patch = make_patch(
        suspended,
        3,
        [Restore("op-restore", "alignment-1", "val-does-not-exist", "blind")],
    )
    result = apply_patch(suspended, patch, PatchContext.trusted())
    assert not result.accepted
    assert result.rejection_code == VALIDATION_NOT_FOUND
    assert result.before_hash == result.after_hash


def test_failed_guard_is_recorded_but_cannot_restore(root_state) -> None:
    suspended = apply_ok(root_state, 2, [Suspend("op-suspend", "alignment-1", "uncertain")])
    guarded = revalidate_slot(
        suspended,
        "alignment-1",
        {"object_id": "cup-1", "pose_unchanged": False},
        _present,
    )
    assert not guarded.success
    assert guarded.error_code == VALIDATION_FAILED
    checked = apply_ok(suspended, 3, [guarded.operation])
    result = apply_patch(
        checked,
        make_patch(checked, 4, [Restore("op-restore", "alignment-1", guarded.validation_id, "unsafe")]),
        PatchContext.trusted(),
    )
    assert not result.accepted
    assert result.rejection_code == VALIDATION_FAILED


def test_validator_exception_becomes_explicit_failed_result(root_state) -> None:
    suspended = apply_ok(root_state, 2, [Suspend("op-suspend", "alignment-1", "uncertain")])

    def broken(slot, evidence):
        raise RuntimeError("camera unavailable")

    result = revalidate_slot(suspended, "alignment-1", {"frame": "missing"}, broken)
    assert not result.success
    assert result.error_code == VALIDATOR_ERROR
    assert "RuntimeError" in result.error_message


def test_expired_slot_cannot_be_revalidated_or_restored(root_state) -> None:
    expired = apply_ok(root_state, 2, [Expire("op-expire", "alignment-1", "cup moved")])
    try:
        revalidate_slot(expired, "alignment-1", {"pose_unchanged": True}, _present)
    except Exception as exc:
        assert getattr(exc, "code", None) == EXPIRED_RESTORE
    else:
        raise AssertionError("expired slot was revalidated")
    result = apply_patch(
        expired,
        make_patch(expired, 3, [Restore("op-restore", "alignment-1", "val-any", "illegal")]),
        PatchContext.trusted(),
    )
    assert not result.accepted
    assert result.rejection_code == EXPIRED_RESTORE


def test_successful_validation_becomes_stale_after_later_slot_update(root_state) -> None:
    state = apply_ok(root_state, 2, [Suspend("op-suspend-1", "alignment-1", "temporary")])
    guarded = revalidate_slot(
        state,
        "alignment-1",
        {"object_id": "cup-1", "pose_unchanged": True},
        _present,
    )
    state = apply_ok(state, 3, [guarded.operation])
    state = apply_ok(
        state,
        4,
        [Restore("op-restore-1", "alignment-1", guarded.validation_id, "first restore")],
    )
    state = apply_ok(state, 5, [Suspend("op-suspend-2", "alignment-1", "new interruption")])
    result = apply_patch(
        state,
        make_patch(
            state,
            6,
            [Restore("op-restore-2", "alignment-1", guarded.validation_id, "stale restore")],
        ),
        PatchContext.trusted(),
    )
    assert not result.accepted
    assert result.rejection_code == VALIDATION_STALE


def test_validation_for_one_slot_cannot_restore_another() -> None:
    state = ConstraintState.empty("cross-slot")
    first = make_slot("first", "event-1")
    second = make_slot("second", "event-1")
    state = apply_ok(state, 1, [Insert("op-first", first), Insert("op-second", second)])
    state = apply_ok(
        state,
        2,
        [
            Suspend("op-suspend-first", "first", "temporary"),
            Suspend("op-suspend-second", "second", "temporary"),
        ],
    )
    guarded = revalidate_slot(
        state,
        "first",
        {"object_id": "cup-1", "pose_unchanged": True},
        _present,
    )
    state = apply_ok(state, 3, [guarded.operation])
    result = apply_patch(
        state,
        make_patch(
            state,
            4,
            [Restore("op-wrong-slot", "second", guarded.validation_id, "wrong slot")],
        ),
        PatchContext.trusted(),
    )
    assert not result.accepted
    assert result.rejection_code == BLIND_RESTORE


def test_overridden_slot_cannot_restore_while_replacement_is_active(root_state) -> None:
    old = root_state.get_slot("alignment-1")
    replacement = make_slot(
        "alignment-2",
        "event-2",
        priority=60,
        parent=old,
        overrides=(old.slot_id,),
    )
    state = apply_ok(
        root_state,
        2,
        [Override("op-override", old.slot_id, replacement, "new observation")],
    )
    guarded = revalidate_slot(
        state,
        old.slot_id,
        {"object_id": "cup-1", "pose_unchanged": True},
        _present,
    )
    state = apply_ok(state, 3, [guarded.operation])
    result = apply_patch(
        state,
        make_patch(
            state,
            4,
            [Restore("op-conflict", old.slot_id, guarded.validation_id, "conflicts")],
        ),
        PatchContext.trusted(),
    )
    assert not result.accepted
    assert result.rejection_code == CONFLICTING_OVERRIDE
