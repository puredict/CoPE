from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from cope.compact_tx import (
    CompactTransactionRejected,
    execute_compact_transaction,
    proposal_from_verbose_carrier,
)
from cope.native_ntrack import build_case, derive_post_state, state_without_history, validate_and_compile
from cope.tx_exec import execute_transaction
from cope.types import canonical_json


CASES = [
    "no_op", "cancel_sibling", "replace_pending_target", "activate_override",
    "release_override", "world_change_release", "wrong_source_revoke", "stale_version",
    "idempotence", "irrelevant_sibling_change", "continuity_valid", "continuity_invalid",
]


def proposal(case_id: str):
    case = build_case(case_id, "assigned", "test", "public_synthetic")
    verbose = execute_transaction(case.pre_state, case.event, validate_and_compile)
    return case, proposal_from_verbose_carrier(verbose.carrier)


@pytest.mark.parametrize("case_id", CASES)
def test_compact_materializer_matches_oracle(case_id: str) -> None:
    case, compact = proposal(case_id)
    before = canonical_json(case.pre_state)
    result = execute_compact_transaction(compact, case.pre_state, case.event, validate_and_compile)
    assert result.post_state == state_without_history(derive_post_state(case.pre_state, case.event))
    assert result.receipt["validator_calls"] == 1
    assert result.receipt["published"] is True
    assert canonical_json(case.pre_state) == before


@pytest.mark.parametrize("fault_id", ["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08"])
def test_compact_faults_fail_closed(fault_id: str) -> None:
    source = {
        "C01": "cancel_sibling", "C02": "cancel_sibling", "C03": "cancel_sibling",
        "C04": "replace_pending_target", "C05": "cancel_sibling",
        "C06": "replace_pending_target", "C07": "continuity_invalid",
        "C08": "irrelevant_sibling_change",
    }[fault_id]
    case, compact = proposal(source)
    compact = copy.deepcopy(compact)
    staged_fault = None
    if fault_id == "C01": compact["base_version"] -= 1
    elif fault_id == "C02": compact["event_id"] = "wrong:event"
    elif fault_id == "C03": compact["writes"].append({"op": "replace", "path": "/schema_version", "value": "evil"})
    elif fault_id == "C04": compact["writes"].append(copy.deepcopy(compact["writes"][0]))
    elif fault_id == "C05": compact["writes"][0]["path"] = "/commitments/unknown:id/lifecycle_status"
    elif fault_id == "C06": staged_fault = "drop_progress_ledger"
    elif fault_id == "C07": staged_fault = "retain_illegal_executing_action"

    def validator(candidate, state, event):
        if fault_id == "C08": raise RuntimeError("external validator exception")
        return validate_and_compile(candidate, state, event)

    before = canonical_json(case.pre_state)
    with pytest.raises(CompactTransactionRejected) as caught:
        execute_compact_transaction(compact, case.pre_state, case.event, validator, staged_fault=staged_fault)
    assert caught.value.receipt["published"] is False
    assert caught.value.receipt["rolled_back"] is True
    assert caught.value.receipt["after_sha256"] is None
    expected_stage = {
        "C01": "parser", "C02": "parser", "C03": "parser", "C04": "parser",
        "C05": "materializer", "C06": "semantic_validator",
        "C07": "semantic_validator", "C08": "semantic_validator",
    }[fault_id]
    assert caught.value.receipt["rejection_stage"] == expected_stage
    assert canonical_json(case.pre_state) == before


def test_compact_source_does_not_use_semantic_constructors() -> None:
    path = Path(__file__).resolve().parents[1] / "cope" / "compact_tx.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = {"expected_patch", "materialize_patch", "derive_post_state", "apply_patch"}
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name): used.add(node.id)
        elif isinstance(node, ast.Attribute): used.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names: used.add(alias.name.rsplit(".", 1)[-1])
    assert not forbidden.intersection(used)
