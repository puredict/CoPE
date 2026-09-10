import hashlib
from pathlib import Path

import pytest

from cope_benchmark.repeated_v2.enums import (
    CommitmentRole, GroundingValidity, Lifecycle, MethodName, ProtocolName, Satisfaction,
)
from cope_benchmark.repeated_v2.schema import (
    BeliefFact, CommitmentOccurrence, ContinuationState, ExecutionContext,
    PersistentLedger, PlanningProblem, ProgressCertificate, PublicEventPayload,
)
from cope_benchmark.repeated_v2.trace_contract_v1 import SealedOutcomeV1, TRACE_CONTRACT_VERSION
from cope_benchmark.repeated_v2.trace_exporter_v1 import (
    export_runtime_trace_bundle_v1, occurrence_allocator_version_v1,
    read_runtime_trace_bundle_v1, read_sealed_outcome_v1,
    write_runtime_trace_bundle_v1, write_sealed_outcome_v1,
)


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def runtime_values():
    event = PublicEventPayload("event-1", 1, "estimated cup pose changed", .8,
                               ("evidence-1",), 5, "shared detector", ("obs-2",))
    slot = CommitmentOccurrence(
        "goal:cup", "goal:cup@1", CommitmentRole.ACHIEVEMENT_GOAL, "inside",
        ("cup", "basket"), Lifecycle.ACTIVE, GroundingValidity.DEGRADED, 1, "hard",
        "task", "user", evidence_ids=("evidence-1",))
    ledger = PersistentLedger(0, (slot,))
    progress = ProgressCertificate("m1", "inside", ("cup", "basket"),
                                   Satisfaction.SATISFIED, "verify-1", ("evidence-1",), 4)
    context = ExecutionContext(
        (BeliefFact("cup_visible", True, .8, ("evidence-1",), 5),), (progress,),
        ContinuationState("transport", "place", 2, None, ("place",), "state-4", 4))
    problem = PlanningProblem("problem-1", MethodName.COPE_TYPED_EDIT, 0, (),
                              ("goal:cup@1",), ({"occurrence_id": "goal:cup@1"},),
                              (), (), ("m1",), (), (), (progress,), {})
    return event, ledger, progress, context, problem


def test_exporter_converts_existing_v2_records_and_roundtrips(tmp_path):
    event, ledger, progress, context, problem = runtime_values()
    outcome = SealedOutcomeV1(
        TRACE_CONTRACT_VERSION, "outcome-1", True, ("goal:cup@1",), (), (), (), (),
        True, False, False, "sealed_dynamic_v2.1", sha("truth"))
    allocator = occurrence_allocator_version_v1(sha("occurrence implementation"))
    bundle = export_runtime_trace_bundle_v1(
        trace_id="trace-1", master_session_id="session-1",
        method=MethodName.COPE_TYPED_EDIT, protocol=ProtocolName.END_TO_END,
        task_id=1, initial_state_id=6, schedule_realization_id="schedule-1",
        occurrence_allocator=allocator, public_events=(event,), ledger_snapshots=(ledger,),
        execution_context_snapshots=(context,), planning_problems=(problem,),
        runtime_verifier_outputs=({"verifier_record_id": "verify-1", "evidence_ids": ["evidence-1"]},),
        progress_certificates=(progress,), sealed_outcome_ref=outcome.sha256, created_at_ns=6)
    public_path, sealed_path = tmp_path / "trace.json", tmp_path / "sealed.json"
    assert write_runtime_trace_bundle_v1(public_path, bundle) == bundle.sha256
    assert write_sealed_outcome_v1(sealed_path, outcome) == outcome.sha256
    assert read_runtime_trace_bundle_v1(public_path) == bundle
    assert read_sealed_outcome_v1(sealed_path) == outcome
    with pytest.raises(FileExistsError):
        write_runtime_trace_bundle_v1(public_path, bundle)
