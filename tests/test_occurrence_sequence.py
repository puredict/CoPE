from __future__ import annotations

import csv

from experiments import occurrence_restoration_gate as gate


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
