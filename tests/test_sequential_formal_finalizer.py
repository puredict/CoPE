from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cope.sequential_prompting import ARMS
from cope.types import canonical_json
from experiments.sequential_formal_runner import RESULT_FIELDS
from tools import analyze_sequential_formal as analyzer
from tools import finalize_sequential_formal_journal as finalizer


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests" / "sequential_formal_40x4x2_v1.csv"


def journal_rows():
    with MANIFEST.open(newline="", encoding="utf-8") as handle:
        sequences = list(csv.DictReader(handle))
    rows = []
    for sequence in sequences:
        for arm in ARMS:
            for event_index in (1, 2):
                row = dict.fromkeys(RESULT_FIELDS, "")
                row.update(
                    sequence_id=sequence["sequence_id"], arm=arm,
                    event_index=event_index, provider_called=True, retry_count=0,
                    substrate_eligible=True, parser_valid=True,
                    semantic_valid=True, revision_hash_continuity=True,
                    intermediate_invariant_valid=True, progress_preserved=True,
                    stale_commitment_executed=False, final_intent_satisfied=True,
                    action_budget_respected=True, call_budget_respected=True,
                    proposal_bytes=(100 if arm == "cope" else 200),
                    prompt_tokens=10, completion_tokens=5, latency_seconds=0.1,
                    input_sha256=f"input-{sequence['sequence_id']}-{event_index}",
                    prefix_action_sha256=f"action-{sequence['sequence_id']}",
                    prefix_simulator_sha256=f"sim-{sequence['sequence_id']}",
                )
                rows.append(row)
    return rows


def run_finalizer(monkeypatch, result_dir: Path):
    def fake_run(command, **kwargs):
        stdout = "test-runtime-commit\n" if "rev-parse" in command else ""
        return SimpleNamespace(stdout=stdout)

    monkeypatch.setattr(finalizer.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys, "argv",
        ["finalize", "--manifest", str(MANIFEST), "--result-dir", str(result_dir)],
    )
    return finalizer.main()


def test_formal_finalizer_derives_exact_complete_table(tmp_path, monkeypatch):
    result_dir = tmp_path / "complete"
    result_dir.mkdir()
    (result_dir / "01_EVENT_JOURNAL.txt").write_text(
        "".join(canonical_json(row) + "\n" for row in journal_rows()),
        encoding="utf-8",
    )
    assert run_finalizer(monkeypatch, result_dir) == 0
    assert len((result_dir / "03_EVENT_RESULTS.csv").read_text().splitlines()) == 321
    status = json.loads((result_dir / "00_STATUS.txt").read_text())
    assert status["result_cells"] == 320
    assert status["provider_calls"] == 320
    assert status["journal_recovery"] is True
    analysis_dir = tmp_path / "analysis"
    monkeypatch.setattr(
        sys, "argv",
        [
            "analyze", "--manifest", str(MANIFEST),
            "--event-results", str(result_dir / "03_EVENT_RESULTS.csv"),
            "--output-dir", str(analysis_dir),
        ],
    )
    assert analyzer.main() == 0
    assert (analysis_dir / "00_RESULT.md").is_file()


def test_formal_finalizer_rejects_partial_table_without_outputs(tmp_path, monkeypatch):
    result_dir = tmp_path / "partial"
    result_dir.mkdir()
    (result_dir / "01_EVENT_JOURNAL.txt").write_text(
        "".join(canonical_json(row) + "\n" for row in journal_rows()[:-1]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="incomplete"):
        run_finalizer(monkeypatch, result_dir)
    assert not (result_dir / "03_EVENT_RESULTS.csv").exists()
    assert not (result_dir / "00_STATUS.txt").exists()
