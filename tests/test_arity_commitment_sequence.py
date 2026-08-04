from __future__ import annotations

import copy

import pytest

from cope.arity_commitment_sequence import (
    ArityCommitmentError,
    CommitmentAtom,
    DONE_ATOM,
    PENDING_ATOM,
    REPLACEMENT_ATOM,
    active_tip,
    build_event,
    build_initial_state,
    execute_transition,
    initialize_typed_state,
    oracle_proposal,
)


TRUTH = (DONE_ATOM.commitment_id,)


def initial(sequence_id="unit"):
    return (
        initialize_typed_state(sequence_id=sequence_id),
        build_initial_state(sequence_id=sequence_id, world_version=100),
    )


def test_stable_ids_encode_predicate_and_exact_arity():
    assert PENDING_ATOM.commitment_id == "goal:close:microwave_1"
    assert DONE_ATOM.commitment_id == (
        "goal:in:white_yellow_mug_1:microwave_1_heating_region"
    )
    assert PENDING_ATOM.commitment_id != REPLACEMENT_ATOM.commitment_id


def test_cross_predicate_override_then_cancel_preserves_done_and_lineage():
    typed0, logical0 = initial()
    event1 = build_event(
        logical0, sequence_id="unit", step_index=1,
        event_type="replace_pending_goal", replacement_atom=REPLACEMENT_ATOM,
        world_version=101,
    )
    typed1, logical1, receipt1, directive1 = execute_transition(
        typed0, logical0, event1, oracle_proposal(event1), physically_true_ids=TRUTH
    )
    event2 = build_event(
        logical1, sequence_id="unit", step_index=2,
        event_type="cancel_pending_goal", replacement_atom=None, world_version=102,
    )
    typed2, logical2, receipt2, directive2 = execute_transition(
        typed1, logical1, event2, oracle_proposal(event2), physically_true_ids=TRUTH
    )
    assert directive1 == (
        "place_in(porcelain_mug_1, microwave_1_heating_region)"
    )
    assert directive2 == "HALT"
    assert event2["target_commitment_id"] == REPLACEMENT_ATOM.commitment_id
    rows = {row["id"]: row for row in logical2["commitments"]}
    assert rows[DONE_ATOM.commitment_id]["lifecycle_status"] == "satisfied"
    assert rows[PENDING_ATOM.commitment_id]["lifecycle_status"] == "superseded"
    assert rows[PENDING_ATOM.commitment_id]["supersession_links"] == [
        REPLACEMENT_ATOM.commitment_id
    ]
    assert rows[REPLACEMENT_ATOM.commitment_id]["lifecycle_status"] == "cancelled"
    assert rows[REPLACEMENT_ATOM.commitment_id]["override_links"] == [
        PENDING_ATOM.commitment_id
    ]
    assert typed2.revision == 3
    assert receipt1["after_hash"] == receipt2["before_hash"]
    assert logical2["progress_ledger"] == logical0["progress_ledger"]


@pytest.mark.parametrize("atom", [
    CommitmentAtom("close", ("microwave_1", "extra")),
    CommitmentAtom("open", ("microwave_1",)),
    CommitmentAtom("in", ("unknown", "microwave_1_heating_region")),
])
def test_unknown_predicate_argument_or_arity_fails_closed(atom):
    _, logical = initial()
    with pytest.raises(ArityCommitmentError):
        build_event(
            logical, sequence_id="unit", step_index=1,
            event_type="replace_pending_goal", replacement_atom=atom,
            world_version=101,
        )


@pytest.mark.parametrize("field,value", [
    ("target_id", DONE_ATOM.commitment_id),
    ("base_version", 0),
    ("replacement_id", PENDING_ATOM.commitment_id),
])
def test_wrong_target_stale_version_and_wrong_replacement_fail_closed(field, value):
    typed, logical = initial()
    event = build_event(
        logical, sequence_id="unit", step_index=1,
        event_type="replace_pending_goal", replacement_atom=REPLACEMENT_ATOM,
        world_version=101,
    )
    proposal = oracle_proposal(event)
    proposal[field] = value
    with pytest.raises(ArityCommitmentError):
        execute_transition(typed, logical, event, proposal, physically_true_ids=TRUTH)


def test_replay_and_missing_physical_witness_fail_closed():
    typed0, logical0 = initial()
    event1 = build_event(
        logical0, sequence_id="unit", step_index=1,
        event_type="replace_pending_goal", replacement_atom=REPLACEMENT_ATOM,
        world_version=101,
    )
    typed1, logical1, _, _ = execute_transition(
        typed0, logical0, event1, oracle_proposal(event1), physically_true_ids=TRUTH
    )
    with pytest.raises(ArityCommitmentError):
        execute_transition(
            typed1, logical1, event1, oracle_proposal(event1), physically_true_ids=TRUTH
        )
    typed, logical = initial("missing-witness")
    event = build_event(
        logical, sequence_id="missing-witness", step_index=1,
        event_type="replace_pending_goal", replacement_atom=REPLACEMENT_ATOM,
        world_version=101,
    )
    with pytest.raises(ArityCommitmentError):
        execute_transition(typed, logical, event, oracle_proposal(event), physically_true_ids=())


def test_duplicate_historical_id_and_source_atom_tamper_fail_closed():
    typed0, logical0 = initial()
    event1 = build_event(
        logical0, sequence_id="unit", step_index=1,
        event_type="replace_pending_goal", replacement_atom=REPLACEMENT_ATOM,
        world_version=101,
    )
    _, logical1, _, _ = execute_transition(
        typed0, logical0, event1, oracle_proposal(event1), physically_true_ids=TRUTH
    )
    assert active_tip(logical1) == REPLACEMENT_ATOM
    with pytest.raises(ArityCommitmentError):
        build_event(
            logical1, sequence_id="unit", step_index=2,
            event_type="replace_pending_goal", replacement_atom=PENDING_ATOM,
            world_version=102,
        )
    tampered = copy.deepcopy(event1)
    tampered["source_atom"] = DONE_ATOM.to_dict()
    with pytest.raises(ArityCommitmentError):
        execute_transition(
            typed0, logical0, tampered, oracle_proposal(tampered),
            physically_true_ids=TRUTH,
        )

