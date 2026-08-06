from __future__ import annotations

import copy

from auditability.common import content_hash
from auditability.corruptions import CORRUPTIONS, generate_corruptions
from auditability.deterministic_auditor import audit_episode
from auditability.scoring import score_corruptions
from auditability.synthetic import synthetic_episode


def test_corruptions_are_deterministic_and_do_not_modify_source() -> None:
    episode = synthetic_episode(0)
    before = copy.deepcopy(episode)
    first = generate_corruptions(episode, seed=17)
    second = generate_corruptions(episode, seed=17)
    assert first == second
    assert episode == before
    assert content_hash(episode) == content_hash(before)
    manifests = [manifest for _, manifest in first]
    assert {row["error_type"] for row in manifests if not row["negative_control"]} == set(
        CORRUPTIONS
    )
    assert sum(row["negative_control"] for row in manifests) == 1
    for trace, manifest in first:
        if manifest["negative_control"]:
            assert manifest["original_hash"] == manifest["corrupted_hash"]
        else:
            assert manifest["original_hash"] != manifest["corrupted_hash"]


def test_deterministic_auditor_detects_corruptions_and_passes_control() -> None:
    episode = synthetic_episode(3)
    generated = generate_corruptions(episode, seed=9)
    manifests = [manifest for _, manifest in generated]
    audits = [audit_episode(trace) for trace, _ in generated]
    score = score_corruptions(manifests, audits)
    assert score["recall"] == 1.0
    assert score["false_positive_rate"] == 0.0
    assert score["error_type_recall"] == 1.0
    assert score["f1"] == 1.0
