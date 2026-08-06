from __future__ import annotations

import copy

import pytest

from cope.relational_sequential_semantics import (
    DONE_ATOM,
    EVENT1_ATOM,
    ORIGINAL_PENDING_ATOM,
    RETARGET_ATOM,
    RelationalAtom,
    RelationalSemanticError,
    active_chain_tip,
    build_event,
    build_initial_state,
    execute_typed_transition,
    initialize_typed_state,
    oracle_sparse_proposal,
)


TRUTH = (DONE_ATOM.commitment_id,)


def initial(sequence_id: str = "unit"):
    logical = build_initial_state(sequence_id=sequence_id, world_version=10)
    typed = initialize_typed_state(sequence_id=sequence_id)
    return typed, logical


def apply_replace(typed, logical, replacement, step):
    event = build_event(
        logical,
        sequence_id="unit",
        step_index=step,
        event_type="replace_pending_goal",
        replacement_atom=replacement,
        world_version=10 + step,
    )
    return event, execute_typed_transition(
        typed,
        logical,
        event,
        oracle_sparse_proposal(event),
        physically_true_commitment_ids=TRUTH,
    )


def test_full_atom_identity_distinguishes_same_object_different_target():
    assert EVENT1_ATOM.object_name == RETARGET_ATOM.object_name
    assert EVENT1_ATOM.target_name != RETARGET_ATOM.target_name
    assert EVENT1_ATOM.commitment_id != RETARGET_ATOM.commitment_id


def test_two_overrides_preserve_history_and_compile_retarget():
    typed0, logical0 = initial()
    event1, (typed1, logical1, receipt1, directive1) = apply_replace(
        typed0, logical0, EVENT1_ATOM, 1
    )
    event2, (typed2, logical2, receipt2, directive2) = apply_replace(
        typed1, logical1, RETARGET_ATOM, 2
    )

    assert directive1.endswith("living_room_table_plate_right_region)")
    assert directive2 == (
        "place_on(red_coffee_mug_1, living_room_table_plate_left_region)"
    )
    rows = {row["id"]: row for row in logical2["commitments"]}
    assert rows[ORIGINAL_PENDING_ATOM.commitment_id]["lifecycle_status"] == "superseded"
    assert rows[ORIGINAL_PENDING_ATOM.commitment_id]["supersession_links"] == [
        EVENT1_ATOM.commitment_id
    ]
    assert rows[EVENT1_ATOM.commitment_id]["lifecycle_status"] == "superseded"
    assert rows[EVENT1_ATOM.commitment_id]["override_links"] == [
        ORIGINAL_PENDING_ATOM.commitment_id
    ]
    assert rows[EVENT1_ATOM.commitment_id]["supersession_links"] == [
        RETARGET_ATOM.commitment_id
    ]
    assert rows[RETARGET_ATOM.commitment_id]["lifecycle_status"] == "active"
    assert rows[RETARGET_ATOM.commitment_id]["override_links"] == [
        EVENT1_ATOM.commitment_id
    ]
    assert typed2.revision == 3
    assert receipt1["before_hash"] != receipt1["after_hash"]
    assert receipt2["before_hash"] == receipt1["after_hash"]
    assert event1["target_commitment_id"] == ORIGINAL_PENDING_ATOM.commitment_id
    assert event2["target_commitment_id"] == EVENT1_ATOM.commitment_id


def test_second_event_cancellation_compiles_halt_and_preserves_done():
    typed0, logical0 = initial()
    _, (typed1, logical1, _, _) = apply_replace(typed0, logical0, EVENT1_ATOM, 1)
    event2 = build_event(
        logical1,
        sequence_id="unit",
        step_index=2,
        event_type="cancel_pending_goal",
        replacement_atom=None,
        world_version=12,
    )
    _, logical2, _, directive = execute_typed_transition(
        typed1,
        logical1,
        event2,
        oracle_sparse_proposal(event2),
        physically_true_commitment_ids=TRUTH,
    )
    assert directive == "HALT"
    assert logical2["current_goal"] == {"all": [DONE_ATOM.to_predicate()]}
    done = {row["id"]: row for row in logical2["commitments"]}[DONE_ATOM.commitment_id]
    assert done["lifecycle_status"] == "satisfied"
    assert logical2["progress_ledger"][0]["milestone_id"] == DONE_ATOM.commitment_id


@pytest.mark.parametrize("field,value", [
    ("target_id", ORIGINAL_PENDING_ATOM.commitment_id),
    ("base_version", 1),
    ("replacement_id", ORIGINAL_PENDING_ATOM.commitment_id),
])
def test_wrong_chain_tip_stale_version_and_wrong_replacement_fail_closed(field, value):
    typed0, logical0 = initial()
    _, (typed1, logical1, _, _) = apply_replace(typed0, logical0, EVENT1_ATOM, 1)
    event2 = build_event(
        logical1,
        sequence_id="unit",
        step_index=2,
        event_type="replace_pending_goal",
        replacement_atom=RETARGET_ATOM,
        world_version=12,
    )
    proposal = oracle_sparse_proposal(event2)
    proposal[field] = value
    with pytest.raises(RelationalSemanticError):
        execute_typed_transition(
            typed1,
            logical1,
            event2,
            proposal,
            physically_true_commitment_ids=TRUTH,
        )


def test_replay_of_old_event_fails_closed():
    typed0, logical0 = initial()
    event1, (typed1, logical1, _, _) = apply_replace(typed0, logical0, EVENT1_ATOM, 1)
    with pytest.raises(RelationalSemanticError):
        execute_typed_transition(
            typed1,
            logical1,
            event1,
            oracle_sparse_proposal(event1),
            physically_true_commitment_ids=TRUTH,
        )


@pytest.mark.parametrize(
    "args",
    [
        ("inside", "red_coffee_mug_1", "living_room_table_plate_left_region"),
        ("on", "unknown_object", "living_room_table_plate_left_region"),
        ("on", "red_coffee_mug_1", "unknown_target"),
        ("on", "porcelain_mug_1", "living_room_table_plate_left_region"),
    ],
)
def test_unknown_or_unlicensed_atoms_fail_closed(args):
    with pytest.raises(RelationalSemanticError):
        RelationalAtom(*args)


def test_event_predicate_mismatch_and_physical_witness_mismatch_fail_closed():
    typed, logical = initial()
    event = build_event(
        logical,
        sequence_id="unit",
        step_index=1,
        event_type="replace_pending_goal",
        replacement_atom=EVENT1_ATOM,
        world_version=11,
    )
    bad_event = copy.deepcopy(event)
    bad_event["replacement_atom"]["predicate"] = "in"
    with pytest.raises(RelationalSemanticError):
        oracle_sparse_proposal(bad_event)
        execute_typed_transition(
            typed,
            logical,
            bad_event,
            oracle_sparse_proposal(bad_event),
            physically_true_commitment_ids=TRUTH,
        )
    with pytest.raises(RelationalSemanticError):
        execute_typed_transition(
            typed,
            logical,
            event,
            oracle_sparse_proposal(event),
            physically_true_commitment_ids=(),
        )


def test_active_chain_tip_uses_full_atom_not_object_only():
    typed0, logical0 = initial()
    _, (_, logical1, _, _) = apply_replace(typed0, logical0, EVENT1_ATOM, 1)
    assert active_chain_tip(logical1) == EVENT1_ATOM

