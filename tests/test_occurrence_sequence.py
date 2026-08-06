from __future__ import annotations

import csv
import copy

import pytest

from experiments import occurrence_restoration_gate as gate
from cope.occurrence_sequence import (
    build_recurrence_case, cope_oracle, expected_next_state, fsr_oracle,
    full_replan_oracle, governed_oracle, materialize_cope,
    materialize_fsr, materialize_full_replan, materialize_governed,
    materialize_neutral, neutral_oracle,
)


def test_occurrence_restoration_gate(tmp_path, monkeypatch):
    output = tmp_path / "gate"
    monkeypatch.setattr("sys.argv", ["gate", "--output-dir", str(output)])
    assert gate.main() == 0
    with (output / "01_RESULTS.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 20
    assert {row["arm"] for row in rows} == set(gate.ARMS)
    restored = [
        row for row in rows
        if row["sequence_type"] == "replace_then_restore" and row["event_index"] == "2"
    ]
    assert len(restored) == 5
    assert {row["original_occurrence_1_status"] for row in restored} == {"superseded"}
    assert {row["original_occurrence_2_status"] for row in restored} == {"active"}
    with (output / "02_NEGATIVE_CASES.csv").open(newline="", encoding="utf-8") as handle:
        negative = list(csv.DictReader(handle))
    assert len(negative) == 5
    assert {row["rejected"] for row in negative} == {"True"}


def test_occurrence_controls_reject_nonminimal_or_overbroad_deltas():
    pre, event, _ = build_recurrence_case(
        case_id="strict-controls", done_object="alphabet_soup_1",
        recurring_object="cream_cheese_1", intermediate_object="tomato_sauce_1",
        recurrence_depth=1,
    )
    expected = expected_next_state(pre, event)
    neutral = neutral_oracle(pre, expected, event)
    neutral["writes"].append({
        "op": "replace", "path": "/pending_restorations", "value": [],
    })
    with pytest.raises(Exception, match="minimum canonical"):
        materialize_neutral(neutral, pre, event, ("alphabet_soup_1",))

    governed = governed_oracle(pre, expected, event)
    unchanged = copy.deepcopy(pre["commitments"][0])
    governed["affected_scope"].append(unchanged["id"])
    governed["affected_scope"].sort()
    governed["forest_delta"].append({"node_id": unchanged["id"], "after": unchanged})
    governed["forest_delta"].sort(key=lambda item: item["node_id"])
    with pytest.raises(Exception, match="scope is not exact"):
        materialize_governed(governed, pre, event, ("alphabet_soup_1",))


def test_occurrence_all_native_contracts_reject_noncanonical_outputs():
    case_id = "strict-five-arm-contracts"
    done = "alphabet_soup_1"
    recurring = "cream_cheese_1"
    pre, event, typed = build_recurrence_case(
        case_id=case_id, done_object=done, recurring_object=recurring,
        intermediate_object="tomato_sauce_1", recurrence_depth=1,
    )
    expected = expected_next_state(pre, event)

    cope = cope_oracle(event)
    cope["extra"] = True
    with pytest.raises(Exception, match="fields are noncanonical"):
        materialize_cope(cope, typed, pre, event, (done,))

    duplicate = cope_oracle(event)
    duplicate["patch_id"] = f"occurrence:{case_id}:genesis:loader"
    with pytest.raises(Exception, match="typed occurrence transition rejected"):
        materialize_cope(duplicate, typed, pre, event, (done,))

    fsr = fsr_oracle(expected)
    fsr["extra"] = True
    with pytest.raises(Exception, match="complete semantic state"):
        materialize_fsr(fsr, pre, event, (done,))

    full = full_replan_oracle(expected, event)
    full["extra"] = True
    with pytest.raises(Exception, match="not occurrence-canonical"):
        materialize_full_replan(full, pre, event, (done,))
