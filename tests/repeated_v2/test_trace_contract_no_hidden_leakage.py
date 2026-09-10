import json
from pathlib import Path

import pytest

from cope_benchmark.repeated_v2.trace_contract_validation_v1 import (
    TraceLeakageError, assert_no_hidden_leakage, validate_public_bundle,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "frozen/repeated_v2_trace_contract_v1/fixtures/runtime_trace_bundle.json"


@pytest.mark.parametrize("payload", [
    {"nested": [{"canonical_state": {"goal": True}}]},
    {"payload": json.dumps({"gold_occurrence": "goal:x@2"})},
    {"event": {"family": "USER_CANCELS_ACTIVE_GOAL"}},
    {"observation": {"object-state": [1, 2, 3]}},
    {"deep": [{"more": [{"simulator_truth": True}]}]},
])
def test_recursive_scanner_rejects_hidden_or_answer_bearing_content(payload):
    with pytest.raises(TraceLeakageError):
        assert_no_hidden_leakage(payload)


def test_method_proposed_operator_is_public_audit_data_not_a_gold_label():
    assert_no_hidden_leakage({"raw_patch": {"operations": [{"op": "SUSPEND"}]}})


def test_poisoned_nested_runtime_record_is_rejected():
    value = json.loads(FIXTURE.read_text())
    value["planner_decisions"][0]["debug"] = {"expected_operator": "SUSPEND"}
    with pytest.raises(TraceLeakageError):
        validate_public_bundle(value)
