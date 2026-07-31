from __future__ import annotations

import json

import pytest

from cope.semantic_replacement import (
    MilestoneEvent,
    build_oracle_full_state,
    build_replacement_event,
)
from experiments.semantic_replacement_canary import (
    _load_prefix_records,
    _prompt_for_variant,
)


def full_state():
    event = build_replacement_event(
        MilestoneEvent(
            policy_step=135,
            done_object="cream_cheese_1",
            pending_object="butter_1",
            stable_steps=5,
        ),
        pair_key="pair",
    )
    return build_oracle_full_state(event)


@pytest.mark.parametrize(
    ("variant", "expected"),
    (
        (
            "shared_compiler",
            "put both the alphabet soup and the cream cheese box in the basket",
        ),
        ("single_object", "put the alphabet soup in the basket"),
        (
            "progress_explicit",
            "the cream cheese box is already in the basket; now put the alphabet soup in the basket",
        ),
        ("pick_place", "pick up the alphabet soup and place it in the basket"),
        (
            "task0_exact_diagnostic",
            "put both the alphabet soup and the tomato sauce in the basket",
        ),
    ),
)
def test_prompt_variants(variant, expected) -> None:
    assert _prompt_for_variant(variant, full_state()) == expected


def test_prefix_loader_preserves_contiguous_policy_steps(tmp_path) -> None:
    path = tmp_path / "trace.jsonl"
    rows = [
        {"record_type": "start"},
        {"record_type": "policy_step", "policy_step": 0, "environment_action": [0.0]},
        {"record_type": "policy_step", "policy_step": 1, "environment_action": [1.0]},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    assert [row["policy_step"] for row in _load_prefix_records(path)] == [0, 1]


def test_prefix_loader_rejects_gaps(tmp_path) -> None:
    path = tmp_path / "trace.jsonl"
    path.write_text(
        json.dumps({"record_type": "policy_step", "policy_step": 1, "environment_action": [0.0]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="contiguous"):
        _load_prefix_records(path)
