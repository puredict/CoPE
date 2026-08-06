from __future__ import annotations

from copy import deepcopy

from cope.types import METHOD_NAMES
from cope.validation import validate_pair_records
from tests.test_budget_accounting import minimal_record


def test_event_initial_state_actions_and_observation_are_strictly_paired() -> None:
    records = [minimal_record(method) for method in METHOD_NAMES]
    assert validate_pair_records(records)["passed"]
    records[-1]["event"] = {"event_type": "different"}
    records[-2]["initial_state_hash"] = "different"
    records[-3]["pre_event_action_digest"] = "different"
    records[-4]["fresh_observation_hash"] = "different"
    result = validate_pair_records(records)
    assert not result["passed"]
    joined = "\n".join(result["errors"])
    assert "event mismatch" in joined
    assert "initial_state_hash mismatch" in joined
    assert "pre_event_action_digest mismatch" in joined
    assert "fresh_observation_hash mismatch" in joined


def test_full_regeneration_and_cope_must_share_provider_and_common_input() -> None:
    records = [minimal_record(method) for method in METHOD_NAMES]
    records[-1]["provider_metadata"] = {"model": "different"}
    records[-1]["recovery_input_hash"] = "different"
    result = validate_pair_records(records)
    assert not result["passed"]
    assert any("provider_metadata mismatch" in error for error in result["errors"])
    assert any("same common recovery input hash" in error for error in result["errors"])
