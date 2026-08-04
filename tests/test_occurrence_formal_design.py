from __future__ import annotations

from collections import Counter

from cope.occurrence_sequence import build_recurrence_case, expected_next_state, occurrence_id
from tools.build_occurrence_formal_manifest import build
from experiments.occurrence_formal_preflight import ARMS, validate_manifest


def test_occurrence_manifest_is_balanced_and_cases_reconstruct():
    rows = build()
    validate_manifest([{key: str(value) for key, value in row.items()} for row in rows])
    positions = Counter()
    for row in rows:
        for position, arm in enumerate(str(row["arm_order"]).split(";")):
            positions[(position, arm)] += 1
        pre, event, _ = build_recurrence_case(
            case_id=str(row["case_id"]), done_object=str(row["done_object"]),
            recurring_object=str(row["recurring_object"]),
            intermediate_object=str(row["intermediate_object"]),
            recurrence_depth=int(row["recurrence_depth"]),
        )
        expected = expected_next_state(pre, event)
        replacement = occurrence_id(
            str(row["recurring_object"]), int(row["recurrence_depth"]) + 1
        )
        records = {item["id"]: item for item in expected["commitments"]}
        assert records[replacement]["lifecycle_status"] == "active"
    assert len(rows) == 40
    assert set(positions.values()) == {8}
    assert set(arm for _, arm in positions) == set(ARMS)
