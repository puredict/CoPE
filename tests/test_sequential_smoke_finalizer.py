from __future__ import annotations

import csv
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cope.sequential_prompting import ARMS
from cope.types import canonical_json
from experiments.sequential_provider_development_smoke import SMOKE_RESULT_FIELDS
from tools import finalize_sequential_provider_smoke_journal as finalizer


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests" / "sequential_persistence_gate_v2.csv"


def journal_rows():
    with MANIFEST.open(newline="", encoding="utf-8") as handle:
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
    return rows


def run_finalizer(monkeypatch, result_dir: Path):
    monkeypatch.setattr(
        finalizer.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=""),
    )
    monkeypatch.setattr(
        sys, "argv",
        ["finalize", "--case-manifest", str(MANIFEST), "--result-dir", str(result_dir)],
    )
    return finalizer.main()


def test_finalizer_derives_complete_smoke_without_rerun(tmp_path, monkeypatch):
    result_dir = tmp_path / "complete"
    result_dir.mkdir()
    (result_dir / "01_JOURNAL.txt").write_text(
        "".join(canonical_json(row) + "\n" for row in journal_rows()),
        encoding="utf-8",
    )
    assert run_finalizer(monkeypatch, result_dir) == 0
    assert len((result_dir / "02_RESULTS.csv").read_text(encoding="utf-8").splitlines()) == 33
    assert "Recovery: derived from a complete retained" in (
        result_dir / "03_RESULT.md"
    ).read_text(encoding="utf-8")


def test_finalizer_rejects_partial_smoke_journal(tmp_path, monkeypatch):
    result_dir = tmp_path / "partial"
    result_dir.mkdir()
    (result_dir / "01_JOURNAL.txt").write_text(
        "".join(canonical_json(row) + "\n" for row in journal_rows()[:-1]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="incomplete"):
        run_finalizer(monkeypatch, result_dir)
    assert not (result_dir / "02_RESULTS.csv").exists()
    assert not (result_dir / "03_RESULT.md").exists()
