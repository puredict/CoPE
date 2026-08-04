from __future__ import annotations

import csv
import importlib.util
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_sequential_formal_v2_manifest",
    ROOT / "tools" / "build_sequential_formal_v2_manifest.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_v2_manifest_preserves_units_and_balances_five_arm_positions():
    with (ROOT / "manifests" / "sequential_formal_40x4x2_v1.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        source = list(csv.DictReader(handle))
    output = MODULE.build(source)
    assert len(output) == 40
    assert [row["sequence_id"] for row in output] == [row["sequence_id"] for row in source]
    assert all(row["schema_version"] == "cope-sequential-formal-manifest-v2" for row in output)
    assert all(row["governed_contract_sha256"] for row in output)
    positions = Counter()
    for row in output:
        order = row["arm_order"].split(";")
        assert set(order) == set(MODULE.ARMS) and len(order) == 5
        for index, arm in enumerate(order):
            positions[(arm, index)] += 1
    assert set(positions.values()) == {8}

