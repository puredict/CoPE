from pathlib import Path
import socket

import pytest

from cope_benchmark.repeated_v2.canonical import canonical_json
from cope_benchmark.repeated_v2.config import load_config
from cope_benchmark.repeated_v2.preflight import run_pilot_preflight, run_preflight
from cope_benchmark.repeated_v2.task_catalog import TaskCatalog, load_task_catalog
from tests.repeated_v2.catalog_fixtures import synthetic_catalog, synthetic_catalog_v2_1

ROOT = Path(__file__).resolve().parents[2]
SHA = "84e1e742579899adb67efee92cef16efca063b31"


def test_preflight_is_deterministic_and_never_calls_providers(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("zero-provider preflight attempted network access")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    for variable in ("COPE_REASONER_FACTORY", "COPE_VLA_FACTORY", "COPE_PLANNER_FACTORY", "COPE_RETRIEVER_FACTORY"):
        monkeypatch.setenv(variable, "must_not_import:must_not_call")
    config = load_config(ROOT / "configs/repeated_interruptions_v2_formal.yaml")
    catalog = synthetic_catalog(task_count=8)
    first = run_preflight(config, catalog, source_commit=SHA, allow_synthetic=True)
    second = run_preflight(config, catalog, source_commit=SHA, allow_synthetic=True)
    assert first["passed"] is True, first["errors"]
    assert canonical_json(first) == canonical_json(second)
    assert first["provider_calls"] == first["vla_calls"] == 0
    assert first["formal_execution_authorized"] is False
    assert first["expected_counts"]["all_conditions"]["event_cells"] == 25920


def test_checked_in_catalog_fails_closed_without_calibration():
    config = load_config(ROOT / "configs/repeated_interruptions_v2_formal.yaml")
    catalog = load_task_catalog(ROOT / "task_catalogs/repeated_v2.json")
    report = run_preflight(config, catalog, source_commit=SHA)
    assert not report["passed"]
    assert report["eligible_task_ids"] == []
    assert report["manifest_sha256"] is None
    assert report["catalog_gap_count"] > 0
    assert report["provider_calls"] == report["vla_calls"] == 0
    assert canonical_json(report) == canonical_json(run_preflight(config, catalog, source_commit=SHA))


def test_synthetic_catalog_cannot_pass_formal_preflight():
    config = load_config(ROOT / "configs/repeated_interruptions_v2_formal.yaml")
    report = run_preflight(config, synthetic_catalog(task_count=10), source_commit=SHA)
    assert not report["passed"]
    assert report["manifest_sha256"] is None
    assert any("synthetic" in error for error in report["errors"])


def test_pilot_preflight_requires_two_tasks_but_preserves_formal_eight_task_gate():
    config = load_config(ROOT / "configs/repeated_interruptions_v2_1_pilot.yaml")
    raw = synthetic_catalog_v2_1(task_count=7).to_dict()
    raw["provenance_kind"] = "source_backed"
    catalog = TaskCatalog.from_dict(raw)

    pilot = run_pilot_preflight(config, catalog, source_commit=SHA)
    formal = run_preflight(config, catalog, source_commit=SHA)

    assert pilot["status"] == "PILOT_PREFLIGHT_PASSED"
    assert pilot["pilot_task_ids"] == [1, 4]
    assert pilot["eligible_task_ids"] == list(range(7))
    assert pilot["formal_minimum_met"] is False
    assert pilot["expected_counts"]["primary_non_oracle_trajectories"] == 32
    assert formal["status"] == "BLOCKED_INSUFFICIENT_ELIGIBLE_TASKS"
    assert formal["passed"] is False
    assert formal["eligible_task_ids"] == list(range(7))
