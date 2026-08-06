from __future__ import annotations

from cope.shared_commit_envelope import ARMS, materialize_proposal, oracle_proposal
from cope.shared_envelope_holdout import build_holdout_cases
from cope.types import stable_hash


def test_holdout_has_36_unique_cases_and_families() -> None:
    cases = build_holdout_cases()
    assert len(cases) == 36
    assert len({case.case_id for case in cases}) == 36
    assert len({case.family for case in cases}) == 36
    assert all(case.case_id.startswith("SCE-H") for case in cases)


def test_holdout_has_144_equivalent_oracle_materializations() -> None:
    cells = 0
    for case in build_holdout_cases():
        outputs = []
        for arm in ARMS:
            outputs.append(materialize_proposal(case, arm, oracle_proposal(case, arm)))
            cells += 1
        assert len({stable_hash(output) for output in outputs}) == 1
    assert cells == 144


def test_every_holdout_delta_has_visible_rule_clause() -> None:
    for case in build_holdout_cases():
        assert len(case.rule_clauses) == len(case.oracle_operations)
        assert [rule["id"] for rule in case.rule_clauses] == [
            f"R{index}" for index in range(1, len(case.rule_clauses) + 1)
        ]
        assert all(rule["text"] for rule in case.rule_clauses)


def test_holdout_excludes_transaction_metadata_from_oracles() -> None:
    banned = {"state_version", "evidence_version", "processed_events", "payload_sha256", "receipt"}
    for case in build_holdout_cases():
        for arm in ARMS:
            proposal = oracle_proposal(case, arm)
            assert not (set(proposal) & banned)
