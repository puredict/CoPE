"""Synthetic unit fixtures qualify freeze logic; these are never formal evidence."""

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from cope_benchmark.repeated_v2.freeze import (
    COMPARATORS, IDENTITY_COMPONENTS, NON_ORACLE_METHODS, REQUIRED_ARTIFACTS,
    REQUIRED_CHECKS, FreezeBlocked, ProtocolDrift, artifact_inventory,
    audit_journal_directory,
    build_freeze_bundle, deterministic_shards, formal_call_guard,
    select_primary_comparator, validate_frozen_bundle, write_freeze_artifacts,
    validate_archived_bundle,
    validate_static_frozen_bundle,
)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def raw_journal(root, identities, protocol, count, *, phase="pilot", freeze=None,
                methods=NON_ORACLE_METHODS, master=None, seed=999, development=False):
    """Write explicit synthetic envelopes for read-only journal auditor tests."""
    root.mkdir(parents=True, exist_ok=True)
    def envelope(path, kind, payload, key=None, label=None):
        body = {"schema": "cope-repeated-v2-journal-1", "kind": kind, "payload": payload}
        if key is not None:
            body["key"] = dict(zip(("protocol", "master_episode_id", "method", "event_index"), key))
        if label:
            body["label"] = label
        body["sha256"] = digest(body)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, sort_keys=True) + "\n")
    metadata = freeze or {"phase": phase, "fixture": False, "identities": identities}
    envelope(root / "frozen_metadata.json", "metadata", metadata)
    for name in ("intents", "responses", "results", "episodes", "snapshots"):
        (root / name).mkdir(exist_ok=True)
    result_payloads = []
    for method in methods:
        for index in range(count + 1):
            key = (protocol, master or f"pilot-{protocol}", method, index)
            filename = digest(list(key)) + ".json"
            called = index > 0 and method not in {"classical_execution_monitor", "oracle_persistent_update"}
            if called:
                request = {"messages": [{"role": "user", "content": "synthetic unit fixture"}],
                           "config": {"provider": identities["reasoner"]["provider_id"], "model": identities["reasoner"]["model_id"],
                                      "temperature": 0, "semantic_retries": 0}}
                envelope(root / "intents" / filename, "intent", {"request": request, "request_sha256": digest(request)}, key)
                envelope(root / "responses" / filename, "response", {"response": {"text": "unit response", "fixture": False}, "request_sha256": digest(request)}, key)
            success = method == "full_history_replan" if development else True
            result = {"protocol": protocol, "master_episode_id": key[1], "method": method, "event_index": index,
                      "phase": phase, "fixture": False, "status": "COMPLETED", "success": success,
                      "final_active_task_success_after_last_event": success, "high_level_calls": int(called),
                      "history_corruption": 0,
                      "information_condition": "evidence_matched", "freeze_sha256": freeze.get("bundle_sha256") if freeze else None}
            if method == "oracle_persistent_update":
                result.update(privileged=True, evidence_admissibility="diagnostic_oracle")
            envelope(root / "results" / filename, "result", result, key)
            snapshot = {"index": index, "pending_result": result, "identity": {"initial_state_id": 0, "seed": seed}}
            envelope(root / "snapshots" / "completed" / filename, "snapshot", snapshot, key, "completed")
            result_payloads.append(result)
        episode_key = (protocol, master or f"pilot-{protocol}", method, 0)
        episode = {k: v for k, v in result.items() if k != "event_index"}
        envelope(root / "episodes" / (digest(list(episode_key)) + ".json"), "episode", episode, episode_key)
    return result_payloads


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    # Only the upstream design is isolated here; the public freeze API has no
    # allow_synthetic or gate bypass option. Integration tests use phase-1 code.
    def synthetic_design(root, config, catalog, manifest):
        return catalog, {"unique_master_sessions": len(manifest), "information_conditions": ["evidence_matched", "token_matched"],
                         "per_condition": {"by_protocol": {"controlled": {"non_oracle_event_cells": len(manifest) * 64}}}}
    monkeypatch.setattr("cope_benchmark.repeated_v2.freeze._validate_upstream_design", synthetic_design)
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "freeze-unit@example.invalid")
    git(root, "config", "user.name", "Freeze Unit Fixture")
    artifacts = {}
    for role in REQUIRED_ARTIFACTS:
        path = root / "research" / "fixture" / f"{role}.txt"
        write(path, {"unit_fixture_only": role})
        artifacts[role] = str(path)
    for role in ("pilot_controlled_journals", "pilot_end_to_end_journals", "development_traces"):
        path = root / "research" / "fixture" / role
        path.mkdir()
        write(path / "before_fixture.txt", {})
        artifacts[role] = str(path)
    test_source = Path(artifacts["gate_tests"])
    test_source.write_text("def test_qualified_contract():\n    assert True\n")
    Path(artifacts["junit_report"]).write_text('<testsuite tests="1" failures="0" errors="0"><testcase name="test_qualified_contract"/></testsuite>')
    config = {
        "methods": {"non_oracle": list(NON_ORACLE_METHODS)},
        "task_selection": {"formal_state_ids": [0, 1, 2, 3, 4], "formal_policy_seeds": [11, 29, 47],
                           "calibration_state_ids": [0, 1, 2, 3, 4], "calibration_policy_seeds": [101, 131],
                           "clean_success_interval": [0.40, 0.95], "forbid_selection_by_method_difference": True},
        "primary_analysis": {"protocol": "end_to_end", "checkpoint": 4, "success_margin_vs_nonpersistent": 0.10,
                             "generic_noninferiority_margin": -0.05, "bootstrap_replicates": 10000, "alpha": 0.05,
                             "multiple_testing": "holm", "cluster_unit": "master_episode_id"},
        "reasoner": {"semantic_retries": 0, "calls_per_event": 1, "record_exact_prompts": True},
        "protocols": {"controlled": {"event_count": 8, "checkpoints": [0, 1, 2, 4, 8]},
                      "end_to_end": {"event_count": 4, "checkpoints": [0, 1, 2, 4]}},
    }
    write(Path(artifacts["config"]), config)
    write(Path(artifacts["catalog"]), [{"task_id": str(i)} for i in range(8)])
    manifest = [{"master_episode_id": f"t{task}s{state}p{seed}", "task_id": str(task),
                 "initial_state_id": state, "policy_seed": seed, "master_event_schedule": list(range(8))}
                for task in range(8) for state in range(5) for seed in [11, 29, 47]]
    write(Path(artifacts["manifest"]), manifest)
    inventory = artifact_inventory(root, artifacts)
    identities = {component: {"provider_id": f"qualified_{component}", "version": "revision-123",
                             "implementation_sha256": inventory[f"{component}_implementation"]["sha256"]}
                  for component in IDENTITY_COMPONENTS}
    for component in ("reasoner", "vla"):
        identities[component].update(model_id="qualified_model", model_revision="revision-123", model_sha256="a" * 64,
                                     model_digest_provenance="Unit fixture for digest binding; never production evidence")
    identities["vla"].update(learned_policy=True, uses_privileged_state=False,
                              checkpoint_sha256=inventory["vla_checkpoint"]["entries"][0]["sha256"])
    calibration = [{"task_id": str(task), "initial_state_id": state, "policy_seed": seed,
                    "success": state < 3, "phase": "calibration", "learned_policy": True,
                    "uses_privileged_state": False, "checkpoint_sha256": identities["vla"]["checkpoint_sha256"],
                    "provider_id": identities["vla"]["provider_id"],
                    "trace_sha256": inventory["calibration_traces"]["entries"][0]["sha256"]}
                   for task in range(8) for state in range(5) for seed in [101, 131]]
    write(Path(artifacts["calibration_records"]), calibration)
    development_root = Path(artifacts["development_traces"])
    raw_journal(development_root, identities, "end_to_end", 4, phase="development", methods=COMPARATORS,
                master="development-master", seed=777, development=True)
    development_digest = artifact_inventory(root, {"development_traces": development_root})["development_traces"]["entries"][0]["sha256"]
    development = [{"master_episode_id": "development-master", "task_id": "0", "initial_state_id": 0,
                    "policy_seed": 777, "phase": "development", "protocol": "end_to_end", "checkpoint": 4,
                    "method": method, "success": method == "full_history_replan", "history_corruption": 0,
                    "runtime_identities": identities, "fixture": False, "information_condition": "evidence_matched",
                    "trace_sha256": development_digest} for method in COMPARATORS]
    write(Path(artifacts["development_records"]), development)
    for protocol, count in (("controlled", 8), ("end_to_end", 4)):
        journal_root = Path(artifacts[f"pilot_{protocol}_journals"])
        raw_journal(journal_root, identities, protocol, count)
        journal_digest = artifact_inventory(root, {"journal": str(journal_root)})["journal"]["entries"][0]["sha256"]
        records = [{"master_episode_id": f"pilot-{protocol}", "task_id": "0", "initial_state_id": 0,
                    "policy_seed": 999, "phase": "pilot", "protocol": protocol, "status": "COMPLETE", "method": method,
                    "event_indices": list(range(1, count + 1)), "integrity_status": "VALID", "missing_cells": 0,
                    "duplicate_cells": 0, "unexpected_cells": 0, "reasoner_provider_id": identities["reasoner"]["provider_id"],
                    "reasoner_model_revision": identities["reasoner"]["model_revision"],
                    "journal_sha256": journal_digest,
                    "runtime_identities": identities, "fixture": False, "information_condition": "evidence_matched",
                    "checkpoint_sha256": identities["vla"]["checkpoint_sha256"], "learned_policy": True,
                    "uses_privileged_state": False} for method in NON_ORACLE_METHODS]
        write(Path(artifacts[f"pilot_{protocol}_records"]), records)
    git(root, "add", ".")
    git(root, "commit", "-qm", "synthetic source fixture")
    sha = git(root, "rev-parse", "HEAD")

    def refresh_audit():
        inventory = artifact_inventory(root, artifacts)
        report = {"schema_version": "repeated_v2_gate_evidence_v1", "provenance": {
            "producer_git_sha": sha, "producer_command": ["python", "-m", "pytest", "synthetic-unit-only"]},
            "checks": {check: ["test_qualified_contract"] for check in REQUIRED_CHECKS},
            "input_sha256": {k: v["sha256"] for k, v in inventory.items() if k != "gate_report"}}
        write(Path(artifacts["gate_report"]), report)
        git(root, "add", ".")
        git(root, "commit", "-qm", "synthetic audit evidence")

    refresh_audit()
    return {"repo_root": root, "artifact_paths": artifacts, "identities": identities, "phase3_sha": sha}, refresh_audit


def test_build_freeze_and_deterministic_shards(evidence):
    kwargs, _ = evidence
    bundle = build_freeze_bundle(**kwargs)
    assert bundle["primary_comparator"]["method"] == "full_history_replan"
    assert bundle["expected_counts"]["unique_master_sessions"] == 120
    assert bundle["expected_counts"]["per_condition"]["by_protocol"]["controlled"]["non_oracle_event_cells"] == 7680
    assert len(bundle["shards"]) == 8
    validate_frozen_bundle(bundle, current_identity=lambda: kwargs["identities"])
    manifest = json.loads(Path(kwargs["artifact_paths"]["manifest"]).read_text())
    expanded = [dict(r, method=m, checkpoint=k) for r in manifest for m in NON_ORACLE_METHODS for k in [0, 1, 2, 4, 8]]
    shards = deterministic_shards(expanded)
    assert shards == deterministic_shards(list(reversed(expanded)))
    owners = {}
    for shard_id, shard in enumerate(shards):
        for row in shard:
            assert owners.setdefault(row["master_episode_id"], shard_id) == shard_id
    assert len(owners) == 120


def test_missing_dependencies_and_boolean_gate_never_authorize(tmp_path, evidence):
    with pytest.raises(FreezeBlocked, match="MISSING_FREEZE_ARTIFACTS"):
        build_freeze_bundle(repo_root=tmp_path, artifact_paths={}, identities={}, phase3_sha="a" * 40)
    kwargs, _ = evidence
    write(Path(kwargs["artifact_paths"]["gate_report"]), {"passed": True})
    git(kwargs["repo_root"], "add", ".")
    git(kwargs["repo_root"], "commit", "-qm", "invalid boolean report")
    with pytest.raises(FreezeBlocked, match="gate evidence schema"):
        build_freeze_bundle(**kwargs)


def test_mutated_artifact_and_identity_rejected(evidence):
    kwargs, _ = evidence
    bundle = build_freeze_bundle(**kwargs)
    changed = copy.deepcopy(kwargs["identities"])
    changed["reasoner"]["model_revision"] = "revision-124"
    with pytest.raises(ProtocolDrift, match="identity drift"):
        validate_frozen_bundle(bundle, current_identity=lambda: changed)
    Path(kwargs["artifact_paths"]["prompts"]).write_text("mutated prompt")
    with pytest.raises(ProtocolDrift):
        validate_frozen_bundle(bundle, current_identity=lambda: kwargs["identities"])


def test_mutation_during_validation_stops_before_call(evidence):
    kwargs, _ = evidence
    bundle = build_freeze_bundle(**kwargs)
    calls = []
    def live_identity():
        Path(kwargs["artifact_paths"]["schemas"]).write_text("mutation inside identity callback")
        return kwargs["identities"]
    with pytest.raises(ProtocolDrift, match="during live identity"):
        with formal_call_guard(bundle, current_identity=live_identity):
            calls.append("should-never-run")
    assert calls == []


def test_post_call_drift_keeps_observed_response(evidence):
    kwargs, _ = evidence
    bundle = build_freeze_bundle(**kwargs)
    responses = []
    with pytest.raises(ProtocolDrift):
        with formal_call_guard(bundle, current_identity=lambda: kwargs["identities"]):
            responses.append({"id": "actual-response-must-be-retained"})
            Path(kwargs["artifact_paths"]["config"]).write_text("changed during call")
    assert len(responses) == 1


def test_freeze_bundle_and_git_mutations_rejected(evidence):
    kwargs, _ = evidence
    bundle = build_freeze_bundle(**kwargs)
    tampered = copy.deepcopy(bundle)
    tampered["primary_comparator"]["method"] = "rag_replan"
    with pytest.raises(ProtocolDrift, match="digest mismatch"):
        validate_frozen_bundle(tampered, current_identity=lambda: kwargs["identities"])
    git(kwargs["repo_root"], "commit", "--allow-empty", "-qm", "post-freeze commit")
    with pytest.raises(ProtocolDrift, match="git SHA"):
        validate_frozen_bundle(bundle, current_identity=lambda: kwargs["identities"])


@pytest.mark.parametrize("mutation", ["calibration_missing", "pilot_missing", "dev_overlap", "test_failure", "raw_hash_only"])
def test_upstream_evidence_failures_block(evidence, mutation):
    kwargs, refresh = evidence
    artifacts = kwargs["artifact_paths"]
    if mutation == "calibration_missing":
        path = Path(artifacts["calibration_records"])
        rows = json.loads(path.read_text())
        write(path, rows[:-1])
    elif mutation == "pilot_missing":
        path = Path(artifacts["pilot_end_to_end_records"])
        write(path, json.loads(path.read_text())[:-1])
    elif mutation == "dev_overlap":
        path = Path(artifacts["development_records"])
        rows = json.loads(path.read_text())
        for row in rows:
            row["policy_seed"] = 11
        write(path, rows)
    elif mutation == "test_failure":
        Path(artifacts["junit_report"]).write_text('<testsuite><testcase name="test_qualified_contract"><failure/></testcase></testsuite>')
    else:
        path = Path(artifacts["calibration_records"])
        rows = json.loads(path.read_text())
        rows[0]["trace_sha256"] = "b" * 64
        write(path, rows)
    refresh()
    with pytest.raises(FreezeBlocked):
        build_freeze_bundle(**kwargs)


def test_shards_reject_duplicates_and_wrong_count():
    row = {"master_episode_id": "m", "method": "cope_typed_edit", "checkpoint": 4}
    with pytest.raises(FreezeBlocked, match="duplicate"):
        deterministic_shards([row, row])
    with pytest.raises(FreezeBlocked, match="exactly 8"):
        deterministic_shards([row], shard_count=7)


def test_comparator_tie_break_and_incomplete_pairing():
    rows = [{"master_episode_id": "m", "task_id": "t", "initial_state_id": 0, "policy_seed": 999,
             "phase": "development", "protocol": "end_to_end", "checkpoint": 4, "success": True,
             "history_corruption": 1 if method == "classical_execution_monitor" else 0, "method": method}
            for method in COMPARATORS]
    assert select_primary_comparator(rows)["method"] == "full_history_replan"
    with pytest.raises(FreezeBlocked, match="incomplete paired"):
        select_primary_comparator(rows[:-1])


def test_writes_exactly_eight_shards_without_overwrite(evidence):
    kwargs, _ = evidence
    bundle = build_freeze_bundle(**kwargs)
    output = kwargs["repo_root"] / "research" / "frozen"
    paths = write_freeze_artifacts(bundle, output_dir=output)
    assert len(paths) == 9
    assert {Path(p).suffix for p in paths} == {".txt", ".csv"}
    with pytest.raises(FreezeBlocked, match="overwrite"):
        write_freeze_artifacts(bundle, output_dir=output)
    validate_frozen_bundle(bundle, current_identity=lambda: kwargs["identities"])


@pytest.mark.parametrize("content,suffix", [
    ('{"a":1}\n{"a":2}', ".txt"),
    ('{"a":1}\n\n{"a":2}\n', ".txt"),
    ('{"a":1}\n{"a":NaN}\n', ".txt"),
    ('{"a":1}\n{"a":1e999}\n', ".txt"),
    ('{"a":1,"a":2}', ".txt"),
    ('a: 1\na: 2\n', ".yaml"),
    ('a: .nan\n', ".yaml"),
])
def test_torn_nonfinite_or_duplicate_input_rejected(tmp_path, content, suffix):
    from cope_benchmark.repeated_v2.freeze import _load
    path = tmp_path / f"bad{suffix}"
    path.write_text(content)
    with pytest.raises((FreezeBlocked, ValueError)):
        _load(path)


def test_real_upstream_catalog_cannot_be_replaced_with_a_pass_boolean(tmp_path):
    from cope_benchmark.repeated_v2.freeze import _validate_upstream_design
    with pytest.raises(FreezeBlocked):
        _validate_upstream_design(tmp_path, {}, {"passed": True}, [])


def test_nested_phase1_pair_fields_and_conflict_rejected():
    row = {"master_episode_id": "m", "pair_fields": {"task_id": 1, "initial_state_id": 0, "policy_seed": 11}}
    shards = deterministic_shards([dict(row, method=m) for m in NON_ORACLE_METHODS])
    assert len([s for s in shards if s]) == 1
    changed = copy.deepcopy(row)
    changed["pair_fields"]["policy_seed"] = 29
    with pytest.raises(FreezeBlocked, match="inconsistent master"):
        deterministic_shards([row, changed])


def resign(path, mutate):
    value = json.loads(path.read_text())
    mutate(value)
    value.pop("sha256")
    value["sha256"] = digest(value)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")


@pytest.mark.parametrize("mutation", ["missing_result", "ambiguous_call", "false_summary", "missing_snapshot",
                                      "wrong_provider", "fixture_response", "wrong_seed"])
def test_raw_pilot_corruption_blocks_even_with_refreshed_summary_and_audit(evidence, mutation):
    kwargs, refresh = evidence
    artifacts = kwargs["artifact_paths"]
    root = Path(artifacts["pilot_end_to_end_journals"])
    key = ("end_to_end", "pilot-end_to_end", "cope_typed_edit", 1)
    filename = digest(list(key)) + ".json"
    if mutation == "missing_result":
        (root / "results" / filename).rename(root / "retained_result.txt")
    elif mutation == "ambiguous_call":
        (root / "responses" / filename).rename(root / "retained_response.txt")
    elif mutation == "false_summary":
        resign(root / "results" / filename, lambda value: value["payload"].update(success=False, final_active_task_success_after_last_event=False))
    elif mutation == "missing_snapshot":
        (root / "snapshots" / "completed" / filename).rename(root / "retained_snapshot.txt")
    elif mutation == "wrong_provider":
        def change_request(value):
            value["payload"]["request"]["config"]["model"] = "another-model"
            value["payload"]["request_sha256"] = digest(value["payload"]["request"])
        resign(root / "intents" / filename, change_request)
        request_digest = json.loads((root / "intents" / filename).read_text())["payload"]["request_sha256"]
        resign(root / "responses" / filename, lambda value: value["payload"].update(request_sha256=request_digest))
    elif mutation == "fixture_response":
        resign(root / "responses" / filename, lambda value: value["payload"]["response"].update(fixture=True))
    else:
        initial_key = (*key[:3], 0)
        resign(root / "snapshots" / "completed" / (digest(list(initial_key)) + ".json"),
               lambda value: value["payload"]["identity"].update(seed=11))
    journal_digest = artifact_inventory(kwargs["repo_root"], {"journal": str(root)})["journal"]["entries"][0]["sha256"]
    path = Path(artifacts["pilot_end_to_end_records"])
    rows = json.loads(path.read_text())
    for row in rows:
        row["journal_sha256"] = journal_digest
    write(path, rows)
    refresh()
    with pytest.raises(FreezeBlocked):
        build_freeze_bundle(**kwargs)


@pytest.mark.parametrize("field,value", [("learned_policy", False), ("uses_privileged_state", True),
                                         ("model_id", "different-model"), ("checkpoint_sha256", "c" * 64),
                                         ("provider_id", "oracle_policy")])
def test_development_requires_same_production_policy(evidence, field, value):
    kwargs, refresh = evidence
    path = Path(kwargs["artifact_paths"]["development_records"])
    rows = json.loads(path.read_text())
    rows[0]["runtime_identities"]["vla"][field] = value
    write(path, rows)
    refresh()
    with pytest.raises(FreezeBlocked, match="development runtime identity"):
        build_freeze_bundle(**kwargs)


def test_read_only_audit_binds_export_and_preserves_bytes(evidence):
    kwargs, _ = evidence
    directory = Path(kwargs["artifact_paths"]["pilot_end_to_end_journals"])
    expected = [("end_to_end", "pilot-end_to_end", method, index) for method in NON_ORACLE_METHODS for index in range(5)]
    before = artifact_inventory(kwargs["repo_root"], {"journal": directory})
    audit = audit_journal_directory(directory, expected_cells=expected, expected_phase="pilot", identities=kwargs["identities"])
    assert audit["status"] == "VALID" and audit["result_count"] == 40
    audit_journal_directory(directory, expected_cells=expected, expected_phase="pilot", identities=kwargs["identities"], exported_results=audit["results"])
    altered = copy.deepcopy(audit["results"])
    altered[0]["success"] = False
    with pytest.raises(FreezeBlocked, match="exported results"):
        audit_journal_directory(directory, expected_cells=expected, expected_phase="pilot", identities=kwargs["identities"], exported_results=altered)
    assert artifact_inventory(kwargs["repo_root"], {"journal": directory}) == before


def test_hf_symlink_checkpoint_and_external_implementation_are_hashed_in_place(tmp_path):
    repo, cache, installed = (tmp_path / name for name in ("repo", "cache", "installed"))
    repo.mkdir()
    snapshot, blobs = cache / "snapshots" / "pinned-revision", cache / "blobs"
    snapshot.mkdir(parents=True)
    blobs.mkdir()
    installed.mkdir()
    (blobs / "weight-a").write_bytes(b"original-checkpoint")
    (blobs / "weight-b").write_bytes(b"original-checkpoint")
    (snapshot / "model.safetensors").symlink_to("../../blobs/weight-a")
    (installed / "client.py").write_text("# installed implementation\n")
    alias = tmp_path / "checkpoint-alias"
    alias.symlink_to(snapshot, target_is_directory=True)
    paths = {"vla_checkpoint": alias, "vla_implementation": installed}
    before = artifact_inventory(repo, paths)
    entry = before["vla_checkpoint"]["entries"][0]
    assert len(entry["symlinks"]) == 2 and entry["resolved_path"] == str(snapshot)
    expected = hashlib.sha256(b"model.safetensors\0" + hashlib.sha256(b"original-checkpoint").digest()).hexdigest()
    assert entry["sha256"] == expected
    (snapshot / "replacement").symlink_to("../../blobs/weight-b")
    (snapshot / "replacement").replace(snapshot / "model.safetensors")
    relinked = artifact_inventory(repo, paths)
    assert relinked["vla_checkpoint"]["entries"][0]["sha256"] == entry["sha256"]
    assert relinked != before  # Same bytes, distinct link mapping is still drift.
    (blobs / "weight-b").write_bytes(b"changed-checkpoint")
    assert artifact_inventory(repo, paths)["vla_checkpoint"]["entries"][0]["sha256"] != entry["sha256"]


def test_symlink_directory_cycle_and_missing_target_fail_closed(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    checkpoint = root / "checkpoint"
    checkpoint.mkdir()
    (checkpoint / "weights").write_bytes(b"bytes")
    (checkpoint / "cycle").symlink_to(checkpoint, target_is_directory=True)
    with pytest.raises(FreezeBlocked, match="cycle"):
        artifact_inventory(root, {"vla_checkpoint": checkpoint})
    dangling = root / "dangling"
    dangling.symlink_to(root / "absent")
    with pytest.raises(FreezeBlocked):
        artifact_inventory(root, {"vla_checkpoint": dangling})


def test_empty_formal_shard_requires_empty_journal_and_verified_metadata(evidence):
    kwargs, _ = evidence
    bundle = build_freeze_bundle(**kwargs)
    directory = kwargs["repo_root"] / "research" / "empty_formal_shard" / "journal"
    directory.mkdir(parents=True)
    for name in ("intents", "responses", "results", "episodes", "snapshots"):
        (directory / name).mkdir()
    record = {"schema": "cope-repeated-v2-journal-1", "kind": "metadata", "payload": bundle}
    record["sha256"] = digest(record)
    (directory / "frozen_metadata.json").write_text(json.dumps(record) + "\n")
    audit = audit_journal_directory(directory, expected_cells=[], expected_phase="formal",
                                     identities=kwargs["identities"], freeze_sha256=bundle["bundle_sha256"])
    assert audit["results"] == [] and audit["result_count"] == 0
    with pytest.raises(FreezeBlocked, match="expected frozen bundle"):
        audit_journal_directory(directory, expected_cells=[], expected_phase="formal", freeze_sha256="a" * 64)


def test_freeze_cli_malformed_artifact_map_is_blocked_without_calls(tmp_path, capsys):
    from tools.freeze_repeated_interruptions_v2 import main
    repo = tmp_path / "repo"
    repo.mkdir()
    bad_map = tmp_path / "bad-map.txt"
    write(bad_map, [])
    code = main(["--repo-root", str(repo), "--phase3-sha", "a" * 40, "--config", "missing.txt",
                 "--task-catalog", "missing.txt", "--manifest", "missing.txt", "--artifact-map", str(bad_map),
                 "--output-dir", "research/blocked"])
    assert code == 2
    response = json.loads(capsys.readouterr().out)
    assert response["formal_calls"] == 0 and response["status"] == "BLOCKED_FORMAL_FREEZE"
    assert (repo / "research" / "blocked" / "BLOCKED_FREEZE.txt").is_file()


@pytest.mark.parametrize("mutation", ["success", "corruption", "missing_raw_metric"])
def test_development_selection_uses_raw_k4_outcomes(evidence, mutation):
    kwargs, refresh = evidence
    artifacts = kwargs["artifact_paths"]
    summary_path = Path(artifacts["development_records"])
    summaries = json.loads(summary_path.read_text())
    if mutation == "success":
        summaries[0]["success"] = not summaries[0]["success"]
    elif mutation == "corruption":
        summaries[0]["history_corruption"] = 100
    else:
        directory = Path(artifacts["development_traces"])
        key = ("end_to_end", "development-master", summaries[0]["method"], 4)
        filename = digest(list(key)) + ".json"
        resign(directory / "results" / filename, lambda value: value["payload"].pop("history_corruption"))
        resign(directory / "snapshots" / "completed" / filename,
               lambda value: value["payload"]["pending_result"].pop("history_corruption"))
        new_digest = artifact_inventory(kwargs["repo_root"], {"development_traces": directory})["development_traces"]["entries"][0]["sha256"]
        for summary in summaries:
            summary["trace_sha256"] = new_digest
    write(summary_path, summaries)
    refresh()
    with pytest.raises(FreezeBlocked, match="development summary/raw|DEVELOPMENT_TRACE_SCHEMA_UNAVAILABLE"):
        build_freeze_bundle(**kwargs)


def test_retained_oracle_and_noncomparator_arms_are_audited_without_selection(evidence):
    kwargs, refresh = evidence
    artifacts = kwargs["artifact_paths"]
    for protocol, count in (("controlled", 8), ("end_to_end", 4)):
        directory = Path(artifacts[f"pilot_{protocol}_journals"])
        raw_journal(directory, kwargs["identities"], protocol, count, methods=("oracle_persistent_update",))
        new_digest = artifact_inventory(kwargs["repo_root"], {"journal": directory})["journal"]["entries"][0]["sha256"]
        path = Path(artifacts[f"pilot_{protocol}_records"])
        summaries = json.loads(path.read_text())
        for summary in summaries:
            summary["journal_sha256"] = new_digest
        write(path, summaries)
    directory = Path(artifacts["development_traces"])
    raw_journal(directory, kwargs["identities"], "end_to_end", 4, phase="development", master="development-master",
                methods=("cope_typed_edit", "generic_persistent_edit", "oracle_persistent_update"), seed=777, development=True)
    new_digest = artifact_inventory(kwargs["repo_root"], {"development_traces": directory})["development_traces"]["entries"][0]["sha256"]
    path = Path(artifacts["development_records"])
    summaries = json.loads(path.read_text())
    for summary in summaries:
        summary["trace_sha256"] = new_digest
    write(path, summaries)
    refresh()
    bundle = build_freeze_bundle(**kwargs)
    assert bundle["primary_comparator"]["method"] == "full_history_replan"
    assert {row["method"] for row in bundle["primary_comparator"]["ranking"]} == set(COMPARATORS)
    key = ("end_to_end", "development-master", "oracle_persistent_update", 4)
    filename = digest(list(key)) + ".json"
    resign(directory / "results" / filename, lambda value: value["payload"].update(privileged=False))
    with pytest.raises(ProtocolDrift):
        validate_frozen_bundle(bundle, current_identity=lambda: kwargs["identities"])


def test_archived_validation_accepts_only_result_commit_and_runtime_stays_strict(evidence):
    kwargs, _ = evidence
    bundle = build_freeze_bundle(**kwargs)
    validate_archived_bundle(bundle)
    root = kwargs["repo_root"]
    (root / "research" / "formal-results.csv").write_text("method,status\n")
    (root / "research" / ".journal-owner.lock").write_text("12345\n")
    (root / "research" / (".pending-" + "a" * 32)).write_text('{"retained_forensic_record": true}\n')
    (root / "docs").mkdir()
    (root / "docs" / "REPORT.md").write_text("# Historical artifact\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "result artifacts only")
    validate_archived_bundle(bundle)
    with pytest.raises(ProtocolDrift, match="git SHA"):
        validate_frozen_bundle(bundle, current_identity=lambda: kwargs["identities"])


@pytest.mark.parametrize("mutation", ["modified", "deleted", "renamed", "new_code", "executable", "shebang", "outside_output", "symlink"])
def test_archive_rejects_source_or_historical_artifact_changes(evidence, mutation):
    kwargs, _ = evidence
    root = kwargs["repo_root"]
    bundle = build_freeze_bundle(**kwargs)
    source = Path(kwargs["artifact_paths"]["prompts"])
    if mutation == "modified":
        source.write_text("changed frozen prompt")
    elif mutation in {"deleted", "renamed"}:
        source.rename(root / "research" / "retained-original.txt")
        if mutation == "deleted":
            git(root, "add", "-u")
    else:
        path = root / "research" / ("module.py" if mutation == "new_code" else "artifact.txt")
        if mutation == "outside_output":
            path = root / "artifact.txt"
        if mutation == "symlink":
            path.symlink_to(source)
        else:
            path.write_text("#!/bin/sh\necho payload\n" if mutation == "shebang" else "artifact\n")
            if mutation == "executable":
                path.chmod(0o755)
    git(root, "add", "-u" if mutation == "deleted" else ".")
    git(root, "commit", "-qm", f"invalid archived change: {mutation}")
    with pytest.raises(ProtocolDrift):
        validate_archived_bundle(bundle)


def test_archived_bundle_rejects_dirty_source_and_tampered_binding(evidence):
    kwargs, _ = evidence
    bundle = build_freeze_bundle(**kwargs)
    tampered = copy.deepcopy(bundle)
    tampered["primary_comparator"]["method"] = "rag_replan"
    with pytest.raises(ProtocolDrift, match="digest mismatch"):
        validate_archived_bundle(tampered)
    Path(kwargs["artifact_paths"]["schemas"]).write_text("uncommitted source mutation")
    with pytest.raises(ProtocolDrift, match="DIRTY_TRACKED"):
        validate_archived_bundle(bundle)


def test_file_hash_cache_reuses_bytes_but_detects_same_size_restored_mtime(tmp_path, monkeypatch):
    from cope_benchmark.repeated_v2.freeze import _sha_file
    path = tmp_path / "checkpoint.bin"
    path.write_bytes(b"first-checkpoint")
    original_stat = path.stat()
    original_open = Path.open
    reads = []
    def counted_open(source, *args, **kwargs):
        if source == path and args and args[0] == "rb":
            reads.append(str(source))
        return original_open(source, *args, **kwargs)
    monkeypatch.setattr(Path, "open", counted_open)
    original = _sha_file(path)
    assert _sha_file(path) == original and len(reads) == 1
    path.write_bytes(b"other-checkpoint")
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert path.stat().st_size == original_stat.st_size and path.stat().st_mtime_ns == original_stat.st_mtime_ns
    changed = _sha_file(path)
    assert changed != original and len(reads) == 2
    assert _sha_file(path) == changed and len(reads) == 2


@pytest.mark.parametrize("mutation", ["bytes", "link"])
def test_archived_validation_rechecks_external_checkpoint_bytes_and_links(evidence, mutation):
    kwargs, refresh = evidence
    original = Path(kwargs["artifact_paths"]["vla_checkpoint"]).read_bytes()
    external = kwargs["repo_root"].parent / "external-checkpoint"
    external.mkdir()
    (external / "model-a").write_bytes(original)
    (external / "model-b").write_bytes(original)
    alias = external / "selected-model"
    alias.symlink_to("model-a")
    kwargs["artifact_paths"]["vla_checkpoint"] = str(alias)
    refresh()
    bundle = build_freeze_bundle(**kwargs)
    validate_archived_bundle(bundle)
    if mutation == "bytes":
        model = external / "model-a"
        before = model.stat()
        model.write_bytes(b"x" * len(original))
        os.utime(model, ns=(before.st_atime_ns, before.st_mtime_ns))
    else:
        replacement = external / "next-model"
        replacement.symlink_to("model-b")
        replacement.replace(alias)
    with pytest.raises(ProtocolDrift, match="bytes or links drift"):
        validate_archived_bundle(bundle)


def test_static_frozen_validation_needs_no_provider_and_keeps_exact_head(evidence, monkeypatch):
    kwargs, _ = evidence
    bundle = build_freeze_bundle(**kwargs)
    # Static admission must not call the live validator with fabricated identity.
    def forbidden_live_validation(*args, **kwargs):
        raise AssertionError("live validation must not be invoked for an empty shard")
    monkeypatch.setattr("cope_benchmark.repeated_v2.freeze.validate_frozen_bundle", forbidden_live_validation)
    validate_static_frozen_bundle(bundle)
    (kwargs["repo_root"] / "research" / "result.csv").write_text("status\n")
    git(kwargs["repo_root"], "add", ".")
    git(kwargs["repo_root"], "commit", "-qm", "historical result artifact")
    validate_archived_bundle(bundle)
    with pytest.raises(ProtocolDrift, match="git SHA"):
        validate_static_frozen_bundle(bundle)


def test_static_frozen_validation_rejects_tampering_without_live_callback(evidence):
    kwargs, _ = evidence
    bundle = build_freeze_bundle(**kwargs)
    tampered = copy.deepcopy(bundle)
    tampered["shards"][0]["manifest_sha256"] = "b" * 64
    with pytest.raises(ProtocolDrift, match="digest mismatch"):
        validate_static_frozen_bundle(tampered)
    Path(kwargs["artifact_paths"]["config"]).write_text("changed frozen config")
    with pytest.raises(ProtocolDrift):
        validate_static_frozen_bundle(bundle)
