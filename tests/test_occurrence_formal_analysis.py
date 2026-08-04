from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

from experiments.occurrence_formal_runner import RESULT_FIELDS


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("occ_analysis", ROOT / "tools" / "analyze_occurrence_formal.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


def synthetic(manifest):
    rows = []
    for index, case in enumerate(manifest):
        for arm in MODULE.ARMS:
            row = dict.fromkeys(RESULT_FIELDS, "")
            row.update(
                sequence_id=case["case_id"], case_id=case["case_id"], arm=arm,
                event_index=1, triple_index=case["triple_index"],
                recurrence_depth=case["recurrence_depth"], provider_called=True,
                retry_count=0, parser_valid=True, semantic_valid=True,
                canonical_valid=True, history_valid=True, directive_valid=True,
                proposal_bytes=100 if arm == "cope" else 200,
                input_sha256=f"input-{case['case_id']}", failure_class="",
            )
            if arm == "neutral_patch" and index < 8:
                row["canonical_valid"] = False
            if arm == "governed_delta" and index < 10:
                row["canonical_valid"] = False
            rows.append(row)
    return rows


def run(tmp_path, monkeypatch, rows, suffix):
    manifest_path = ROOT / "manifests" / "occurrence_learned_formal_40x5_v1.csv"
    result_path = tmp_path / f"rows-{suffix}.csv"
    with result_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    output = tmp_path / f"out-{suffix}"
    monkeypatch.setattr(sys, "argv", [
        "analyze", "--manifest", str(manifest_path),
        "--event-results", str(result_path), "--output-dir", str(output),
    ])
    assert MODULE.main() == 0
    return (output / "00_RESULT.md").read_text()


def test_occurrence_analysis_requires_both_primary_controls(tmp_path, monkeypatch):
    manifest_path = ROOT / "manifests" / "occurrence_learned_formal_40x5_v1.csv"
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    rows = synthetic(manifest)
    text = run(tmp_path, monkeypatch, rows, "pass")
    assert "NECESSARY_SYMBOLIC_GATE_PASS" in text
    for row in rows:
        if row["arm"] == "neutral_patch":
            row["canonical_valid"] = True
    text = run(tmp_path, monkeypatch, rows, "neutral-tie")
    assert "NO_GO_PRIMARY_NEUTRAL_COMPARISON" in text


def test_occurrence_analysis_invalidates_infrastructure_failure(tmp_path, monkeypatch):
    manifest_path = ROOT / "manifests" / "occurrence_learned_formal_40x5_v1.csv"
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        rows = synthetic(list(csv.DictReader(handle)))
    rows[0]["failure_class"] = "FormalTransitionError:provider_timeout"
    text = run(tmp_path, monkeypatch, rows, "infra")
    assert "INVALID_INFRASTRUCTURE_FAILURE" in text
