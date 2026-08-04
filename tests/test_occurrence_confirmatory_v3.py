import csv
from pathlib import Path

from cope.occurrence_prompting import ARMS
from cope.occurrence_prompting_confirmatory_v3 import (
    CONTRACTS_V3,
    EXPECTED_CONTRACT_HASHES_V3,
)
from cope.types import stable_hash
from experiments.occurrence_confirmatory_runner_v3 import EXPECTED_MANIFEST_SHA256_V3


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "research" / "occurrence_confirmatory_v3" / "manifest.csv"
V1_OBJECTS = {
    "alphabet_soup_1", "butter_1", "cream_cheese_1", "ketchup_1",
    "milk_1", "orange_juice_1", "tomato_sauce_1",
}


def test_v3_contracts_are_frozen_and_field_explicit() -> None:
    assert tuple(CONTRACTS_V3) == ARMS
    assert {arm: stable_hash(CONTRACTS_V3[arm]) for arm in ARMS} == EXPECTED_CONTRACT_HASHES_V3
    neutral = CONTRACTS_V3["neutral_patch"]
    assert 'must not end\nin "/"' in neutral
    assert "/commitments/+/goal:in:item_1:box_region@2" in neutral
    for contract in CONTRACTS_V3.values():
        assert "event.target_commitment_id" in contract
        assert "event.replacement_commitment_id" in contract


def test_v3_manifest_is_locked_balanced_and_vocabulary_disjoint() -> None:
    assert MANIFEST.is_file()
    assert __import__("hashlib").sha256(MANIFEST.read_bytes()).hexdigest() == EXPECTED_MANIFEST_SHA256_V3
    with MANIFEST.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 40
    assert len({row["case_id"] for row in rows}) == 40
    objects = {
        row[key]
        for row in rows
        for key in ("done_object", "recurring_object", "intermediate_object")
    }
    assert objects.isdisjoint(V1_OBJECTS)
    assert {(int(row["triple_index"]), int(row["recurrence_depth"])) for row in rows} == {
        (triple, depth) for triple in range(10) for depth in range(1, 5)
    }
    positions = {
        (position, arm): sum(
            row["arm_order"].split(";")[position] == arm for row in rows
        )
        for position in range(5) for arm in ARMS
    }
    assert set(positions.values()) == {8}
