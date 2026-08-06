from __future__ import annotations

from collections import Counter

from cope.shared_commit_envelope import ARMS, materialize_proposal, oracle_proposal
from cope.shared_envelope_scaling import STATE_SIZES, build_scaling_cases


def test_scaling_corpus_has_36_matched_transitions_at_each_size() -> None:
    cases = build_scaling_cases()
    assert len(cases) == 108
    assert Counter(len(case.pre_state["commitments"]) for case in cases) == {4: 36, 16: 36, 32: 36}
    assert len({case.case_id for case in cases}) == 108
    assert all(case.case_id.startswith("SCE-S") for case in cases)


def test_scaling_transitions_remain_sparse_as_state_grows() -> None:
    for case in build_scaling_cases():
        assert 1 <= len(case.oracle_operations) <= 4
        assert len(case.oracle_operations) / len(case.pre_state["commitments"]) <= 1.0


def test_all_scaling_oracles_materialize_through_the_shared_envelope() -> None:
    for case in build_scaling_cases():
        outputs = [materialize_proposal(case, arm, oracle_proposal(case, arm)) for arm in ARMS]
        assert outputs.count(outputs[0]) == len(ARMS)


def test_scaling_sizes_are_frozen() -> None:
    assert STATE_SIZES == (4, 16, 32)
