from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

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
                    event_index=event_index, task_id=sequence["task_id"],
                    state_id=sequence["state_id"],
                    prefix_orientation=sequence["prefix_orientation"],
                    sequence_type=sequence["sequence_type"], substrate_eligible=True,
                    provider_called=True, retry_count=0, parser_valid=True,
                    semantic_valid=True, revision_hash_continuity=True,
                    intermediate_invariant_valid=True, progress_preserved=True,
                    stale_commitment_executed=False, final_intent_satisfied=True,
                    action_budget_respected=True, call_budget_respected=True,
                    proposal_bytes=(100 if arm == "cope" else 200),
                    prompt_tokens=10, completion_tokens=5, latency_seconds=0.1,
                    failure_class="",
                    input_sha256=hashlib.sha256(f"input-{sequence['sequence_id']}-{event_index}".encode()).hexdigest(),
                    proposal_sha256="a" * 64, response_sha256="b" * 64,
                    logical_before_sha256="c" * 64,
                    logical_after_sha256="d" * 64,
                    prefix_action_sha256=hashlib.sha256(f"action-{sequence['sequence_id']}".encode()).hexdigest(),
                    prefix_simulator_sha256=hashlib.sha256(f"sim-{sequence['sequence_id']}".encode()).hexdigest(),
                )
                if arm == "neutral_patch" and index < 8 and event_index == 2:
                    row["final_intent_satisfied"] = False
                if arm == "governed_delta" and index < 10 and event_index == 2:
                    row["final_intent_satisfied"] = False
                rows.append(row)
    return rows


def run_analysis(tmp_path, monkeypatch, rows, suffix):
    manifest_path = ROOT / "manifests" / "sequential_formal_40x5x2_v2.csv"
    run_dir = tmp_path / f"run-{suffix}"
    run_dir.mkdir()
    event_path = run_dir / "03_EVENT_RESULTS.csv"
    with event_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    (run_dir / "00_RUN_METADATA.txt").write_text(json.dumps({
        "manifest_sha256": MODULE.EXPECTED_MANIFEST_SHA256,
    }) + "\n")
    with (run_dir / "01_EVENT_JOURNAL.txt").open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
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
        substrate_complete=True, infrastructure_valid=True,
        primary=primary, task_count=1
    ) == "NO_GO_PRIMARY_GOVERNED_COMPARISON"


def test_infrastructure_failure_invalidates_an_otherwise_passing_run(tmp_path, monkeypatch):
    manifest_path = ROOT / "manifests" / "sequential_formal_40x5x2_v2.csv"
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    rows = make_rows(manifest)
    rows[0]["failure_class"] = "event1:FormalTransitionError:provider_http_503"
    for field in (
        "parser_valid", "semantic_valid", "revision_hash_continuity",
        "intermediate_invariant_valid", "progress_preserved",
        "final_intent_satisfied", "action_budget_respected",
    ):
        rows[0][field] = False
    rows[0]["proposal_bytes"] = 0
    rows[0]["proposal_sha256"] = ""
    rows[0]["response_sha256"] = ""
    rows[0]["logical_after_sha256"] = ""
    rows[1].update(
        provider_called=False, parser_valid=False, semantic_valid=False,
        revision_hash_continuity=False, intermediate_invariant_valid=False,
        progress_preserved=False, final_intent_satisfied=False,
        action_budget_respected=False, proposal_bytes=0, input_sha256="",
        proposal_sha256="", response_sha256="", logical_before_sha256="",
        logical_after_sha256="", failure_class="dependency_skip_after_event1_failure",
    )
    output = run_analysis(tmp_path, monkeypatch, rows, "infrastructure")
    text = (output / "00_RESULT.md").read_text()
    assert "INVALID_INFRASTRUCTURE_FAILURE" in text
    assert "Infrastructure failures: **1**" in text


def _break_event1_dependency(rows):
    rows[0].update(
        semantic_valid=False, revision_hash_continuity=False,
        intermediate_invariant_valid=False, progress_preserved=False,
        final_intent_satisfied=False, action_budget_respected=False,
        failure_class="synthetic_semantic_failure",
    )


@pytest.mark.parametrize("mutation,match", [
    (lambda rows: rows.pop(), "missing, duplicated, or extra"),
    (lambda rows: rows[0].update(state_id="99"), "metadata drift"),
    (lambda rows: rows[0].update(progress_preserved="garbage"), "boolean is noncanonical"),
    (lambda rows: rows[0].update(prefix_action_sha256=""), "prefix hash drift"),
    (lambda rows: rows[0].update(input_sha256="e" * 64), "common event-1 input drift"),
    (lambda rows: rows[0].update(proposal_sha256=""), "proposal evidence invalid"),
    (lambda rows: rows[0].update(logical_after_sha256=""), "semantic evidence inconsistent"),
    (_break_event1_dependency, "event-2 call dependency"),
])
def test_v2_analysis_rejects_corrupt_or_drifted_results(
    tmp_path, monkeypatch, mutation, match,
):
    manifest_path = ROOT / "manifests" / "sequential_formal_40x5x2_v2.csv"
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        rows = make_rows(list(csv.DictReader(handle)))
    mutation(rows)
    with pytest.raises(ValueError, match=match):
        run_analysis(tmp_path, monkeypatch, rows, "corrupt")
