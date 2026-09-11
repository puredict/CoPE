"""Mock qualification of the CLI seam; these tests are never experiment evidence."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from cope_benchmark.repeated_v2.config import ROOT, load_config
from cope_benchmark.repeated_v2.enums import MethodName
from cope_benchmark.repeated_v2.journal import DurableJournal, stable_hash
from cope_benchmark.repeated_v2.pilot import (
    EpisodeInputs, RuntimeAssembly, _publish, dependency_report, execute_assembly,
    export_journal, pilot_manifest, run_experiment,
)
from cope_benchmark.repeated_v2.provider import FixtureReasoner, ReasonerConfig
from cope_benchmark.repeated_v2.runner import RuntimeBlocked
from .test_phase3_runner import (
    EPISODE, MockEnvironment, MockMethod, MockPlanner, MockVLA, canonical_ledger,
    context, schedule,
)
from .catalog_fixtures import synthetic_catalog_v2_1


def config():
    return {"methods": {"non_oracle": [MethodName.COPE_TYPED_EDIT.value,
                                      MethodName.GENERIC_PERSISTENT_EDIT.value], "oracle": []},
            "evidence": {"primary_condition": "evidence_matched", "secondary_condition": "token_matched"},
            "protocols": {"controlled": {"event_count": 8}, "end_to_end": {"event_count": 4}},
            "vla": {"max_policy_steps": 180, "action_dimension": 7, "action_chunk_horizon": 8}}


def manifest():
    events = schedule().to_dict()
    return [{"master_episode_id": EPISODE, "master_schedule": events,
             "master_schedule_sha256": stable_hash(events),
             "pair_fields": {"task_id": 0, "initial_state_id": 0, "policy_seed": 15}}]


def assembly(*, environment_factory=MockEnvironment, method_factory=None,
             policy_factory=MockVLA):
    def build_method(*, method_name, information_condition):
        result = MockMethod()
        result.method = MethodName(method_name)
        return result
    return RuntimeAssembly(
        episode_inputs=lambda **_: EpisodeInputs({"language": "mock task"}, canonical_ledger(0), context()),
        environment_factory=environment_factory, planner_factory=MockPlanner,
        method_factory=method_factory or build_method, policy_factory=policy_factory,
        identity={"provider_id": "mock-test-only"}, fixture=True)


def execute(path, *, protocol="controlled", runtime=None, **kwargs):
    return execute_assembly(assembly=runtime or assembly(), config=config(), manifest=manifest(),
        catalog={0: {"task_id": 0}}, output_dir=path, phase="pilot", protocol=protocol,
        source_commit="a" * 40, qualification=True, information_condition="evidence_matched", **kwargs)


@pytest.mark.parametrize("protocol,count", [("controlled", 8), ("end_to_end", 4)])
def test_mock_qualification_exports_every_method_cell_without_claims(tmp_path, protocol, count):
    envs = []
    def environment():
        env = MockEnvironment()
        envs.append(env)
        return env
    report = execute(tmp_path, protocol=protocol, runtime=assembly(environment_factory=environment))
    assert report["status"] == "MOCK_QUALIFICATION_COMPLETE"
    assert report["fixture"] and report["performance_claims"] is False
    assert len(envs) == 2 and all(env.reset_calls == 1 for env in envs)
    rows = [json.loads(line) for line in (tmp_path / "06_EVENT_RESULTS.jsonl").read_text().splitlines()]
    assert len(rows) == 2 * (count + 1)
    assert all(row["fixture"] for row in rows)
    assert all(row["information_condition"] == "evidence_matched" for row in rows)
    for number in range(4, 10):
        assert len(list(tmp_path.glob(f"{number:02d}_*"))) == 1
    for path in (tmp_path / "10_ACTION_TRACES").glob("*.gz"):
        entries = [json.loads(line) for line in gzip.decompress(path.read_bytes()).splitlines()]
        assert entries and all("target_occurrence_id" in entry for entry in entries)
    assert report["exports"]["evidence_matched"]["integrity"]["valid"]


def test_v2_1_smallest_pilot_is_two_tasks_two_states_one_seed_and_eight_nonoracle_methods(tmp_path):
    cfg = load_config(ROOT / "configs/repeated_interruptions_v2_1_pilot.yaml")
    raw_catalog = synthetic_catalog_v2_1().to_dict()
    raw_catalog["provenance_kind"] = "source_backed"
    from cope_benchmark.repeated_v2.task_catalog import TaskCatalog
    task_catalog = TaskCatalog.from_dict(raw_catalog)
    rows = pilot_manifest(cfg, task_catalog, source_commit="a" * 40)
    assert len(rows) == 4
    assert {(row["pair_fields"]["task_id"], row["pair_fields"]["initial_state_id"],
             row["pair_fields"]["policy_seed"]) for row in rows} == {
        (task_id, state_id, 11) for task_id in (1, 4) for state_id in (10, 11)
    }
    assert all(row["pipeline_evidence_only"] is True for row in rows)
    environments = []
    class PilotMockEnvironment(MockEnvironment):
        def trigger_context(self, *, previous_event_step):
            from cope_benchmark.repeated_v2.scheduler import TriggerContext
            return TriggerContext(
                self.policy_step, {"verified_cube_placement": self.segment_actions > 0},
                {"certified_event_pose": True}, previous_event_step=previous_event_step,
            )
    def environment_factory():
        value = PilotMockEnvironment()
        environments.append(value)
        return value
    runtime = assembly(environment_factory=environment_factory)
    report = execute_assembly(
        assembly=runtime, config=cfg, manifest=rows,
        catalog={task.task_id: task.to_dict() for task in task_catalog.tasks},
        catalog_data=task_catalog.to_dict(), output_dir=tmp_path, phase="pilot",
        protocol="end_to_end", source_commit="a" * 40, qualification=True,
    )
    assert report["master_count"] == 4
    assert report["method_count"] == 8
    assert report["information_conditions"] == ["evidence_matched"]
    assert len(environments) == 32
    episodes = [json.loads(line) for line in
                (tmp_path / "evidence_matched/07_EPISODE_RESULTS.jsonl").read_text().splitlines()]
    assert len(episodes) == 32
    assert all(row["required_events"] == row["reached_events"] == 4 for row in episodes)
    assert report["exports"]["evidence_matched"]["integrity"]["valid"]


def test_completed_resume_preserves_export_bytes_and_calls(tmp_path):
    execute(tmp_path)
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*")
              if path.is_file() and path.name != ".journal-owner.lock"}
    execute(tmp_path, resume=True)
    assert before == {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*")
                      if path.is_file() and path.name != ".journal-owner.lock"}


def test_resume_preserves_first_stop_receipt_without_masking_current_failure(tmp_path):
    class FailingEnvironment(MockEnvironment):
        def reset(self, **kwargs):
            raise RuntimeBlocked("BLOCKED_TEST_DEPENDENCY", "test dependency is unavailable")

    runtime = assembly(environment_factory=FailingEnvironment)
    with pytest.raises(RuntimeBlocked) as first:
        execute(tmp_path, runtime=runtime)
    assert first.value.status == "BLOCKED_TEST_DEPENDENCY"
    receipt = (tmp_path / "13_INFRASTRUCTURE_STOP.json").read_bytes()

    with pytest.raises(RuntimeBlocked) as resumed:
        execute(tmp_path, runtime=runtime, resume=True)
    assert resumed.value.status == "BLOCKED_TEST_DEPENDENCY"
    assert (tmp_path / "13_INFRASTRUCTURE_STOP.json").read_bytes() == receipt


def test_changed_config_or_identity_on_resume_is_durably_rejected(tmp_path):
    execute(tmp_path)
    other = assembly()
    object.__setattr__(other, "identity", {"provider_id": "another-test"})
    with pytest.raises(Exception) as error:
        execute(tmp_path, runtime=other, resume=True)
    assert getattr(error.value, "status", None) == "INVALID_PROTOCOL_DRIFT"


def test_reusing_mutable_method_state_is_rejected_before_environment_reset(tmp_path):
    shared = MockMethod()
    called = []
    def method(**kwargs):
        shared.method = MethodName(kwargs["method_name"])
        return shared
    with pytest.raises(RuntimeBlocked) as error:
        execute(tmp_path, runtime=assembly(method_factory=method, environment_factory=lambda: called.append(1)))
    assert error.value.status == "INVALID_SHARED_METHOD_STATE"
    assert called == []


def test_different_reasoner_settings_fail_before_any_environment_or_provider_call(tmp_path):
    calls = []
    def method(*, method_name, information_condition):
        reasoner = FixtureReasoner(["{}"] * 8)
        result = MockMethod(reasoner=reasoner)
        result.method = MethodName(method_name)
        if result.method == MethodName.GENERIC_PERSISTENT_EDIT:
            result.gateway.config = ReasonerConfig("mock-provider", "different-model")
        return result
    with pytest.raises(RuntimeBlocked) as error:
        execute(tmp_path, runtime=assembly(method_factory=method, environment_factory=lambda: calls.append(1)))
    assert error.value.status == "INVALID_REASONER_PARITY"
    assert calls == []


def test_factory_cannot_share_a_gateway_between_independent_methods(tmp_path):
    shared = MockMethod(reasoner=FixtureReasoner(["{}"] * 8)).gateway
    def method(*, method_name, information_condition):
        result = MockMethod()
        result.method = MethodName(method_name)
        result.gateway = shared
        return result
    with pytest.raises(RuntimeBlocked) as error:
        execute(tmp_path, runtime=assembly(method_factory=method))
    assert error.value.status == "INVALID_SHARED_METHOD_STATE"


def test_qualification_cannot_enter_formal_mode_or_unmarked_pilot(tmp_path):
    for phase, qualification in (("formal", True), ("pilot", False)):
        with pytest.raises(RuntimeBlocked) as error:
            execute_assembly(assembly=assembly(), config=config(), manifest=manifest(), catalog={0: {}},
                output_dir=tmp_path, phase=phase, protocol="controlled", source_commit="a" * 40,
                qualification=qualification)
        assert error.value.status == "INVALID_FIXTURE_RUN"
    assert not tmp_path.exists() or not any(tmp_path.iterdir())


def test_missing_dependencies_do_not_import_or_invoke_runtime_factory(tmp_path, monkeypatch):
    imported = []
    monkeypatch.setattr("cope_benchmark.repeated_v2.pilot.load_runtime_factory", lambda *a, **k: imported.append(1))
    report = run_experiment(config_path=ROOT / "configs/repeated_interruptions_v2_pilot.yaml",
        output_dir=tmp_path, phase="pilot", protocol="end_to_end", environ={})
    assert report["passed"] is False and report["provider_calls"] == report["vla_calls"] == 0
    assert report["runtime_factory_calls"] == report["result_rows_generated"] == 0
    assert imported == []
    assert "BLOCKED_VLA_ADAPTER_UNAVAILABLE" in {entry["status"] for entry in report["blockers"]}
    assert not list(tmp_path.rglob("06_EVENT_RESULTS.jsonl"))
    old = (tmp_path / "13_INFRASTRUCTURE_STOP.json").read_bytes()
    rerun = run_experiment(config_path=ROOT / "configs/repeated_interruptions_v2_pilot.yaml",
        output_dir=tmp_path, phase="pilot", protocol="end_to_end", environ={}, resume=True)
    assert rerun == report
    assert (tmp_path / "13_INFRASTRUCTURE_STOP.json").read_bytes() == old


def test_reasoner_factory_and_local_checkpoint_are_mandatory(tmp_path):
    cfg = load_config(ROOT / "configs/repeated_interruptions_v2_pilot.yaml")
    result = dependency_report(cfg, phase="formal", protocol="end_to_end", environ={
        "COPE_RUNTIME_FACTORY": "does.not.import:factory", "COPE_VLA_FACTORY": "does.not.import:factory",
        "COPE_VLA_CHECKPOINT": str(tmp_path / "missing")})
    statuses = {row["status"] for row in result["blockers"]}
    assert {"BLOCKED_REASONER_ADAPTER_UNAVAILABLE", "BLOCKED_VLA_CHECKPOINT_UNAVAILABLE",
            "BLOCKED_FREEZE_REQUIRED"} <= statuses
    assert result["runtime_factory_calls"] == 0


def test_development_production_gate_blocks_before_factory_with_disjoint_design(tmp_path, monkeypatch):
    factories = []
    monkeypatch.setattr("cope_benchmark.repeated_v2.pilot.load_runtime_factory", lambda *a, **k: factories.append(1))
    report = run_experiment(config_path=ROOT / "configs/repeated_interruptions_v2_pilot.yaml",
        output_dir=tmp_path, phase="development", protocol="end_to_end", environ={},
        information_condition="evidence_matched")
    assert report["phase"] == "development" and report["passed"] is False
    assert report["provider_calls"] == report["runtime_factory_calls"] == 0
    assert factories == []
    assert not any(entry["status"] == "BLOCKED_FREEZE_REQUIRED" for entry in report["blockers"])


def test_export_refuses_incomplete_journal_and_does_not_impute(tmp_path):
    with DurableJournal(tmp_path, frozen_metadata={"fixture": True}) as journal:
        with pytest.raises(RuntimeBlocked) as error:
            export_journal(journal, output_dir=tmp_path,
                expected_cells=[("controlled", "master", "method", 0)],
                condition="evidence_matched", resume=False)
        assert error.value.status == "INVALID_RUN"
        assert not (tmp_path / "06_EVENT_RESULTS.jsonl").exists()


def test_export_atomic_resume_rejects_changed_bytes(tmp_path):
    path = tmp_path / "artifact.txt"
    _publish(path, b"original", resume=False)
    _publish(path, b"original", resume=True)
    with pytest.raises(RuntimeBlocked):
        _publish(path, b"different", resume=True)
    assert path.read_bytes() == b"original"


def _formal_partition_fixture():
    rows = manifest()
    rows[0]["source_commit"] = "a" * 40
    owner = int(hashlib.sha256(EPISODE.encode()).hexdigest(), 16) % 8
    partitions = [rows if index == owner else [] for index in range(8)]
    bundle = {"status": "FROZEN", "schema_version": "mock-freeze-contract-only",
              "identities": {"test_scope": "zero-job integration; no production evidence"},
              "shard_count": 8,
              "shards": [{"shard_id": index, "master_episode_ids": [row["master_episode_id"] for row in values],
                          "manifest_sha256": stable_hash(values)} for index, values in enumerate(partitions)]}
    bundle["bundle_sha256"] = stable_hash(bundle)
    return rows, bundle, owner, (owner + 1) % 8


def test_empty_formal_shard_exports_and_resumes_without_any_runtime_factory(tmp_path, monkeypatch):
    rows, bundle, owner, empty = _formal_partition_fixture()
    full_path = tmp_path / "full.jsonl"
    full_path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(bundle))
    preflights, static_checks, factories = [], [], []
    def preflight(config, catalog, *, source_commit, manifest=None):
        preflights.append(deepcopy(manifest))
        assert manifest == rows and source_commit == "a" * 40
        return {"passed": True, "status": "MOCK_FULL_PREFLIGHT_FOR_ZERO_JOB_TEST"}
    monkeypatch.setattr("cope_benchmark.repeated_v2.preflight.run_preflight", preflight)
    monkeypatch.setattr("cope_benchmark.repeated_v2.pilot._load_freeze", lambda _: deepcopy(bundle))
    monkeypatch.setitem(sys.modules, "cope_benchmark.repeated_v2.freeze",
                        SimpleNamespace(validate_static_frozen_bundle=lambda value: static_checks.append(value)))
    monkeypatch.setattr("cope_benchmark.repeated_v2.pilot.load_runtime_factory", lambda *a, **k: factories.append(1))
    output = tmp_path / "empty-shard"
    kwargs = dict(config_path=ROOT / "configs/repeated_interruptions_v2_formal.yaml", output_dir=output,
                  phase="formal", protocol="end_to_end", information_condition="evidence_matched",
                  manifest_path=full_path, frozen_bundle_path=freeze_path,
                  shard_index=empty, num_shards=8, environ={})
    result = run_experiment(**kwargs)
    assert result["status"] == "COMPLETE" and result["empty_shard"] is True
    assert result["runtime_factory_calls"] == result["provider_calls"] == result["vla_calls"] == 0
    assert result["executed_trajectory_count"] == result["result_rows_generated"] == 0
    assert factories == [] and len(preflights) == 2 and len(static_checks) == 1
    metadata = json.loads((output / "00_RUN_METADATA.json").read_text())
    assert metadata["shard_id"] == empty and metadata["full_manifest_sha256"] == stable_hash(rows)
    assert metadata["freeze_sha256"] == bundle["bundle_sha256"]
    assert metadata["live_identity_check"] == "not_required_no_external_calls"
    for number in range(3, 10):
        path, = output.glob(f"{number:02d}_*.jsonl")
        assert path.read_bytes() == b""
    assert (output / "10_ACTION_TRACES").is_dir() and not list((output / "10_ACTION_TRACES").iterdir())
    with DurableJournal(output) as journal:
        assert journal.records("results") == journal.records("episodes") == journal.records("intents") == {}
    before = {path.relative_to(output): path.read_bytes() for path in output.rglob("*")
              if path.is_file() and path.name != ".journal-owner.lock"}
    assert run_experiment(**kwargs, resume=True) == result
    after = {path.relative_to(output): path.read_bytes() for path in output.rglob("*")
             if path.is_file() and path.name != ".journal-owner.lock"}
    assert before == after and factories == [] and len(static_checks) == 2


def test_empty_formal_claim_cannot_omit_owned_episodes_or_skip_full_preflight(tmp_path, monkeypatch):
    from cope_benchmark.repeated_v2.task_catalog import load_task_catalog
    rows, bundle, owner, empty = _formal_partition_fixture()
    cfg = load_config(ROOT / "configs/repeated_interruptions_v2_formal.yaml")
    catalog = load_task_catalog()
    checks = []
    monkeypatch.setattr("cope_benchmark.repeated_v2.preflight.run_preflight", lambda *a, **k: {"passed": True})
    monkeypatch.setattr("cope_benchmark.repeated_v2.pilot._validate_empty_freeze", lambda _: checks.append(1))
    kwargs = dict(assembly=None, config=cfg, manifest=[], catalog={}, catalog_data=catalog.to_dict(),
                  output_dir=tmp_path / "no-output", phase="formal", protocol="controlled", source_commit="a" * 40,
                  frozen_bundle=bundle, information_condition="evidence_matched", full_manifest=rows)
    with pytest.raises(RuntimeBlocked) as error:
        execute_assembly(**kwargs, shard_index=owner)
    assert error.value.status == "INVALID_SHARD" and checks == []
    monkeypatch.setattr("cope_benchmark.repeated_v2.preflight.run_preflight",
                        lambda *a, **k: {"passed": False, "status": "BLOCKED_TASK_CATALOG_GAPS"})
    with pytest.raises(RuntimeBlocked) as error:
        execute_assembly(**kwargs, shard_index=empty)
    assert error.value.status == "BLOCKED_TASK_CATALOG_GAPS" and checks == []
    assert not (tmp_path / "no-output").exists()


@pytest.mark.parametrize("phase", ["pilot", "development"])
def test_empty_nonformal_design_stays_blocked(tmp_path, phase):
    runtime = assembly()
    object.__setattr__(runtime, "fixture", False)
    with pytest.raises(RuntimeBlocked) as error:
        execute_assembly(assembly=runtime, config=config(), manifest=[], catalog={}, output_dir=tmp_path,
                         phase=phase, protocol="controlled", source_commit="a" * 40)
    assert error.value.status == "BLOCKED_EMPTY_MANIFEST"


def test_empty_shard_requires_phase4_public_static_validator(monkeypatch):
    from cope_benchmark.repeated_v2.pilot import _validate_empty_freeze
    monkeypatch.setitem(sys.modules, "cope_benchmark.repeated_v2.freeze", SimpleNamespace())
    with pytest.raises(RuntimeBlocked) as error:
        _validate_empty_freeze({"status": "FROZEN"})
    assert error.value.status == "BLOCKED_FREEZE_REQUIRED"
