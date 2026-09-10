"""Authoritative JSON Schema documents for the frozen v1 records."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .canonical import CANONICAL_SERIALIZATION_VERSION
from .contract import CONTRACT_VERSION
from .occurrence import OCCURRENCE_ALLOCATOR_VERSION

TEXT = {"type": "string", "minLength": 1, "pattern": r"\S"}
NONNEGATIVE = {"type": "integer", "minimum": 0}
POSITIVE = {"type": "integer", "minimum": 1}
SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
OBJECT = {"type": "object"}
OBJECTS = {"type": "array", "items": OBJECT}
STRINGS = {"type": "array", "items": TEXT, "uniqueItems": True}


def _document(title: str, properties: dict[str, Any], required: tuple[str, ...] | None = None) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://cope.local/schemas/exp1_trace_contract_v1/{title}.schema.json",
        "title": title,
        "type": "object",
        "additionalProperties": False,
        "properties": deepcopy(properties),
        "required": list(required or properties),
    }


SCHEMA_DOCUMENTS = {
    "public_event_evidence_v1.schema.json": _document(
        "PublicEventEvidenceV1",
        {
            "event_id": TEXT,
            "event_index": POSITIVE,
            "hypothesis": TEXT,
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence_ids": {**STRINGS, "minItems": 1},
            "timestamp": NONNEGATIVE,
            "provenance": TEXT,
            "observation_refs": STRINGS,
            "user_message": {"type": ["string", "null"]},
            "affected_entity_hypotheses": STRINGS,
        },
    ),
    "persistent_ledger_snapshot_v1.schema.json": _document(
        "PersistentLedgerSnapshotV1",
        {"revision": NONNEGATIVE, "slots": OBJECTS, "relations": OBJECTS, "history_records": OBJECTS},
    ),
    "execution_context_snapshot_v1.schema.json": _document(
        "ExecutionContextSnapshotV1",
        {"captured_at_step": NONNEGATIVE, "beliefs": OBJECTS, "progress": OBJECTS, "continuation": OBJECT},
    ),
    "patch_record_v1.schema.json": _document(
        "PatchRecordV1",
        {
            "patch_id": TEXT,
            "episode_id": TEXT,
            "event_index": POSITIVE,
            "base_revision": NONNEGATIVE,
            "checks": OBJECTS,
            "operations": OBJECTS,
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "accepted": {"type": "boolean"},
            "rejection_reasons": STRINGS,
        },
    ),
    "planning_problem_v1.schema.json": _document(
        "PlanningProblemV1",
        {
            "problem_id": TEXT,
            "source_method": TEXT,
            "source_revision": NONNEGATIVE,
            "initial_facts": OBJECTS,
            "active_goal_occurrence_ids": STRINGS,
            "remaining_goals": OBJECTS,
            "hard_constraints": OBJECTS,
            "soft_preferences": OBJECTS,
            "forbidden_regressions": STRINGS,
            "grounding_bindings": OBJECTS,
            "restore_eligibility": OBJECTS,
            "progress_certificates": OBJECTS,
            "continuation_assumptions": OBJECT,
        },
    ),
    "progress_certificate_v1.schema.json": _document(
        "ProgressCertificateV1",
        {
            "milestone_id": TEXT,
            "predicate": TEXT,
            "arguments": {"type": "array", "items": {"type": "string"}},
            "satisfaction": TEXT,
            "verifier_record_id": TEXT,
            "evidence_ids": {**STRINGS, "minItems": 1},
            "verified_at_step": NONNEGATIVE,
            "affected_by_event_ids": STRINGS,
            "currently_preserved": {"type": "boolean"},
        },
    ),
    "sealed_outcome_v1.schema.json": _document(
        "SealedOutcomeV1",
        {"evaluation_id": TEXT, "event_id": TEXT, "outcomes": OBJECT, "hidden_truth_sha256": SHA256},
    ),
    "runtime_trace_bundle_v1.schema.json": _document(
        "RuntimeTraceBundleV1",
        {
            "schema_version": {"const": CONTRACT_VERSION},
            "canonical_serialization_version": {"const": CANONICAL_SERIALIZATION_VERSION},
            "occurrence_allocator_version": {"const": OCCURRENCE_ALLOCATOR_VERSION},
            "trace_id": TEXT,
            "episode_id": TEXT,
            "public_events": OBJECTS,
            "ledger_snapshots": OBJECTS,
            "execution_context_snapshots": OBJECTS,
            "patches": OBJECTS,
            "planning_problems": OBJECTS,
            "progress_certificates": OBJECTS,
            "sealed_outcome_ref": {"anyOf": [SHA256, {"type": "null"}]},
        },
    ),
}
