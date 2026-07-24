from __future__ import annotations

import copy

from auditability.deterministic_auditor import audit_episode
from auditability.synthetic import synthetic_episode
from auditability.trace_state import replay_patch, state_hash


def test_synthetic_trace_replays_and_hashes_cleanly() -> None:
    episode = synthetic_episode(5)
    assert audit_episode(episode)["findings"] == []
    states = {row["id"]: row for row in episode["cope"]["states"]}
    for state in states.values():
        assert state["state_hash"] == state_hash(state)
    for patch in episode["cope"]["patches"]:
        before = states[patch["before_state_id"]]
        after = states[patch["after_state_id"]]
        assert replay_patch(before["slots"], patch) == after["slots"]


def test_replay_and_hash_mismatches_are_reported() -> None:
    episode = synthetic_episode(6)
    broken = copy.deepcopy(episode)
    broken["cope"]["states"][0]["state_hash"] = "bad"
    kinds = set(audit_episode(broken)["detected_error_types"])
    assert "state_hash_mismatch" in kinds
    broken = copy.deepcopy(episode)
    broken["cope"]["states"][1]["slots"][0]["value"] = "silently changed"
    broken["cope"]["states"][1]["state_hash"] = state_hash(
        broken["cope"]["states"][1]
    )
    kinds = set(audit_episode(broken)["detected_error_types"])
    assert "patch_replay_mismatch" in kinds
