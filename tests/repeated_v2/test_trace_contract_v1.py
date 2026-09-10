import json
from pathlib import Path

import jsonschema

from cope_benchmark.repeated_v2.canonical import canonical_sha256
from cope_benchmark.repeated_v2.trace_contract_v1 import (
    EXP1_FORMAL_TRACE_DATA_AVAILABLE, EXP1_INTERFACE_CONTRACT_FROZEN,
    EXP1_TASK_CATALOG_FROZEN, RuntimeTraceBundleV1, SealedOutcomeV1,
    TRACE_CONTRACT_VERSION, contract_identity, experiment1_dependency_gates,
)
from cope_benchmark.repeated_v2.trace_contract_validation_v1 import (
    load_canonical_record, validate_public_bundle, validate_schema_directory,
    validate_sealed_outcome,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas/repeated_v2/trace_contract_v1"
FIXTURES = ROOT / "frozen/repeated_v2_trace_contract_v1/fixtures"


def test_checked_in_schemas_are_exact_executable_contract():
    hashes = validate_schema_directory(SCHEMAS)
    assert set(hashes) == {
        "runtime_trace_bundle.schema.json", "public_event_evidence.schema.json",
        "persistent_ledger_snapshot.schema.json", "execution_context_snapshot.schema.json",
        "patch_record.schema.json", "planning_problem.schema.json",
        "progress_certificate.schema.json", "sealed_outcome.schema.json",
    }
    assert all(len(value) == 64 for value in hashes.values())


def test_runtime_and_sealed_fixtures_validate_and_are_digest_bound():
    bundle = validate_public_bundle(load_canonical_record(FIXTURES / "runtime_trace_bundle.json"))
    outcome = validate_sealed_outcome(load_canonical_record(FIXTURES / "sealed_outcome.json"))
    assert isinstance(bundle, RuntimeTraceBundleV1)
    assert isinstance(outcome, SealedOutcomeV1)
    assert bundle.sealed_outcome_ref == canonical_sha256(outcome)
    assert outcome.final_active_task_success is False


def test_interface_gate_is_independent_of_catalog_and_formal_data():
    gates = experiment1_dependency_gates(
        interface_contract_frozen=True, task_catalog_frozen=False,
        formal_trace_data_available=False)
    assert gates == {
        EXP1_INTERFACE_CONTRACT_FROZEN: True,
        EXP1_TASK_CATALOG_FROZEN: False,
        EXP1_FORMAL_TRACE_DATA_AVAILABLE: False,
    }


def test_contract_identity_is_versioned_and_names_all_records():
    identity = contract_identity()
    assert identity["schema_version"] == TRACE_CONTRACT_VERSION
    assert "RuntimeTraceBundleV1" in identity["record_types"]
    assert "SealedOutcomeV1" in identity["record_types"]
    assert len(identity["record_types"]) == 11
