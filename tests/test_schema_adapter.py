from __future__ import annotations

import pytest

from auditability import SCHEMA_VERSION
from auditability.corpus_builder import validate_input_provenance
from auditability.schema_adapter import adapt_episode
from auditability.synthetic import synthetic_episode


def test_legacy_summary_and_logs_adapt_without_losing_records() -> None:
    legacy = {
        "task_id": 2,
        "initial_state_id": 1,
        "seed": 7,
        "mode": "reactive_disturbed",
        "success": False,
        "events": [{"event": "disturbance_applied", "policy_step": 7}],
        "actions": [{"policy_step": 7, "action": [0, 1]}],
        "git_commit": "abc123",
        "config_hash": "cfg123",
        "schema_version": "legacy.test",
    }
    adapted = adapt_episode(legacy, origin="/tmp/example")
    assert adapted["schema_version"] == SCHEMA_VERSION
    assert adapted["metadata"]["input_commit"] == "abc123"
    assert adapted["metadata"]["input_config_hash"] == "cfg123"
    assert adapted["metadata"]["input_schema_version"] == "legacy.test"
    assert adapted["raw"]["events"][0]["id"].startswith("event:")
    assert adapted["raw"]["actions"][0]["id"].startswith("action:")


def test_canonical_record_preserves_nested_metadata() -> None:
    source = synthetic_episode(0)
    adapted = adapt_episode(source)
    assert adapted["metadata"]["synthetic"] is True
    assert adapted["metadata"]["input_schema_version"] == "auditability.synthetic.v1"
    assert adapted["episode_id"] == source["episode_id"]


def test_formal_and_synthetic_inputs_cannot_be_mixed_or_mislabeled() -> None:
    synthetic = synthetic_episode(1)
    validate_input_provenance([synthetic], data_kind="synthetic")
    with pytest.raises(ValueError, match="cannot mix or mislabel"):
        validate_input_provenance([synthetic], data_kind="formal")
    formal = synthetic_episode(2)
    formal["metadata"]["synthetic"] = False
    formal["metadata"]["input_commit"] = "commit123"
    formal["metadata"]["input_config_hash"] = "config123"
    formal["metadata"]["input_schema_version"] = "cope.state.v1"
    validate_input_provenance([formal], data_kind="formal")
