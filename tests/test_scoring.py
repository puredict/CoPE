from __future__ import annotations

from auditability.blinding import make_packages
from auditability.corruptions import generate_corruptions
from auditability.deterministic_auditor import audit_episode
from auditability.question_generator import generate_questions
from auditability.scoring import score_all, token_f1
from auditability.synthetic import oracle_predictions, synthetic_episode


def _corpus() -> tuple[list[dict], list[dict], list[dict]]:
    questions = []
    packages = []
    key = []
    for index in range(3):
        episode = synthetic_episode(index)
        episode_questions = generate_questions(episode)
        episode_packages, episode_key = make_packages(
            episode, episode_questions, seed=11
        )
        questions.extend(episode_questions)
        packages.extend(episode_packages)
        key.extend(episode_key)
    return questions, packages, key


def test_token_f1_and_oracle_scoring() -> None:
    assert token_f1("", "") == 1.0
    assert token_f1("", "answer") == 0.0
    assert token_f1("new alignment", "new alignment") == 1.0
    questions, packages, key = _corpus()
    predictions = oracle_predictions(questions, packages)
    score = score_all(
        questions,
        packages,
        key,
        predictions,
        seed=3,
        bootstrap_iterations=100,
    )
    assert score["missing_prediction_count"] == 0
    assert score["duplicate_prediction_count"] == 0
    for condition in ("raw", "regeneration", "typed_patch"):
        assert score["conditions"][condition]["audit_qa_exact_accuracy"] == 1.0
        assert score["conditions"][condition]["token_f1"] == 1.0
        assert score["conditions"][condition]["field_f1"] == 1.0
        assert score["conditions"][condition]["provenance_link_accuracy"] == 1.0


def test_corruption_metrics_include_negative_controls() -> None:
    generated = generate_corruptions(synthetic_episode(0), seed=12)
    manifests = [manifest for _, manifest in generated]
    audits = [audit_episode(trace) for trace, _ in generated]
    questions, packages, key = _corpus()
    score = score_all(
        questions,
        packages,
        key,
        oracle_predictions(questions, packages),
        seed=3,
        bootstrap_iterations=20,
        corruption_manifests=manifests,
        corruption_audits=audits,
    )
    assert score["corruption_detection"]["recall"] == 1.0
    assert score["corruption_detection"]["false_positive_rate"] == 0.0
