from __future__ import annotations

from collections import Counter

from auditability.blinding import find_blinding_leaks, make_packages
from auditability.question_generator import generate_questions
from auditability.synthetic import synthetic_episode


def test_three_conditions_are_blinded_and_questions_match() -> None:
    episode = synthetic_episode(2)
    questions = generate_questions(episode)
    packages, key = make_packages(episode, questions, seed=42)
    assert len(packages) == 18
    assert len(key) == 3
    assert {row["internal_condition"] for row in key} == {
        "raw",
        "regeneration",
        "typed_patch",
    }
    assert all(not find_blinding_leaks(package) for package in packages)
    grouped = Counter(package["item_id"] for package in packages)
    assert set(grouped.values()) == {3}
    for item_id in grouped:
        text = {row["question"] for row in packages if row["item_id"] == item_id}
        assert len(text) == 1


def test_blinded_labels_are_balanced_and_opaque() -> None:
    episode = synthetic_episode(4)
    packages, key = make_packages(episode, generate_questions(episode), seed=7)
    assert {row["condition_label"] for row in packages} == {"C00", "C01", "C02"}
    assert Counter(row["condition_label"] for row in packages) == {
        "C00": 6,
        "C01": 6,
        "C02": 6,
    }
    assert all("internal_condition" not in row for row in packages)
    assert all(row["key_id"].startswith("conditionkey:") for row in key)
