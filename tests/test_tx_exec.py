from __future__ import annotations

import ast
import csv
from pathlib import Path

import pytest

from cope.native_ntrack import (
    derive_post_state,
    expected_patch,
    materialize_patch,
    state_without_history,
    validate_and_compile,
    build_case,
)
from cope.tx_exec import TransactionRejected, execute_transaction
from cope.types import canonical_json, stable_hash


CASES = [
    "no_op",
    "cancel_sibling",
    "replace_pending_target",
    "activate_override",
    "release_override",
    "world_change_release",
    "wrong_source_revoke",
    "stale_version",
    "idempotence",
    "irrelevant_sibling_change",
    "continuity_valid",
    "continuity_invalid",
]


@pytest.mark.parametrize("case_id", CASES)
def test_tx_exec_matches_oracle_and_materialized_cope(case_id: str) -> None:
    case = build_case(case_id, "assigned", "test", "public_synthetic")
    before = canonical_json(case.pre_state)
    result = execute_transaction(case.pre_state, case.event, validate_and_compile)
    oracle = state_without_history(derive_post_state(case.pre_state, case.event))
    cope = materialize_patch(expected_patch(case.pre_state, case.event), case.pre_state, case.event)
    assert result.post_state == oracle == cope
    assert result.receipt["before_sha256"] == stable_hash(state_without_history(case.pre_state))
    assert result.receipt["staged_sha256"] == result.receipt["after_sha256"]
    assert result.receipt["validator_calls"] == 1
    assert result.receipt["validator_passed"] is True
    assert result.receipt["published"] is True
    assert canonical_json(case.pre_state) == before


FAULTS = [
    ("F01", "cancel_sibling"),
    ("F02", "replace_pending_target"),
    ("F03", "stale_version"),
    ("F04", "wrong_source_revoke"),
    ("F05", "replace_pending_target"),
    ("F06", "release_override"),
    ("F07", "continuity_invalid"),
    ("F08", "irrelevant_sibling_change"),
]


@pytest.mark.parametrize(("fault_id", "case_id"), FAULTS)
def test_faults_fail_closed_without_partial_publish(fault_id: str, case_id: str) -> None:
    case = build_case(case_id, "assigned", "test", "public_synthetic")
    before = canonical_json(case.pre_state)
    with pytest.raises(TransactionRejected) as caught:
        execute_transaction(case.pre_state, case.event, validate_and_compile, fault_id=fault_id)
    receipt = caught.value.receipt
    assert receipt["published"] is False
    assert receipt["rolled_back"] is True
    assert receipt["after_sha256"] is None
    assert canonical_json(case.pre_state) == before


def test_tx_exec_source_is_independent_of_forbidden_constructors() -> None:
    source_path = Path(__file__).resolve().parents[1] / "cope" / "tx_exec.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden = {
        "expected_patch",
        "materialize_patch",
        "derive_post_state",
        "apply_patch",
        "PatchOutput",
        "ConstraintStateEngine",
    }
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                used.add(alias.name.rsplit(".", 1)[-1])
    assert not forbidden.intersection(used)

