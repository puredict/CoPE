"""Canonical exporters from the repeated-v2 runtime into trace contract v1."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .canonical import canonical_json, canonical_sha256
from .schema import (
    ExecutionContext, MethodProposal, PersistentLedger, PlanningProblem,
    ProgressCertificate, PublicEventPayload,
)
from .trace_contract_v1 import (
    AcceptedPatchRecordV1, ActionTraceReferenceV1, ExecutionContextSnapshotV1,
    OCCURRENCE_ALLOCATOR_VERSION, OccurrenceAllocatorVersionV1, PlanningProblemV1,
    ProgressCertificateV1, ProposedPatchRecordV1, PublicEventEvidenceV1,
    PersistentLedgerSnapshotV1, RuntimeTraceBundleV1, SealedOutcomeV1,
    TRACE_CONTRACT_VERSION,
)
from .trace_contract_validation_v1 import (
    load_canonical_record, validate_public_bundle, validate_sealed_outcome,
)


def progress_certificate_v1(value: ProgressCertificate | Mapping[str, Any]) -> ProgressCertificateV1:
    data = value.to_dict() if isinstance(value, ProgressCertificate) else dict(value)
    return ProgressCertificateV1(schema_version=TRACE_CONTRACT_VERSION, **data)


def public_event_evidence_v1(value: PublicEventPayload | Mapping[str, Any]) -> PublicEventEvidenceV1:
    data = value.to_dict() if isinstance(value, PublicEventPayload) else dict(value)
    return PublicEventEvidenceV1(schema_version=TRACE_CONTRACT_VERSION, **data)


def persistent_ledger_snapshot_v1(value: PersistentLedger | Mapping[str, Any]) -> PersistentLedgerSnapshotV1:
    data = value.to_dict() if isinstance(value, PersistentLedger) else dict(value)
    return PersistentLedgerSnapshotV1(schema_version=TRACE_CONTRACT_VERSION, **data)


def execution_context_snapshot_v1(value: ExecutionContext | Mapping[str, Any], *,
                                  captured_at_step: int | None = None) -> ExecutionContextSnapshotV1:
    data = value.to_dict() if isinstance(value, ExecutionContext) else dict(value)
    progress = tuple(progress_certificate_v1(item) for item in data["progress"])
    continuation = data["continuation"]
    step = continuation.get("captured_at_step") if captured_at_step is None else captured_at_step
    if type(step) is not int or step < 0:
        raise ValueError("execution context requires captured_at_step")
    return ExecutionContextSnapshotV1(
        schema_version=TRACE_CONTRACT_VERSION,
        beliefs=tuple(data["beliefs"]),
        progress=progress,
        continuation=continuation,
        captured_at_step=step,
    )


def planning_problem_v1(value: PlanningProblem | Mapping[str, Any]) -> PlanningProblemV1:
    data = value.to_dict() if isinstance(value, PlanningProblem) else dict(value)
    data["progress_certificates"] = tuple(
        progress_certificate_v1(item) for item in data["progress_certificates"])
    return PlanningProblemV1(schema_version=TRACE_CONTRACT_VERSION, **data)


def proposed_patch_record_v1(value: MethodProposal | Mapping[str, Any], *,
                             proposal_id: str, input_evidence_sha256: str,
                             proposed_at_ns: int) -> ProposedPatchRecordV1:
    data = value.to_dict() if isinstance(value, MethodProposal) else dict(value)
    return ProposedPatchRecordV1(
        schema_version=TRACE_CONTRACT_VERSION,
        method=data["method"], event_id=data["event_id"], proposal_id=proposal_id,
        raw_patch=data["raw_output"], input_evidence_sha256=input_evidence_sha256,
        proposed_at_ns=proposed_at_ns,
    )


def occurrence_allocator_version_v1(implementation_sha256: str) -> OccurrenceAllocatorVersionV1:
    return OccurrenceAllocatorVersionV1(
        schema_version=TRACE_CONTRACT_VERSION,
        allocator_id=OCCURRENCE_ALLOCATOR_VERSION,
        occurrence_id_pattern="<family_key>@<positive_monotone_integer>",
        implementation_sha256=implementation_sha256,
    )


def export_runtime_trace_bundle_v1(*, trace_id: str, master_session_id: str,
        method: Any, protocol: Any, task_id: int, initial_state_id: int,
        schedule_realization_id: str, occurrence_allocator: OccurrenceAllocatorVersionV1,
        public_events: Sequence[PublicEventPayload | Mapping[str, Any]] = (),
        ledger_snapshots: Sequence[PersistentLedger | Mapping[str, Any]] = (),
        execution_context_snapshots: Sequence[ExecutionContext | Mapping[str, Any]] = (),
        proposed_patches: Sequence[ProposedPatchRecordV1] = (),
        accepted_patches: Sequence[AcceptedPatchRecordV1] = (),
        planning_problems: Sequence[PlanningProblem | Mapping[str, Any]] = (),
        planner_decisions: Sequence[Mapping[str, Any]] = (),
        skill_calls: Sequence[Mapping[str, Any]] = (),
        action_traces: Sequence[ActionTraceReferenceV1] = (),
        runtime_verifier_outputs: Sequence[Mapping[str, Any]] = (),
        progress_certificates: Sequence[ProgressCertificate | Mapping[str, Any]] = (),
        sealed_outcome_ref: str, created_at_ns: int) -> RuntimeTraceBundleV1:
    bundle = RuntimeTraceBundleV1(
        schema_version=TRACE_CONTRACT_VERSION,
        trace_id=trace_id, master_session_id=master_session_id,
        method=method, protocol=protocol, task_id=task_id,
        initial_state_id=initial_state_id,
        schedule_realization_id=schedule_realization_id,
        occurrence_allocator=occurrence_allocator,
        public_events=tuple(public_event_evidence_v1(item) for item in public_events),
        ledger_snapshots=tuple(persistent_ledger_snapshot_v1(item) for item in ledger_snapshots),
        execution_context_snapshots=tuple(execution_context_snapshot_v1(item) for item in execution_context_snapshots),
        proposed_patches=tuple(proposed_patches), accepted_patches=tuple(accepted_patches),
        planning_problems=tuple(planning_problem_v1(item) for item in planning_problems),
        planner_decisions=tuple(planner_decisions), skill_calls=tuple(skill_calls),
        action_traces=tuple(action_traces), runtime_verifier_outputs=tuple(runtime_verifier_outputs),
        progress_certificates=tuple(progress_certificate_v1(item) for item in progress_certificates),
        sealed_outcome_ref=sealed_outcome_ref, created_at_ns=created_at_ns,
    )
    return validate_public_bundle(bundle)


def _exclusive_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    try:
        payload = (canonical_json(value) + "\n").encode("utf-8")
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_runtime_trace_bundle_v1(path: str | Path, bundle: RuntimeTraceBundleV1) -> str:
    checked = validate_public_bundle(bundle)
    _exclusive_write(Path(path), checked.to_dict())
    return canonical_sha256(checked)


def write_sealed_outcome_v1(path: str | Path, outcome: SealedOutcomeV1) -> str:
    checked = validate_sealed_outcome(outcome)
    _exclusive_write(Path(path), checked.to_dict())
    return canonical_sha256(checked)


def read_runtime_trace_bundle_v1(path: str | Path) -> RuntimeTraceBundleV1:
    return validate_public_bundle(load_canonical_record(path))


def read_sealed_outcome_v1(path: str | Path) -> SealedOutcomeV1:
    return validate_sealed_outcome(load_canonical_record(path))


__all__ = [
    "progress_certificate_v1", "public_event_evidence_v1",
    "persistent_ledger_snapshot_v1", "execution_context_snapshot_v1",
    "planning_problem_v1", "proposed_patch_record_v1",
    "occurrence_allocator_version_v1", "export_runtime_trace_bundle_v1",
    "write_runtime_trace_bundle_v1", "write_sealed_outcome_v1",
    "read_runtime_trace_bundle_v1", "read_sealed_outcome_v1",
]
