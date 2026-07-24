from __future__ import annotations

from dataclasses import replace

from cope import (
    ConstraintMode,
    ConstraintState,
    Insert,
    Override,
    PatchContext,
    Suspend,
    apply_patch,
    validate_state,
)
from cope.errors import (
    HASH_MISMATCH,
    HISTORY_REPLAY_MISMATCH,
    LINEAGE_CYCLE,
    OVERRIDE_CYCLE,
    PRIORITY_VIOLATION,
    SAFETY_OVERRIDE_FORBIDDEN,
    UNAUTHORIZED_SOURCE_MUTATION,
)

from conftest import apply_ok, make_patch, make_slot, rehash


def test_hash_integrity_detects_unhashed_state_change(root_state) -> None:
    slot = root_state.get_slot("alignment-1")
    tampered_slot = replace(slot, priority=slot.priority + 1)
    tampered = replace(root_state, slots=(tampered_slot,))
    report = validate_state(tampered)
    assert not report.valid
    assert HASH_MISMATCH in {error.code for error in report.errors}


def test_recomputed_hash_cannot_hide_mutation_outside_patch_history(root_state) -> None:
    slot = root_state.get_slot("alignment-1")
    tampered_slot = replace(slot, content={"object_id": "other", "relation": "aligned"})
    tampered = rehash(replace(root_state, slots=(tampered_slot,)))
    report = validate_state(tampered)
    assert not report.valid
    assert HISTORY_REPLAY_MISMATCH in {error.code for error in report.errors}


def test_lineage_cycle_detected_even_with_recomputed_hash(root_state) -> None:
    slot = root_state.get_slot("alignment-1")
    cyclic = replace(slot, parent_slot_id=slot.slot_id, lineage=(slot.slot_id, slot.slot_id))
    state = rehash(replace(root_state, slots=(cyclic,)))
    report = validate_state(state)
    assert LINEAGE_CYCLE in {error.code for error in report.errors}


def test_override_cycle_detected_even_with_recomputed_hash() -> None:
    initial = ConstraintState.empty("cycle-state")
    a = make_slot("a", "event-1", priority=60)
    state = apply_ok(initial, 1, [Insert("op-a", a)])
    b = make_slot("b", "event-2", priority=60)
    state = apply_ok(state, 2, [Insert("op-b", b)])
    a_bad = replace(state.get_slot("a"), overrides_slot_ids=("b",), mode=ConstraintMode.ACTIVE)
    b_bad = replace(state.get_slot("b"), overrides_slot_ids=("a",), mode=ConstraintMode.ACTIVE)
    corrupted = rehash(replace(state, slots=(a_bad, b_bad)))
    report = validate_state(corrupted)
    assert OVERRIDE_CYCLE in {error.code for error in report.errors}


def test_low_authority_cannot_suspend_high_priority_constraint(root_state) -> None:
    context = PatchContext(
        actor="low-priority-planner",
        authority_priority=10,
        authorized_sources=("task",),
    )
    result = apply_patch(
        root_state,
        make_patch(root_state, 2, [Suspend("op-suspend", "alignment-1", "unauthorized")]),
        context,
    )
    assert not result.accepted
    assert result.rejection_code == PRIORITY_VIOLATION


def test_successful_patch_revision_is_strictly_monotonic(root_state) -> None:
    state = apply_ok(root_state, 2, [Suspend("op-suspend", "alignment-1", "temporary")])
    assert state.revision == root_state.revision + 1
    assert state.event_history[-1].revision == state.revision


def test_lower_priority_replacement_cannot_override_target(root_state) -> None:
    target = root_state.get_slot("alignment-1")
    replacement = make_slot(
        "weak-replacement",
        "event-2",
        priority=target.priority - 1,
        parent=target,
        overrides=(target.slot_id,),
    )
    result = apply_patch(
        root_state,
        make_patch(
            root_state,
            2,
            [Override("op-weak-override", target.slot_id, replacement, "too weak")],
        ),
        PatchContext.trusted(),
    )
    assert not result.accepted
    assert result.rejection_code == PRIORITY_VIOLATION


def test_safety_slot_requires_explicit_safety_override_permission() -> None:
    state = ConstraintState.empty("safety-auth")
    safety = make_slot("safety-stop", "event-1", source="safety", priority=100)
    state = apply_ok(state, 1, [Insert("op-safety", safety)])
    context = PatchContext(
        actor="planner",
        authority_priority=1000,
        authorized_sources=("safety",),
        allow_safety_override=False,
    )
    result = apply_patch(
        state,
        make_patch(state, 2, [Suspend("op-suspend-safety", safety.slot_id, "not authorized")]),
        context,
    )
    assert not result.accepted
    assert result.rejection_code == SAFETY_OVERRIDE_FORBIDDEN


def test_actor_cannot_insert_a_source_it_is_not_authorized_to_assert() -> None:
    state = ConstraintState.empty("insert-auth")
    forged_user = make_slot("forged-user", "event-1", source="user", priority=20)
    context = PatchContext(
        actor="planner",
        authority_priority=100,
        authorized_sources=("planner",),
    )
    result = apply_patch(
        state,
        make_patch(state, 1, [Insert("op-forged-user", forged_user)]),
        context,
    )
    assert not result.accepted
    assert result.rejection_code == UNAUTHORIZED_SOURCE_MUTATION
