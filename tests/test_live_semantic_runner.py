from __future__ import annotations

import csv
from pathlib import Path

import pytest

from cope.semantic_live_runner import (
    DEVELOPMENT_STATE_IDS,
    load_semantic_config,
    make_paired_recovery_inputs,
    validate_case_rows,
)

# This module intentionally exercises the reusable contract layer, not CLI internals.


def test_development_state_lock_rejects_reserved_state() -> None:
    assert DEVELOPMENT_STATE_IDS == frozenset(range(5))
    rows = [
        {
            "case_id": "forbidden",
            "state_id": "25",
            "event_type": "cancel_pending_goal",
        }
    ]
    with pytest.raises(ValueError, match="outside the consumed development range"):
        validate_case_rows(rows)


def test_paired_recovery_input_is_byte_identical() -> None:
    event = {"event_id": "event-1", "event_type": "cancel_pending_goal"}
    observation = {"sha256": "a" * 64, "predicate_snapshot": {"policy_step": 3}}
    native, cope, payload = make_paired_recovery_inputs(
        pair_key="pair",
        original_task="put both objects in the basket",
        observation=observation,
        event=event,
        public_action_history=({"policy_step": 0, "environment_action": [0.0] * 7},),
        task_progress={"physically_true_objects": ["cream_cheese_1"]},
        observation_fields=("sha256", "predicate_snapshot"),
    )
    assert payload
    assert native.input_hash == cope.input_hash
    assert native.as_payload() == cope.as_payload()


def test_semantic_config_loader_consumes_sidecar_and_reserve_manifest(tmp_path: Path) -> None:
    reserve = tmp_path / "reserve.csv"
    reserve.write_text(
        "state_id,event_type,status\n"
        "25,replace_pending_goal,reserved_uninspected\n"
        "26,cancel_pending_goal,reserved_uninspected\n",
        encoding="utf-8",
    )
    config = tmp_path / "config.csv"
    fields = [
        "schema_version", "task_suite", "task_id", "observation_fields", "event_types",
        "reserved_state_ids", "rollout_authorized", "pilot_manifest_path",
        "predicate_producer_commit",
    ]
    row = {
        "schema_version": "cope-semantic-task1-pilot-config-v1",
        "task_suite": "libero_10",
        "task_id": "1",
        "observation_fields": "sha256;predicate_snapshot",
        "event_types": "replace_pending_goal;cancel_pending_goal",
        "reserved_state_ids": "25;26",
        "rollout_authorized": "false",
        "pilot_manifest_path": "reserve.csv",
        "predicate_producer_commit": "a" * 40,
    }
    with config.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerow(row)
    loaded = load_semantic_config(config, repo_root=tmp_path)
    assert loaded.row["task_id"] == "1"
    assert loaded.reserved_state_ids == frozenset({25, 26})
    assert loaded.predicate_engine_config["predicate_snapshot"]["test_only"] is False
