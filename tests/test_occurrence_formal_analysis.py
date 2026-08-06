from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

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
                input_sha256=MODULE.expected_input_sha256(case),
                proposal_sha256="a" * 64, response_sha256="b" * 64,
                candidate_sha256="c" * 64, failure_class="",
            )
            if arm == "neutral_patch" and index < 8:
                row["canonical_valid"] = False
            if arm == "governed_delta" and index < 10:
                row["canonical_valid"] = False
            rows.append(row)
    return rows


def run(tmp_path, monkeypatch, rows, suffix):
    manifest_path = ROOT / "manifests" / "occurrence_learned_formal_40x5_v1.csv"
    run_dir = tmp_path / f"run-{suffix}"
    run_dir.mkdir()
    result_path = run_dir / "03_EVENT_RESULTS.csv"
    with result_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    (run_dir / "00_RUN_METADATA.txt").write_text(json.dumps({
        "manifest_sha256": MODULE.EXPECTED_MANIFEST_SHA256,
    }) + "\n")
    with (run_dir / "01_EVENT_JOURNAL.txt").open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    with (run_dir / "04_CALL_INTENTS.txt").open("x", encoding="utf-8") as intents, (
        run_dir / "02_PROVIDER_TRACES.txt"
    ).open("x", encoding="utf-8") as responses:
        for row in rows:
            if str(row["provider_called"]).lower() not in {"true", "1", "yes"}:
                continue
            key = {field: row[field] for field in ("sequence_id", "arm", "event_index")}
            intents.write(json.dumps(key, sort_keys=True) + "\n")
            responses.write(json.dumps({**key, "diagnostics": {}}, sort_keys=True) + "\n")
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
    decision = json.loads((tmp_path / "out-pass" / "04_DECISION.txt").read_text())
    assert decision["joint_primary_gate"] is True
    assert decision["secondary_can_rescue"] is False
    for row in rows:
        if row["arm"] == "neutral_patch":
            row["canonical_valid"] = True
    text = run(tmp_path, monkeypatch, rows, "neutral-tie")
    assert "NO_GO_PRIMARY_NEUTRAL_COMPARISON" in text
    decision = json.loads((tmp_path / "out-neutral-tie" / "04_DECISION.txt").read_text())
    assert decision["joint_primary_gate"] is False


def test_occurrence_analysis_invalidates_infrastructure_failure(tmp_path, monkeypatch):
    manifest_path = ROOT / "manifests" / "occurrence_learned_formal_40x5_v1.csv"
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        rows = synthetic(list(csv.DictReader(handle)))
    rows[0]["failure_class"] = "FormalTransitionError:provider_timeout"
    for field in ("parser_valid", "semantic_valid", "canonical_valid", "history_valid", "directive_valid"):
        rows[0][field] = False
    rows[0]["proposal_sha256"] = ""
    rows[0]["candidate_sha256"] = ""
    rows[0]["response_sha256"] = ""
    text = run(tmp_path, monkeypatch, rows, "infra")
    assert "INVALID_INFRASTRUCTURE_FAILURE" in text


def test_two_control_holm_boundary_is_feasible_but_not_two_six_zero_edges():
    weak = MODULE.V1.exact_mcnemar(6, 0)
    strong = MODULE.V1.exact_mcnemar(7, 0)
    assert weak == 0.03125
    assert strong == 0.015625
    adjusted = MODULE.V1.holm({"neutral": weak, "governed": strong})
    assert all(value < 0.05 for value in adjusted.values())
    tied_edges = MODULE.V1.holm({"neutral": weak, "governed": weak})
    assert all(value >= 0.05 for value in tied_edges.values())


def test_occurrence_failure_taxonomy_is_descriptive_and_arm_complete():
    manifest_path = ROOT / "manifests" / "occurrence_learned_formal_40x5_v1.csv"
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        rows = synthetic(list(csv.DictReader(handle)))
    taxonomy = {row["arm"]: row for row in MODULE.failure_taxonomy(rows)}
    assert set(taxonomy) == set(MODULE.ARMS)
    assert taxonomy["cope"]["complete_successes"] == 40
    assert taxonomy["neutral_patch"]["complete_successes"] == 32
    assert taxonomy["governed_delta"]["complete_successes"] == 30
    assert taxonomy["fsr_pc"]["parser_failures"] == 0


@pytest.mark.parametrize("mutation,match", [
    (lambda rows: rows.pop(), "missing, duplicated, or extra"),
    (lambda rows: rows[0].update(input_sha256="d" * 64), "common input drift"),
    (lambda rows: rows[0].update(retry_count=1), "retry detected"),
    (lambda rows: rows[0].update(sequence_id="wrong"), "metadata drift"),
    (lambda rows: rows[0].update(proposal_sha256=""), "proposal evidence invalid"),
    (lambda rows: rows[0].update(candidate_sha256=""), "candidate evidence invalid"),
    (lambda rows: rows[0].update(response_sha256=""), "success evidence inconsistent"),
    (lambda rows: rows[0].update(canonical_valid="garbage"), "boolean is noncanonical"),
    (
        lambda rows: rows[0].update(semantic_valid=False, failure_class="bad_semantics"),
        "invariant/semantic flags inconsistent",
    ),
])
def test_occurrence_analysis_rejects_corrupt_or_drifted_results(
    tmp_path, monkeypatch, mutation, match,
):
    manifest_path = ROOT / "manifests" / "occurrence_learned_formal_40x5_v1.csv"
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        rows = synthetic(list(csv.DictReader(handle)))
    mutation(rows)
    with pytest.raises(ValueError, match=match):
        run(tmp_path, monkeypatch, rows, "corrupt")
