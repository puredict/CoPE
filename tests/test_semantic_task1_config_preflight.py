from __future__ import annotations

import csv
from pathlib import Path


def test_semantic_config_pins_task1_and_keeps_reserved_states_locked() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "manifests" / "semantic_task1_config_v1.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    row = rows[0]
    assert row["task_suite"] == "libero_10"
    assert row["task_id"] == "1"
    assert row["checkpoint_id"] == "openvla-7b-finetuned-libero-10"
    assert row["checkpoint_unnorm_key"] == "libero_10"
    assert row["predicate_producer_commit"] == "298dac707bb0d57aad050978d6e81d7aab93090d"
    assert set(row["event_types"].split(";")) == {
        "replace_pending_goal",
        "cancel_pending_goal",
    }
    assert "predicate_snapshot" in row["observation_fields"].split(";")
    assert row["reserved_state_ids"] == "25;26"
    assert row["rollout_authorized"] == "false"
