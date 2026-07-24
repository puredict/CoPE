from __future__ import annotations

import pytest

from cope import (
    ConstraintMode,
    ConstraintState,
    Expire,
    Insert,
    PatchContext,
    Restore,
    Suspend,
    TransitionError,
    apply_patch,
    revalidate_slot,
    validate_state,
)
from cope.errors import EXPIRED_RESTORE

from conftest import apply_ok, make_patch, make_slot


def test_golden_hand_leaves_but_cup_does_not_move() -> None:
    state = ConstraintState.empty("golden-static-cup")
    alignment = make_slot(
        "cup-alignment-v1",
        "event-1",
        content={"object_id": "cup-1", "pose": [0.1, 0.2, 0.0], "aligned_for": "grasp"},
    )
    state = apply_ok(state, 1, [Insert("op-insert", alignment)])
    state = apply_ok(state, 2, [Suspend("op-suspend", alignment.slot_id, "hand temporarily absent")])

    def same_pose(slot, evidence):
        return evidence["object_id"] == slot.content["object_id"] and evidence["pose"] == slot.content["pose"]

    checked = revalidate_slot(
        state,
        alignment.slot_id,
        {"object_id": "cup-1", "pose": [0.1, 0.2, 0.0], "observation_id": "frame-12"},
        same_pose,
    )
    assert checked.success
    state = apply_ok(state, 3, [checked.operation])
    state = apply_ok(
        state,
        4,
        [Restore("op-restore", alignment.slot_id, checked.validation_id, "cup pose unchanged")],
    )
    restored = state.get_slot(alignment.slot_id)
    assert restored.mode is ConstraintMode.ACTIVE
    assert restored.slot_id == alignment.slot_id
    assert validate_state(state).valid


def test_golden_moved_cup_expires_old_alignment_and_inserts_lineage_successor() -> None:
    state = ConstraintState.empty("golden-moved-cup")
    old = make_slot(
        "cup-alignment-v1",
        "event-1",
        content={"object_id": "cup-1", "pose": [0.1, 0.2, 0.0], "aligned_for": "grasp"},
    )
    state = apply_ok(state, 1, [Insert("op-insert-old", old)])
    new = make_slot(
        "cup-alignment-v2",
        "event-2",
        content={"object_id": "cup-1", "pose": [0.4, -0.1, 0.0], "aligned_for": "grasp"},
        parent=old,
    )
    state = apply_ok(
        state,
        2,
        [
            Expire("op-expire-old", old.slot_id, "cup moved"),
            Insert("op-insert-new", new),
        ],
    )
    assert state.get_slot(old.slot_id).mode is ConstraintMode.EXPIRED
    assert state.get_slot(new.slot_id).mode is ConstraintMode.ACTIVE
    assert state.get_slot(new.slot_id).lineage == (old.slot_id, new.slot_id)
    result = apply_patch(
        state,
        make_patch(
            state,
            3,
            [Restore("op-illegal-restore", old.slot_id, "val-impossible", "must fail")],
        ),
        PatchContext.trusted(),
    )
    assert not result.accepted
    assert result.rejection_code == EXPIRED_RESTORE


def test_golden_missing_cup_expires_every_dependent_constraint_and_escalates() -> None:
    state = ConstraintState.empty("golden-missing-cup")
    slots = [
        make_slot(
            "cup-exists",
            "event-1",
            constraint_type="object_existence",
            content={"object_id": "cup-1", "exists": True},
            source="perception",
            priority=70,
        ),
        make_slot(
            "cup-alignment",
            "event-1",
            content={"object_id": "cup-1", "depends_on_object_id": "cup-1", "aligned_for": "grasp"},
        ),
        make_slot(
            "cup-grasp-plan",
            "event-1",
            constraint_type="action_precondition",
            content={"action": "grasp", "depends_on_object_id": "cup-1"},
            source="planner",
            priority=40,
        ),
    ]
    state = apply_ok(
        state,
        1,
        [Insert(f"op-insert-{index}", slot) for index, slot in enumerate(slots)],
    )
    escalation = make_slot(
        "missing-cup-escalation",
        "event-2",
        constraint_type="escalation",
        content={"object_id": "cup-1", "decision": "stop_and_request_world_update"},
        source="safety",
        priority=100,
    )
    state = apply_ok(
        state,
        2,
        [
            Expire("op-expire-exists", "cup-exists", "cup absent"),
            Expire("op-expire-alignment", "cup-alignment", "dependency absent"),
            Expire("op-expire-plan", "cup-grasp-plan", "dependency absent"),
            Insert("op-escalate", escalation),
        ],
    )
    for slot_id in ("cup-exists", "cup-alignment", "cup-grasp-plan"):
        assert state.get_slot(slot_id).mode is ConstraintMode.EXPIRED
    assert state.get_slot("missing-cup-escalation").mode is ConstraintMode.ACTIVE
    assert all(
        not (
            slot.mode is ConstraintMode.ACTIVE
            and slot.content.get("object_id") == "cup-1"
            and slot.content.get("exists") is True
        )
        for slot in state.slots
    )
    with pytest.raises(TransitionError) as caught:
        revalidate_slot(
            state,
            "cup-exists",
            {"object_id": "cup-1", "exists": True},
            lambda slot, evidence: True,
        )
    assert caught.value.code == EXPIRED_RESTORE
