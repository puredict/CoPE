from __future__ import annotations

import json

import pytest

from cope import (
    ConstraintState,
    Demote,
    Insert,
    Suspend,
    canonical_state_hash,
    deserialize_state,
    replay,
    serialize_state,
)
from cope.errors import HASH_MISMATCH, InvariantError

from conftest import apply_ok, make_slot


def test_serialization_round_trip_is_canonical(root_state) -> None:
    state = apply_ok(root_state, 2, [Suspend("op-suspend", "alignment-1", "temporary")])
    payload = serialize_state(state)
    restored = deserialize_state(json.loads(json.dumps(payload, sort_keys=True)))
    assert serialize_state(restored) == payload
    assert restored.state_hash == state.state_hash
    assert canonical_state_hash(restored) == state.state_hash


def test_replay_matches_canonical_json_and_hash() -> None:
    initial = ConstraintState.empty("replay-state")
    slot = make_slot("slot-1", "event-1")
    state = apply_ok(initial, 1, [Insert("op-insert", slot)])
    state = apply_ok(state, 2, [Demote("op-demote", "slot-1", 20, "lower confidence")])
    replayed = replay(initial, state.patch_history)
    assert serialize_state(replayed) == serialize_state(state)
    assert replayed.state_hash == state.state_hash


def test_deserialize_detects_hash_corruption(root_state) -> None:
    payload = serialize_state(root_state)
    payload["slots"][0]["content"]["object_id"] = "tampered"
    with pytest.raises(InvariantError) as caught:
        deserialize_state(payload)
    assert caught.value.code == HASH_MISMATCH
