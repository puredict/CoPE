"""CLI integrity integration using temporary unit fixtures, never formal evidence.

Production freeze/model readiness is intentionally stubbed only where a test
must reach a later raw-input failure. No fixtures leave pytest's tmp_path.
"""
import copy
import csv
import hashlib
import json
from pathlib import Path

import pytest

from cope_benchmark.repeated_v2.analysis import CHECKPOINTS, METHODS
import tools.analyze_repeated_interruptions_v2 as cli


@pytest.fixture
def isolated_cli(tmp_path, monkeypatch):
    root = tmp_path / "unit-cli-repository"
    root.mkdir()
    monkeypatch.setattr(cli, "__file__", str(root / "tools" / "analyze_repeated_interruptions_v2.py"))
    git_reads = []
    def git_revision(command, *, cwd, text):
        assert command == ["git", "rev-parse", "HEAD"] and cwd == root and text is True
        git_reads.append(command)
        return "1" * 40 + "\n"
    monkeypatch.setattr(cli.subprocess, "check_output", git_revision)
    return root, git_reads


def snapshot(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def digest(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def json_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True) + "\n")


def jsonl_file(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records))


def temporary_export(root, protocols=("controlled",)):
    """Build deliberately unqualified exports with no raw journal in tmp_path."""
    inputs = root / "unit-inputs"
    inputs.mkdir()
    manifest = [dict(master_episode_id="unit-cli-master", pair_fields={"task_id": 0},
        protocol_prefixes={p: {"event_count": ks[-1], "checkpoints": list(ks)} for p, ks in CHECKPOINTS.items()},
        information_conditions=["evidence_matched"], methods={"non_oracle": list(METHODS), "oracle": []},
        master_schedule_sha256="b" * 64)]
    manifest_path = inputs / "manifest.txt"
    jsonl_file(manifest_path, manifest)
    config_path = inputs / "config.txt"
    json_file(config_path, {"unit_fixture_only": True})
    owner = int(hashlib.sha256(b"unit-cli-master").hexdigest(), 16) % 8
    bundle = dict(status="FROZEN", shard_count=8, bundle_sha256="a" * 64,
        primary_comparator={"method": "full_state_regeneration"}, identities={}, git={"sha": "1" * 40},
        artifacts={"manifest": {"entries": [{"sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()}]},
                   "config": {"entries": [{"path": str(config_path)}]}},
        shards=[dict(shard_id=i, master_episode_ids=["unit-cli-master"] if i == owner else [],
                     manifest_sha256=digest(manifest if i == owner else [])) for i in range(8)])
    freeze_path = inputs / "FREEZE.txt"
    json_file(freeze_path, bundle)
    directories = []
    populated = {}
    for protocol in protocols:
        for index in range(8):
            directory = inputs / f"{protocol}-shard-{index}"
            metadata = dict(protocol=protocol, information_condition="evidence_matched", phase="formal",
                fixture=False, freeze_sha256=bundle["bundle_sha256"], shard_id=index, shard_count=8,
                source_commit=bundle["git"]["sha"], runtime_identities=copy.deepcopy(bundle["identities"]),
                manifest_sha256=bundle["shards"][index]["manifest_sha256"],
                config_sha256=digest({"unit_fixture_only": True}))
            json_file(directory / "00_RUN_METADATA.json", metadata)
            records = []
            if index == owner:
                for method in METHODS:
                    for k in range(CHECKPOINTS[protocol][-1] + 1):
                        records.append(dict(protocol=protocol, information_condition="evidence_matched",
                            master_episode_id="unit-cli-master", method=method, event_index=k,
                            phase="formal", fixture=False, evidence_admissibility="formal", status="COMPLETED",
                            freeze_sha256=bundle["bundle_sha256"], master_schedule_sha256="b" * 64,
                            success=False, high_level_calls=int(k > 0), metrics={
                                "timeout": False, "manual_intervention": False,
                                "wrong_occurrence_execution": [], "hard_constraint_violations": [],
                                "completed_step_regression": False, "required_events_reached": True,
                                "history_corruption": False, "planning_fidelity_exact": 0,
                                "planning_fidelity_macro_f1": 0}))
                populated[protocol] = directory
            jsonl_file(directory / "06_EVENT_RESULTS.jsonl", records)
            directories.append(directory)
    args = ["--freeze", str(freeze_path), "--manifest", str(manifest_path)]
    for directory in directories:
        args += ["--run-dir", str(directory)]
    return inputs, args, populated


def assert_empty_outputs(output, expected_status, captured):
    summary = json.loads(captured.out)
    assert summary["status"] == expected_status and summary["formal_calls"] == 0
    assert f"Decision: **{expected_status}**" in (output / "CLAIM_DECISION.md").read_text()
    assert "No formal performance estimate is available" in (output / "REPORT.md").read_text()
    for table in output.glob("*.csv"):
        with table.open(newline="") as handle:
            assert list(csv.DictReader(handle)) == [], table.name
    assert all(path.suffix in {".md", ".csv", ".txt"} for path in output.iterdir())
    report = json.loads((output / "integrity_report.txt").read_text())
    assert report["provenance"]["formal_calls_by_analyzer"] == 0
    return report


@pytest.mark.parametrize("blocker", [None, "BLOCKED_CALIBRATION_UNAVAILABLE"])
def test_no_formal_input_writes_explicit_blocked_zero_cell_report(isolated_cli, monkeypatch, capsys, blocker):
    root, git_reads = isolated_cli
    def forbidden(*args, **kwargs):
        pytest.fail("blocked zero-input report entered formal validation or statistics")
    for name in ("validate_archived_bundle", "group_formal_shards", "audit_journal_directory",
                 "audit_prompt_parity", "analyze_protocol"):
        monkeypatch.setattr(cli, name, forbidden)
    output = root / "research" / "blocked"
    args = ["--output-dir", str(output)]
    if blocker:
        args += ["--blocker", blocker]
    assert cli.main(args) == 2
    status = blocker or "BLOCKED_FORMAL_EVIDENCE_UNAVAILABLE"
    report = assert_empty_outputs(output, status, capsys.readouterr())
    assert report["analyses"] == []
    assert report["provenance"]["observed_result_cells"] == 0
    assert report["provenance"]["source_files"] == {}
    assert len(git_reads) == 1


def test_run_without_freeze_and_manifest_is_invalid_not_an_observed_failure(isolated_cli, capsys):
    root, _ = isolated_cli
    missing = root / "unavailable-run"
    output = root / "docs" / "invalid"
    assert cli.main(["--run-dir", str(missing), "--output-dir", str(output)]) == 2
    report = assert_empty_outputs(output, "INVALID_RUN", capsys.readouterr())
    assert report["provenance"]["observed_result_cells"] == 0
    assert not missing.exists()


@pytest.mark.parametrize("mutation", ["missing_events", "torn_events", "duplicate_json_key", "nonfinite_json",
    "missing_metadata", "malformed_metadata", "metadata_phase", "metadata_freeze", "manifest_hash",
    "missing_manifest", "missing_freeze", "malformed_freeze", "missing_shard", "duplicate_shard"])
def test_raw_input_failures_preserve_bytes_and_prevent_statistics(isolated_cli, monkeypatch, capsys, mutation):
    root, _ = isolated_cli
    inputs, args, populated = temporary_export(root)
    directory = populated["controlled"]
    events, metadata = directory / "06_EVENT_RESULTS.jsonl", directory / "00_RUN_METADATA.json"
    if mutation == "missing_events": events.unlink()
    if mutation == "torn_events": events.write_text('{"unit_test":true}')
    if mutation == "duplicate_json_key": events.write_text('{"success":false,"success":true}\n')
    if mutation == "nonfinite_json": events.write_text('{"success":NaN}\n')
    if mutation == "missing_metadata": metadata.unlink()
    if mutation == "malformed_metadata": metadata.write_text('{"protocol":\n')
    if mutation in {"metadata_phase", "metadata_freeze"}:
        data = json.loads(metadata.read_text())
        data["phase" if mutation == "metadata_phase" else "freeze_sha256"] = "pilot" if mutation == "metadata_phase" else "c" * 64
        json_file(metadata, data)
    if mutation == "manifest_hash": (inputs / "manifest.txt").write_text('{}\n')
    if mutation == "missing_manifest": (inputs / "manifest.txt").unlink()
    if mutation == "missing_freeze": (inputs / "FREEZE.txt").unlink()
    if mutation == "malformed_freeze": (inputs / "FREEZE.txt").write_text('{invalid}\n')
    if mutation == "missing_shard": args = args[:-2]
    if mutation == "duplicate_shard": args += ["--run-dir", str(directory)]
    before = snapshot(inputs)
    monkeypatch.setattr(cli, "validate_archived_bundle", lambda *args, **kwargs: None)
    def forbidden(*args, **kwargs):
        pytest.fail("malformed raw input reached numerical analysis")
    monkeypatch.setattr(cli, "analyze_protocol", forbidden)
    output = root / "research" / "invalid"
    assert cli.main(args + ["--output-dir", str(output)]) == 2
    assert_empty_outputs(output, "INVALID_RUN", capsys.readouterr())
    assert snapshot(inputs) == before


def test_complete_exports_cannot_replace_missing_immutable_journals(isolated_cli, monkeypatch, capsys):
    root, _ = isolated_cli
    inputs, args, _ = temporary_export(root)
    before = snapshot(inputs)
    monkeypatch.setattr(cli, "validate_archived_bundle", lambda *args, **kwargs: None)
    def forbidden(*args, **kwargs):
        pytest.fail("export-only evidence reached inference without its immutable journal")
    monkeypatch.setattr(cli, "analyze_protocol", forbidden)
    output = root / "research" / "journal-invalid"
    assert cli.main(args + ["--output-dir", str(output)]) == 2
    assert_empty_outputs(output, "INVALID_RUN", capsys.readouterr())
    assert "journal" in (output / "CLAIM_DECISION.md").read_text().lower()
    assert snapshot(inputs) == before


def test_any_invalid_group_prevents_statistics_for_all_submitted_groups(isolated_cli, monkeypatch, capsys):
    root, _ = isolated_cli
    inputs, args, populated = temporary_export(root, protocols=("controlled", "end_to_end"))
    event_path = populated["end_to_end"] / "06_EVENT_RESULTS.jsonl"
    rows = [json.loads(line) for line in event_path.read_text().splitlines()]
    # Missing a nonterminal event retains the master in its shard but breaks the
    # exact continuous-cell inventory. Controlled is complete and comes first.
    rows = [r for r in rows if not (r["method"] == METHODS[0] and r["event_index"] == 3)]
    jsonl_file(event_path, rows)
    before = snapshot(inputs)
    monkeypatch.setattr(cli, "validate_archived_bundle", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "audit_journal_directory", lambda *args, **kwargs: {
        "status": "VALID", "results": copy.deepcopy(kwargs["exported_results"]), "intents": {}})
    monkeypatch.setattr(cli, "audit_prompt_parity", lambda *args, **kwargs: {
        "errors": [], "evidence_parity": True, "reasoner_call_parity": True})
    def forbidden(*args, **kwargs):
        pytest.fail("numerical analysis started before every submitted group passed integrity")
    monkeypatch.setattr(cli, "analyze_protocol", forbidden)
    output = root / "research" / "mixed-invalid"
    assert cli.main(args + ["--output-dir", str(output)]) == 2
    report = assert_empty_outputs(output, "INVALID_RUN", capsys.readouterr())
    assert report["provenance"]["observed_result_cells"] == 111
    assert snapshot(inputs) == before


@pytest.mark.parametrize("field,value", [
    ("source_commit", "2" * 40), ("runtime_identities", {"model_id": "changed"}),
    ("manifest_sha256", "c" * 64), ("config_sha256", "d" * 64),
])
def test_outer_metadata_drift_blocks_before_parity_or_statistics(isolated_cli, monkeypatch, capsys, field, value):
    root, _ = isolated_cli
    inputs, args, populated = temporary_export(root)
    metadata_path = populated["controlled"] / "00_RUN_METADATA.json"
    metadata = json.loads(metadata_path.read_text())
    metadata[field] = value
    json_file(metadata_path, metadata)
    before = snapshot(inputs)
    monkeypatch.setattr(cli, "validate_archived_bundle", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "audit_journal_directory", lambda *args, **kwargs: {
        "status": "VALID", "results": copy.deepcopy(kwargs["exported_results"]), "intents": {}})
    def forbidden(*args, **kwargs):
        pytest.fail("contradictory outer metadata reached parity or numerical analysis")
    monkeypatch.setattr(cli, "audit_prompt_parity", forbidden)
    monkeypatch.setattr(cli, "analyze_protocol", forbidden)
    output = root / "research" / "metadata-invalid"
    assert cli.main(args + ["--output-dir", str(output)]) == 2
    assert_empty_outputs(output, "INVALID_RUN", capsys.readouterr())
    assert snapshot(inputs) == before
