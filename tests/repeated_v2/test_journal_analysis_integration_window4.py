"""Actual writer/auditor integration; synthetic fixtures live only in tmp_path.

Fixture provider IDs and absent production freezes make these mechanical
examples inadmissible as formal evidence. No provider or simulator is loaded.
"""
from dataclasses import asdict
import json

import pytest

from cope_benchmark.repeated_v2.freeze import (
    FreezeBlocked, SCHEMA_VERSION, artifact_inventory, audit_journal_directory,
)
from cope_benchmark.repeated_v2.journal import DurableJournal, stable_hash
from cope_benchmark.repeated_v2.pilot import export_journal
from cope_benchmark.repeated_v2.provider import ReasonerConfig, ReasonerResponse

IDENTITIES = {"reasoner": {"provider_id": "fixture-journal-unit-only", "model_id": "fixture-no-network"}}
BASE_KEY = ("end_to_end", "synthetic-integration-master", "cope_typed_edit")
EXPECTED = [(*BASE_KEY, index) for index in range(5)]


def write_actual_journal(directory, *, failed=False, corrupt_source=False):
    config = ReasonerConfig(provider=IDENTITIES["reasoner"]["provider_id"], model=IDENTITIES["reasoner"]["model_id"])
    request = {"messages": [{"role": "user", "content": "Synthetic journal integration fixture."}], "config": asdict(config)}
    response = asdict(ReasonerResponse(text="{}", input_tokens=7, output_tokens=1, token_count_kind="unit_fixture", fixture=False))
    calls, trace = [], []
    metadata = {"phase": "pilot", "fixture": False, "runtime_identities": IDENTITIES}
    with DurableJournal(directory, frozen_metadata=metadata) as journal:
        for index, key in enumerate(EXPECTED):
            called = bool(index and (not failed or index == 1))
            if called:
                def invoke(value):
                    calls.append(value)
                    return response
                assert journal.call_once(key, request, invoke) == response
                assert journal.call_once(key, request, invoke) == response
                trace.append({"values": [0.0] * 7, "raw_values": [0.0] * 7,
                              "action_space": "synthetic_normalized_controller", "event_index": index})
            unreached = failed and index > 1
            status = ("EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE" if unreached else
                      "METHOD_RECOVERY_EXECUTION_FAILURE" if failed and index == 1 else "COMPLETED")
            success = status == "COMPLETED"
            result = {"protocol": key[0], "master_episode_id": key[1], "method": key[2], "event_index": index,
                      "phase": "pilot", "fixture": False, "status": status, "success": success,
                      "final_active_task_success_after_last_event": success, "high_level_calls": int(called),
                      "information_condition": "evidence_matched", "checkpoint": index in (0, 1, 2, 4)}
            if unreached:
                source = journal.load_snapshot(EXPECTED[1], label="completed")
                result.update(source_boundary_event_index=1, prior_failure="METHOD_RECOVERY_EXECUTION_FAILURE",
                              source_boundary_sha256="f" * 64 if corrupt_source else stable_hash(source))
            else:
                journal.save_snapshot(key, {"index": index, "delivered": index, "pending_result": result,
                                            "identity": {"initial_state_id": 0, "seed": 999}}, label="completed")
            journal.record_result(key, result)
        episode = {key: value for key, value in result.items() if key != "event_index"}
        episode.update(status="METHOD_RECOVERY_EXECUTION_FAILURE" if failed else "COMPLETED",
                       action_trace=trace, action_trace_sha256=stable_hash(trace), required_events=4,
                       reached_events=1 if failed else 4)
        journal.record_episode(EXPECTED[0], episode)
        exported = None
        if not corrupt_source:
            export_journal(journal, output_dir=directory, expected_cells=EXPECTED, condition="evidence_matched", resume=False)
            exported = [json.loads(line) for line in (directory / "06_EVENT_RESULTS.jsonl").read_text().splitlines()]
    return calls, exported


def test_real_writer_response_timing_and_export_round_trip(tmp_path):
    directory = tmp_path / "unit-run"
    calls, exported = write_actual_journal(directory)
    assert len(calls) == 4  # Eight call_once invocations, four actual callbacks.
    before = artifact_inventory(tmp_path, {"journal": directory})
    audit = audit_journal_directory(directory, expected_cells=EXPECTED, expected_phase="pilot",
                                     identities=IDENTITIES, exported_results=exported)
    assert audit["status"] == "VALID" and len(audit["results"]) == 5
    assert all(type(row["invocation_seconds"]) is float and row["invocation_seconds"] >= 0 for row in audit["responses"].values())
    assert set(audit["intents"]) == set(audit["responses"]) == set(EXPECTED[1:])
    assert artifact_inventory(tmp_path, {"journal": directory}) == before
    altered_export = [dict(row) for row in exported]
    altered_export[-1]["success"] = False
    with pytest.raises(FreezeBlocked, match="exported results"):
        audit_journal_directory(directory, expected_cells=EXPECTED, expected_phase="pilot",
                                identities=IDENTITIES, exported_results=altered_export)


def test_real_writer_retains_failed_source_and_unreached_cells(tmp_path):
    directory = tmp_path / "unit-failed-run"
    calls, exported = write_actual_journal(directory, failed=True)
    audit = audit_journal_directory(directory, expected_cells=EXPECTED, expected_phase="pilot",
                                     identities=IDENTITIES, exported_results=exported)
    assert len(calls) == 1 and len(audit["results"]) == 5
    assert [row["status"] for row in audit["results"]] == [
        "COMPLETED", "METHOD_RECOVERY_EXECUTION_FAILURE", "EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE",
        "EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE", "EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE"]
    assert all(row["success"] is False for row in audit["results"][1:])
    assert all(row["source_boundary_event_index"] == 1 for row in audit["results"][2:])


def test_real_writer_bad_unreached_source_hash_is_rejected(tmp_path):
    directory = tmp_path / "unit-bad-source"
    write_actual_journal(directory, failed=True, corrupt_source=True)
    with pytest.raises(FreezeBlocked, match="source boundary hash mismatch"):
        audit_journal_directory(directory, expected_cells=EXPECTED, expected_phase="pilot", identities=IDENTITIES)
    assert len(list((directory / "journal" / "results").glob("*.json"))) == 5


def test_actual_response_envelope_mutation_rejected_and_retained(tmp_path):
    directory = tmp_path / "unit-mutated-run"
    write_actual_journal(directory)
    response_path = directory / "journal" / "responses" / (stable_hash(list(EXPECTED[1])) + ".json")
    original = response_path.read_bytes()
    record = json.loads(original)
    record["payload"]["invocation_seconds"] += 100
    response_path.write_text(json.dumps(record) + "\n")
    with pytest.raises(FreezeBlocked, match="envelope hash"):
        audit_journal_directory(directory, expected_cells=EXPECTED, expected_phase="pilot", identities=IDENTITIES)
    assert response_path.is_file() and response_path.read_bytes() != original


def test_actual_empty_assembly_exports_auditable_zero_call_journal(tmp_path, monkeypatch):
    from cope_benchmark.repeated_v2 import pilot
    # Freeze tests cover admission; isolate the actual post-admission empty
    # writer/export path here, without claiming a real qualified freeze.
    admission = []
    monkeypatch.setattr(pilot, "_validate_empty_formal_inputs", lambda **kwargs: admission.append(kwargs))
    def forbidden(*args, **kwargs):
        raise AssertionError("an empty shard must not construct a runtime")
    monkeypatch.setattr(pilot, "load_runtime_factory", forbidden)
    config = {"methods": {"non_oracle": ["cope_typed_edit"], "oracle": []},
              "evidence": {"primary_condition": "evidence_matched", "secondary_condition": "token_matched"}}
    bundle = {"schema_version": SCHEMA_VERSION, "status": "FROZEN", "identities": IDENTITIES}
    bundle["bundle_sha256"] = stable_hash(bundle)
    output = tmp_path / "unit-empty-shard"
    status = pilot.execute_assembly(assembly=None, config=config, manifest=[], catalog={}, output_dir=output,
                                     phase="formal", protocol="end_to_end", source_commit="a" * 40,
                                     frozen_bundle=bundle, information_condition="evidence_matched", shard_index=0,
                                     num_shards=8, catalog_data={"unit_fixture_only": True},
                                     full_manifest=[{"unit_fixture_only": True}])
    assert len(admission) == 1 and status["empty_shard"] is True
    assert status["provider_calls"] == status["vla_calls"] == status["runtime_factory_calls"] == 0
    assert (output / "06_EVENT_RESULTS.jsonl").read_bytes() == b""
    audit = audit_journal_directory(output, expected_cells=[], expected_phase="formal", identities=IDENTITIES,
                                     exported_results=[], freeze_sha256=bundle["bundle_sha256"])
    assert audit["results"] == [] and audit["intents"] == audit["responses"] == {}
