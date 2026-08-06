from __future__ import annotations

import csv
from pathlib import Path

import pytest

from cope.sequential_prompting import ARMS
from experiments.sequential_provider_development_smoke import (
    SMOKE_RESULT_FIELDS,
    summarize_smoke,
)


ROOT = Path(__file__).resolve().parents[1]


def fixture_rows():
    with (ROOT / "manifests" / "sequential_persistence_gate_v2.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        cases = list(csv.DictReader(handle))
    rows = []
    for case in cases:
        for arm in ARMS:
            for event_index in (1, 2):
                row = dict.fromkeys(SMOKE_RESULT_FIELDS, "")
                row.update(
                    case_id=case["case_id"], arm=arm,
                    event_index=event_index, provider_called=True, passed=True,
                    prompt_tokens=1, completion_tokens=1, latency_seconds=0.1,
                )
                rows.append(row)
    return cases, rows


def test_complete_passing_smoke_journal_passes_gate():
    cases, rows = fixture_rows()
    summary = summarize_smoke(cases, rows)
    assert summary == {
        "gate": True,
        "passed_event_cells": 32,
        "result_cells": 32,
        "provider_calls": 32,
    }


def test_incomplete_smoke_journal_is_not_finalizable():
    cases, rows = fixture_rows()
    with pytest.raises(ValueError, match="incomplete"):
        summarize_smoke(cases, rows[:-1])


def test_gate_requires_one_full_sequence_per_arm_and_event_type():
    cases, rows = fixture_rows()
    cancel_cases = {
        case["case_id"] for case in cases
        if case["sequence_type"] == "replace_then_cancel"
    }
    for row in rows:
        if row["arm"] == "neutral_patch" and row["case_id"] in cancel_cases:
            row["passed"] = False
    assert summarize_smoke(cases, rows)["gate"] is False
