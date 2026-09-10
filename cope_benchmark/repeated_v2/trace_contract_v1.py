"""Frozen, read-only Experiment-1 trace interchange contract.

The contract is intentionally independent of task eligibility and experimental
outcome.  It serializes only method-visible state into ``RuntimeTraceBundleV1``;
sealed scoring is a separate ``SealedOutcomeV1`` artifact referenced by digest.
"""

from __future__ import annotations

import re
from dataclasses import MISSING, dataclass, field, fields
from typing import Any, Mapping, get_type_hints

from .canonical import canonical_sha256, to_primitive
from .enums import MethodName, ProtocolName, Satisfaction
from .schema import Record, record_json_schema


TRACE_CONTRACT_VERSION = "exp1-trace-contract-v1"
OCCURRENCE_ALLOCATOR_VERSION = "occurrence-family-monotone-v1"
EXP1_INTERFACE_CONTRACT_FROZEN = "EXP1_INTERFACE_CONTRACT_FROZEN"
EXP1_TASK_CATALOG_FROZEN = "EXP1_TASK_CATALOG_FROZEN"
EXP1_FORMAL_TRACE_DATA_AVAILABLE = "EXP1_FORMAL_TRACE_DATA_AVAILABLE"
_HEX256 = re.compile(r"[0-9a-f]{64}\Z")


def _version(value: str) -> None:
    if value != TRACE_CONTRACT_VERSION:
        raise ValueError(f"trace contract version must be {TRACE_CONTRACT_VERSION}")


def _digest(value: str, name: str) -> None:
    if not _HEX256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA256")


def _distinct(values: tuple[str, ...], name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {name}")


@dataclass(frozen=True)
class OccurrenceAllocatorVersionV1(Record):
    schema_version: str
    allocator_id: str
    occurrence_id_pattern: str
    implementation_sha256: str

    def _validate(self) -> None:
        _version(self.schema_version)
        if self.allocator_id != OCCURRENCE_ALLOCATOR_VERSION:
            raise ValueError("unknown occurrence allocator")
        if self.occurrence_id_pattern != "<family_key>@<positive_monotone_integer>":
            raise ValueError("occurrence allocator pattern drift")
        _digest(self.implementation_sha256, "implementation_sha256")


@dataclass(frozen=True)
class ProgressCertificateV1(Record):
    schema_version: str
    milestone_id: str
    predicate: str
    arguments: tuple[str, ...]
    satisfaction: Satisfaction
    verifier_record_id: str
    evidence_ids: tuple[str, ...]
    verified_at_step: int
    affected_by_event_ids: tuple[str, ...] = ()
    currently_preserved: bool = True

    def _validate(self) -> None:
        _version(self.schema_version)
        if not self.evidence_ids:
            raise ValueError("progress certificate requires public evidence")
        _distinct(self.evidence_ids, "progress evidence IDs")
        if self.currently_preserved and self.satisfaction is not Satisfaction.SATISFIED:
            raise ValueError("preserved progress must be satisfied")


@dataclass(frozen=True)
class ActionTraceReferenceV1(Record):
    schema_version: str
    trace_id: str
    artifact_ref: str
    trace_sha256: str
    action_count: int
    action_space: str
    policy_id: str
    checkpoint_sha256: str

    def _validate(self) -> None:
        _version(self.schema_version)
        _digest(self.trace_sha256, "trace_sha256")
        _digest(self.checkpoint_sha256, "checkpoint_sha256")


@dataclass(frozen=True)
class PublicEventEvidenceV1(Record):
    schema_version: str
    event_id: str
    event_index: int
    hypothesis: str
    confidence: float
    evidence_ids: tuple[str, ...]
    timestamp: int
    provenance: str
    observation_refs: tuple[str, ...] = ()
    user_message: str | None = None
    affected_entity_hypotheses: tuple[str, ...] = ()

    def _validate(self) -> None:
        _version(self.schema_version)
        if self.event_index < 1 or not 0 <= self.confidence <= 1:
            raise ValueError("invalid public event index or confidence")
        if not self.evidence_ids:
            raise ValueError("public event requires evidence IDs")
        _distinct(self.evidence_ids, "event evidence IDs")


@dataclass(frozen=True)
class PersistentLedgerSnapshotV1(Record):
    schema_version: str
    revision: int
    slots: tuple[Mapping[str, Any], ...]
    relations: tuple[Mapping[str, Any], ...] = ()
    history_records: tuple[Mapping[str, Any], ...] = ()

    def _validate(self) -> None:
        _version(self.schema_version)
        ids = tuple(str(slot.get("occurrence_id", "")) for slot in self.slots)
        if any(not value for value in ids):
            raise ValueError("ledger snapshot slot lacks occurrence ID")
        _distinct(ids, "ledger occurrence IDs")


@dataclass(frozen=True)
class ExecutionContextSnapshotV1(Record):
    schema_version: str
    beliefs: tuple[Mapping[str, Any], ...]
    progress: tuple[ProgressCertificateV1, ...]
    continuation: Mapping[str, Any]
    captured_at_step: int

    def _validate(self) -> None:
        _version(self.schema_version)
        _distinct(tuple(p.milestone_id for p in self.progress), "progress milestones")


@dataclass(frozen=True)
class ProposedPatchRecordV1(Record):
    schema_version: str
    method: MethodName
    event_id: str
    proposal_id: str
    raw_patch: Mapping[str, Any]
    input_evidence_sha256: str
    proposed_at_ns: int

    def _validate(self) -> None:
        _version(self.schema_version)
        _digest(self.input_evidence_sha256, "input_evidence_sha256")


@dataclass(frozen=True)
class AcceptedPatchRecordV1(Record):
    schema_version: str
    method: MethodName
    event_id: str
    proposal_id: str
    accepted: bool
    accepted_patch: Mapping[str, Any] | None
    validation_status: str
    state_revision_before: int
    state_revision_after: int
    applied_at_ns: int
    rejection_reasons: tuple[str, ...] = ()

    def _validate(self) -> None:
        _version(self.schema_version)
        if self.accepted != (self.accepted_patch is not None):
            raise ValueError("accepted patch presence disagrees with decision")
        if self.accepted and self.state_revision_after != self.state_revision_before + 1:
            raise ValueError("accepted patch must advance exactly one revision")
        if not self.accepted and self.state_revision_after != self.state_revision_before:
            raise ValueError("rejected patch cannot advance revision")


@dataclass(frozen=True)
class PlanningProblemV1(Record):
    schema_version: str
    problem_id: str
    source_method: MethodName
    source_revision: int
    initial_facts: tuple[Mapping[str, Any], ...]
    active_goal_occurrence_ids: tuple[str, ...]
    remaining_goals: tuple[Mapping[str, Any], ...]
    hard_constraints: tuple[Mapping[str, Any], ...]
    soft_preferences: tuple[Mapping[str, Any], ...]
    forbidden_regressions: tuple[str, ...]
    grounding_bindings: tuple[Mapping[str, Any], ...]
    restore_eligibility: tuple[Mapping[str, Any], ...]
    progress_certificates: tuple[ProgressCertificateV1, ...]
    continuation_assumptions: Mapping[str, Any]

    def _validate(self) -> None:
        _version(self.schema_version)
        _distinct(self.active_goal_occurrence_ids, "active goal occurrence IDs")


@dataclass(frozen=True)
class SealedOutcomeV1(Record):
    schema_version: str
    outcome_id: str
    final_active_task_success: bool
    active_goal_occurrence_ids: tuple[str, ...]
    unsatisfied_goal_occurrence_ids: tuple[str, ...]
    wrong_occurrence_execution: tuple[str, ...]
    completed_step_regression: tuple[str, ...]
    hard_constraint_violations: tuple[str, ...]
    required_events_reached: bool
    timeout: bool
    manual_intervention: bool
    evaluator_version: str
    hidden_truth_sha256: str

    def _validate(self) -> None:
        _version(self.schema_version)
        _digest(self.hidden_truth_sha256, "hidden_truth_sha256")


@dataclass(frozen=True)
class RuntimeTraceBundleV1(Record):
    schema_version: str
    trace_id: str
    master_session_id: str
    method: MethodName
    protocol: ProtocolName
    task_id: int
    initial_state_id: int
    schedule_realization_id: str
    occurrence_allocator: OccurrenceAllocatorVersionV1
    public_events: tuple[PublicEventEvidenceV1, ...]
    ledger_snapshots: tuple[PersistentLedgerSnapshotV1, ...]
    execution_context_snapshots: tuple[ExecutionContextSnapshotV1, ...]
    proposed_patches: tuple[ProposedPatchRecordV1, ...]
    accepted_patches: tuple[AcceptedPatchRecordV1, ...]
    planning_problems: tuple[PlanningProblemV1, ...]
    planner_decisions: tuple[Mapping[str, Any], ...]
    skill_calls: tuple[Mapping[str, Any], ...]
    action_traces: tuple[ActionTraceReferenceV1, ...]
    runtime_verifier_outputs: tuple[Mapping[str, Any], ...]
    progress_certificates: tuple[ProgressCertificateV1, ...]
    sealed_outcome_ref: str
    created_at_ns: int

    def _validate(self) -> None:
        _version(self.schema_version)
        event_ids = tuple(event.event_id for event in self.public_events)
        _distinct(event_ids, "event IDs")
        if tuple(event.event_index for event in self.public_events) != tuple(range(1, len(event_ids) + 1)):
            raise ValueError("public event indices must be contiguous and ordered")
        _distinct(tuple(p.proposal_id for p in self.proposed_patches), "proposal IDs")
        proposed = {p.proposal_id for p in self.proposed_patches}
        if any(p.proposal_id not in proposed for p in self.accepted_patches):
            raise ValueError("accepted patch lacks proposed patch")
        if any(p.method is not self.method for p in (*self.proposed_patches, *self.accepted_patches)):
            raise ValueError("patch method differs from bundle method")
        if any(problem.source_method is not self.method for problem in self.planning_problems):
            raise ValueError("planning problem method differs from bundle method")
        _digest(self.sealed_outcome_ref, "sealed_outcome_ref")


def trace_json_schema(record_type: type[Record]) -> dict[str, Any]:
    """Return the frozen structural schema plus contract-version constraints."""
    schema = record_json_schema(record_type)
    for definition in schema.get("$defs", {}).values():
        properties = definition.get("properties", {})
        if "schema_version" in properties:
            properties["schema_version"] = {"const": TRACE_CONTRACT_VERSION}
        for name in ("trace_sha256", "checkpoint_sha256", "implementation_sha256", "hidden_truth_sha256",
                     "input_evidence_sha256", "sealed_outcome_ref"):
            if name in properties:
                properties[name] = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    return schema


def patch_record_json_schema() -> dict[str, Any]:
    proposed = trace_json_schema(ProposedPatchRecordV1)
    accepted = trace_json_schema(AcceptedPatchRecordV1)
    definitions = {**proposed.get("$defs", {}), **accepted.get("$defs", {})}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "PatchRecordV1",
        "oneOf": [{"$ref": proposed["$ref"]}, {"$ref": accepted["$ref"]}],
        "$defs": definitions,
    }


TRACE_RECORD_TYPES = {
    "runtime_trace_bundle": RuntimeTraceBundleV1,
    "public_event_evidence": PublicEventEvidenceV1,
    "persistent_ledger_snapshot": PersistentLedgerSnapshotV1,
    "execution_context_snapshot": ExecutionContextSnapshotV1,
    "planning_problem": PlanningProblemV1,
    "progress_certificate": ProgressCertificateV1,
    "sealed_outcome": SealedOutcomeV1,
}


def schema_required_fields(record_type: type[Record]) -> tuple[str, ...]:
    return tuple(member.name for member in fields(record_type)
                 if member.default is MISSING and member.default_factory is MISSING)


def contract_identity() -> dict[str, Any]:
    return {
        "schema_version": TRACE_CONTRACT_VERSION,
        "occurrence_allocator": OCCURRENCE_ALLOCATOR_VERSION,
        "record_types": tuple(sorted(cls.__name__ for cls in (
            RuntimeTraceBundleV1, PublicEventEvidenceV1, PersistentLedgerSnapshotV1,
            ExecutionContextSnapshotV1, ProposedPatchRecordV1, AcceptedPatchRecordV1,
            PlanningProblemV1, ProgressCertificateV1, ActionTraceReferenceV1,
            SealedOutcomeV1, OccurrenceAllocatorVersionV1,
        ))),
        "required_fields": {
            cls.__name__: schema_required_fields(cls) for cls in (
                RuntimeTraceBundleV1, PublicEventEvidenceV1, PersistentLedgerSnapshotV1,
                ExecutionContextSnapshotV1, ProposedPatchRecordV1, AcceptedPatchRecordV1,
                PlanningProblemV1, ProgressCertificateV1, ActionTraceReferenceV1,
                SealedOutcomeV1, OccurrenceAllocatorVersionV1,
            )
        },
    }


def experiment1_dependency_gates(*, interface_contract_frozen: bool,
                                 task_catalog_frozen: bool,
                                 formal_trace_data_available: bool) -> dict[str, bool]:
    """Expose independent downstream gates; interface freeze has no data dependency."""
    if any(type(value) is not bool for value in (
            interface_contract_frozen, task_catalog_frozen, formal_trace_data_available)):
        raise ValueError("Experiment-1 gate states must be booleans")
    return {
        EXP1_INTERFACE_CONTRACT_FROZEN: interface_contract_frozen,
        EXP1_TASK_CATALOG_FROZEN: task_catalog_frozen,
        EXP1_FORMAL_TRACE_DATA_AVAILABLE: formal_trace_data_available,
    }


__all__ = [
    "TRACE_CONTRACT_VERSION", "OCCURRENCE_ALLOCATOR_VERSION",
    "RuntimeTraceBundleV1", "PublicEventEvidenceV1", "PersistentLedgerSnapshotV1",
    "ExecutionContextSnapshotV1", "ProposedPatchRecordV1", "AcceptedPatchRecordV1",
    "PlanningProblemV1", "ProgressCertificateV1", "ActionTraceReferenceV1",
    "SealedOutcomeV1", "OccurrenceAllocatorVersionV1", "trace_json_schema",
    "patch_record_json_schema", "contract_identity", "experiment1_dependency_gates",
    "EXP1_INTERFACE_CONTRACT_FROZEN", "EXP1_TASK_CATALOG_FROZEN",
    "EXP1_FORMAL_TRACE_DATA_AVAILABLE",
]
