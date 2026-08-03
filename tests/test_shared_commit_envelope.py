from __future__ import annotations

import copy

import pytest

from cope.shared_commit_envelope import (
    ARMS,
    SharedEnvelopeError,
    build_development_cases,
    commit_envelope,
    materialize_proposal,
    oracle_proposal,
    qualification_rows,
)


def test_six_distinct_new_development_families() -> None:
    cases = build_development_cases()
    assert len(cases) == 6
    assert len({case.case_id for case in cases}) == 6
    assert len({case.family for case in cases}) == 6
    assert all(case.case_id.startswith("SCE-D") for case in cases)


def test_all_oracle_arms_materialize_identically() -> None:
    rows = qualification_rows()
    assert len(rows) == 24
    assert all(row["oracle_accepted"] for row in rows)
    for case in build_development_cases():
        outputs = [materialize_proposal(case, arm, oracle_proposal(case, arm)) for arm in ARMS]
        assert outputs.count(outputs[0]) == 4


def test_no_arm_outputs_transaction_metadata() -> None:
    banned = {"state_version", "evidence_version", "processed_events", "payload_sha256", "receipt"}
    for case in build_development_cases():
        for arm in ARMS:
            proposal = oracle_proposal(case, arm)
            assert not (set(proposal) & banned)
            payload = proposal.get("operations", proposal.get("writes", []))
            assert all(not (set(item) & banned) for item in payload if isinstance(item, dict))


def test_shared_envelope_binds_and_hashes_event() -> None:
    case = build_development_cases()[0]
    meta = commit_envelope(case.transaction_meta, case.event)
    assert meta["state_version"] == case.transaction_meta["state_version"] + 1
    assert meta["evidence_version"] == case.event["world_version"]
    assert meta["processed_events"][0]["event_id"] == case.event["event_id"]
    assert len(meta["processed_events"][0]["payload_sha256"]) == 64


def test_metadata_injection_and_extra_fields_fail() -> None:
    case = build_development_cases()[0]
    for arm in ARMS:
        proposal = oracle_proposal(case, arm)
        proposal["state_version"] = 999
        with pytest.raises(SharedEnvelopeError, match="schema mismatch"):
            materialize_proposal(case, arm, proposal)


def test_stale_binding_and_duplicate_event_fail() -> None:
    case = build_development_cases()[0]
    proposal = oracle_proposal(case, "cope_semantic")
    proposal["base_version"] -= 1
    with pytest.raises(SharedEnvelopeError, match="binding"):
        materialize_proposal(case, "cope_semantic", proposal)
    duplicate = copy.deepcopy(case.transaction_meta)
    duplicate["processed_events"].append({"event_id": case.event["event_id"], "payload_sha256": "0" * 64})
    with pytest.raises(SharedEnvelopeError, match="already processed"):
        commit_envelope(duplicate, case.event)


def test_compact_metadata_paths_are_forbidden() -> None:
    case = build_development_cases()[0]
    proposal = oracle_proposal(case, "compact_semantic")
    proposal["writes"].append({"op": "replace", "path": "/state_version", "value": 99})
    with pytest.raises(SharedEnvelopeError, match="metadata"):
        materialize_proposal(case, "compact_semantic", proposal)


def test_compact_oracle_uses_natural_record_paths_and_remove() -> None:
    cases = build_development_cases()
    replacement = oracle_proposal(cases[1], "compact_semantic")
    assert any(write["path"] == "/commitments/new_part" for write in replacement["writes"])
    release = oracle_proposal(cases[3], "compact_semantic")
    assert {"op": "remove", "path": "/restorations/restore_base", "value": None} in release["writes"]
