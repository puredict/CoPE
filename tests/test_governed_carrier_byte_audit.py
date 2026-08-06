from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

from cope.governance_collision_prompting import GOVERNED_DELTA_CONTRACT


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "governed_carrier_byte_audit",
    ROOT / "experiments" / "governed_carrier_byte_audit.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_governed_contract_freezes_capability_without_cope_operations():
    for required in (
        "governed-delta-v1", "affected_scope", "forest_delta",
        "blackboard_delta", "read_revision",
    ):
        assert required in GOVERNED_DELTA_CONTRACT
    assert "Override" not in GOVERNED_DELTA_CONTRACT
    assert "Expire" not in GOVERNED_DELTA_CONTRACT


def test_all_oracle_carriers_materialize_to_same_transition():
    with (ROOT / "manifests" / "sequential_persistence_gate_v2.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        cases = list(csv.DictReader(handle))
    rows = MODULE.build_rows(cases)
    assert len(rows) == 40
    assert {row["arm"] for row in rows} == set(MODULE.ARMS)
    assert all(row["canonical_equivalent"] for row in rows)
    assert all(row["proposal_bytes"] > 0 and row["contract_bytes"] > 0 for row in rows)
    for case in cases:
        for event_index in (1, 2):
            selected = [
                row for row in rows
                if row["case_id"] == case["case_id"] and row["event_index"] == event_index
            ]
            assert len({row["directive"] for row in selected}) == 1

