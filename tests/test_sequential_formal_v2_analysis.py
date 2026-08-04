from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

from experiments.sequential_formal_runner import RESULT_FIELDS


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "analyze_sequential_formal_v2", ROOT / "tools" / "analyze_sequential_formal_v2.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def make_rows(manifest):
    rows = []
    for index, sequence in enumerate(manifest):
        for arm in MODULE.ARMS:
            for event_index in (1, 2):
                row = dict.fromkeys(RESULT_FIELDS, "")
                row.update(
                    sequence_id=sequence["sequence_id"], arm=arm,
                    event_index=event_index, substrate_eligible=True,
                    provider_called=True, retry_count=0, parser_valid=True,
                    semantic_valid=True, revision_hash_continuity=True,
                    intermediate_invariant_valid=True, progress_preserved=True,
                    stale_commitment_executed=False, final_intent_satisfied=True,
                    action_budget_respected=True, call_budget_respected=True,
                    proposal_bytes=(100 if arm == "cope" else 200),
                    prompt_tokens=10, completion_tokens=5, latency_seconds=0.1,
                    failure_class="",
                    input_sha256=f"input-{sequence['sequence_id']}-{event_index}",
                    prefix_action_sha256=f"action-{sequence['sequence_id']}",
                    prefix_simulator_sha256=f"sim-{sequence['sequence_id']}",
                )
                if arm == "neutral_patch" and index < 8 and event_index == 2:
                    row["final_intent_satisfied"] = False
                    row["failure_class"] = "synthetic_neutral_failure"
                if arm == "governed_delta" and index < 10 and event_index == 2:
                    row["final_intent_satisfied"] = False
                    row["failure_class"] = "synthetic_governed_failure"
                rows.append(row)
    return rows


def run_analysis(tmp_path, monkeypatch, rows, suffix):
    manifest_path = ROOT / "manifests" / "sequential_formal_40x5x2_v2.csv"
    event_path = tmp_path / f"events-{suffix}.csv"
    with event_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    output = tmp_path / f"out-{suffix}"
    monkeypatch.setattr(sys, "argv", [
        "analyze-v2", "--manifest", str(manifest_path),
        "--event-results", str(event_path), "--output-dir", str(output),
    ])
    assert MODULE.main() == 0
    return output


def test_v2_requires_both_neutral_and_governed_primary_gates(tmp_path, monkeypatch):
    manifest_path = ROOT / "manifests" / "sequential_formal_40x5x2_v2.csv"
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    output = run_analysis(tmp_path, monkeypatch, make_rows(manifest), "pass")
    with (output / "02_COPRIMARY_COMPARISONS.csv").open(newline="", encoding="utf-8") as handle:
        primary = {row["control"]: row for row in csv.DictReader(handle)}
    assert primary["neutral_patch"]["control_gate"] == "True"
    assert primary["governed_delta"]["control_gate"] == "True"
    text = (output / "00_RESULT.md").read_text()
    assert "NECESSARY_GATE_PASS_SINGLE_TASK_ONLY" in text

    tied = make_rows(manifest)
    for row in tied:
        if row["arm"] == "neutral_patch":
            row["final_intent_satisfied"] = True
            row["failure_class"] = ""
    output = run_analysis(tmp_path, monkeypatch, tied, "neutral-tie")
    text = (output / "00_RESULT.md").read_text()
    assert "NO_GO_PRIMARY_NEUTRAL_COMPARISON" in text
    assert "Governed control gate: **True**" in text


def test_claim_status_rejects_governed_tie_even_if_neutral_passes():
    primary = [
        {"control": "neutral_patch", "control_gate": True},
        {"control": "governed_delta", "control_gate": False},
    ]
    assert MODULE.claim_status(
        substrate_complete=True, primary=primary, task_count=1
    ) == "NO_GO_PRIMARY_GOVERNED_COMPARISON"

