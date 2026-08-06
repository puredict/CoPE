from __future__ import annotations

import copy

import pytest

from auditability.blinding import make_packages
from auditability.human_study import export_assignments, import_annotations
from auditability.question_generator import generate_questions
from auditability.synthetic import synthetic_episode


def _packages() -> list[dict]:
    rows = []
    for index in range(4):
        episode = synthetic_episode(index)
        packages, _ = make_packages(
            episode, generate_questions(episode), seed=13
        )
        rows.extend(packages)
    return rows


def test_human_export_is_balanced_and_avoids_adjacent_conditions() -> None:
    rows, manifest = export_assignments(
        _packages(),
        episode_count=4,
        annotator_count=3,
        ratings_per_package=3,
        seed=13,
    )
    assert manifest["episode_count"] == 4
    assert manifest["ratings_per_package"] == 3
    by_annotator = {}
    for row in rows:
        by_annotator.setdefault(row["annotator_code"], []).append(row)
    for assignments in by_annotator.values():
        blocks = []
        for row in assignments:
            key = (row["episode_id"], row["condition_label"])
            if not blocks or blocks[-1] != key:
                blocks.append(key)
        for previous, current in zip(blocks, blocks[1:]):
            assert not (previous[0] == current[0] and previous[1] != current[1])


def test_human_import_detects_duplicate_missing_and_bad_time() -> None:
    exported, _ = export_assignments(
        _packages(),
        episode_count=1,
        annotator_count=3,
        ratings_per_package=3,
        seed=5,
    )
    completed = copy.deepcopy(exported)
    for row in completed:
        row.update(
            {
                "answer": "test",
                "confidence_1_to_5": "3",
                "completion_time_seconds": "12.5",
            }
        )
    assert len(import_annotations(completed, exported)) == len(exported)
    with pytest.raises(ValueError, match="duplicate"):
        import_annotations(completed + [completed[0]], exported)
    with pytest.raises(ValueError, match="missing"):
        import_annotations(completed[:-1], exported)
    completed[0]["completion_time_seconds"] = "-1"
    with pytest.raises(ValueError, match="cannot be negative"):
        import_annotations(completed, exported)
