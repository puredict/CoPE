from __future__ import annotations

import json
from pathlib import Path

import pytest

from cope_benchmark.exp1_trace_contract_v1 import (
    CANONICAL_SERIALIZATION_VERSION,
    CONTRACT_VERSION,
    OCCURRENCE_ALLOCATOR_VERSION,
    LeakageError,
    OccurrenceAllocatorV1,
    RuntimeTraceBundleV1,
    SealedOutcomeV1,
    assert_public_safe,
    canonical_json,
    strict_loads,
)
from cope_benchmark.exp1_trace_contract_v1.exporter import ExportBoundaryError, export_public_bundle
from cope_benchmark.exp1_trace_contract_v1.gates import Experiment1DependencyGates
from cope_benchmark.exp1_trace_contract_v1.manifest import verify_manifest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "exp1_trace_contract_v1"


def test_synthetic_public_fixture_round_trips_canonically():
    raw = strict_loads((FIXTURES / "public_trace_bundle.json").read_text())
    record = RuntimeTraceBundleV1.from_dict(raw)
    assert canonical_json(record) == (FIXTURES / "public_trace_bundle.json").read_text().strip()
    assert record.schema_version == CONTRACT_VERSION
    assert record.canonical_serialization_version == CANONICAL_SERIALIZATION_VERSION
    assert record.occurrence_allocator_version == OCCURRENCE_ALLOCATOR_VERSION


def test_sealed_fixture_is_valid_but_forbidden_from_public_tree():
    sealed = SealedOutcomeV1.from_dict(json.loads((FIXTURES / "sealed_outcome.json").read_text()))
    assert sealed.outcomes["success"] is True
    with pytest.raises(LeakageError):
        assert_public_safe({"nested": [{"payload": sealed.to_dict()}]})


@pytest.mark.parametrize(
    "payload",
    [
        {"hidden_cause": "x"},
        {"level1": [{"responsible_modules": ["planner"]}]},
        {"message": '{"sealed_outcome":{"success":true}}'},
        {"message": "prefix oracle_label: planner"},
    ],
)
def test_recursive_leakage_detection(payload):
    with pytest.raises(LeakageError):
        assert_public_safe(payload)


def test_occurrence_allocator_is_monotone_and_versioned():
    allocator = OccurrenceAllocatorV1(
        [{"family_key": "deliver", "occurrence_id": "deliver@2"}]
    )
    assert allocator.version == OCCURRENCE_ALLOCATOR_VERSION
    assert allocator.allocate("deliver") == "deliver@3"
    assert allocator.allocate("inspect") == "inspect@1"


def test_exporter_never_writes_to_read_only_source_root(tmp_path):
    source = FIXTURES / "public_trace_bundle.json"
    with pytest.raises(ExportBoundaryError):
        export_public_bundle(source, FIXTURES / "forbidden.json", read_only_roots=[ROOT])
    destination = tmp_path / "export.json"
    digest = export_public_bundle(source, destination, read_only_roots=[ROOT])
    assert len(digest) == 64
    assert destination.read_text().endswith("\n")
    with pytest.raises(FileExistsError):
        export_public_bundle(source, destination, read_only_roots=[ROOT])


def test_interface_gate_does_not_depend_on_catalog_or_formal_traces():
    gates = Experiment1DependencyGates.inspect(
        contract_manifest=ROOT / "manifests" / "exp1_trace_contract_v1_hashes.csv"
    )
    assert gates.interface_contract_frozen is True
    assert gates.task_catalog_frozen is False
    assert gates.formal_trace_data_available is False


def test_hash_manifest_is_complete_and_exact():
    verify_manifest(ROOT, ROOT / "manifests" / "exp1_trace_contract_v1_hashes.csv")


def test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers():
    with pytest.raises(ValueError):
        strict_loads('{"a":1,"a":2}')
    with pytest.raises(ValueError):
        strict_loads('{"a":NaN}')
