from __future__ import annotations

from auditability.common import is_parseable_id
from auditability.ground_truth import QUESTION_KINDS, extract_ground_truth
from auditability.question_generator import generate_questions
from auditability.synthetic import synthetic_episode


def test_ground_truth_is_deterministic_and_has_six_stable_questions() -> None:
    episode = synthetic_episode(0)
    first = extract_ground_truth(episode)
    second = extract_ground_truth(episode)
    assert first == second
    assert [row["question_kind"] for row in first] == list(QUESTION_KINDS)
    assert len(first) == 6
    assert generate_questions(episode) == generate_questions(episode)
    assert len({row["question_id"] for row in generate_questions(episode)}) == 6


def test_ground_truth_links_parseable_provenance_ids() -> None:
    for truth in extract_ground_truth(synthetic_episode(1)):
        assert truth["answerability"] == "answerable"
        assert truth["supporting_ids"]
        assert all(is_parseable_id(value) for value in truth["supporting_ids"])
        assert truth["provenance"]["synthetic"] is True
        assert truth["provenance"]["input_schema_version"] == "auditability.synthetic.v1"


def test_unknown_evidence_becomes_unanswerable_not_invented() -> None:
    episode = synthetic_episode(2)
    episode["cope"]["validator_outputs"] = []
    restore = next(
        row
        for row in extract_ground_truth(episode)
        if row["question_kind"] == "restore_revalidation"
    )
    assert restore["normalized_answer"].startswith("no:")
    episode["cope"]["patches"] = []
    restore = next(
        row
        for row in extract_ground_truth(episode)
        if row["question_kind"] == "restore_revalidation"
    )
    assert restore["answerability"] == "unanswerable_from_ground_truth"
    assert restore["normalized_answer"] == "unanswerable"
