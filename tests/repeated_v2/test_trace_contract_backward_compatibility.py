from cope_benchmark.repeated_v2.enums import (
    CommitmentRole, GroundingValidity, Lifecycle, MethodName, Satisfaction,
)
from cope_benchmark.repeated_v2.schema import (
    CommitmentOccurrence, PersistentLedger, PlanningProblem, ProgressCertificate,
    PublicEventPayload,
)
from cope_benchmark.repeated_v2.trace_contract_v1 import TRACE_CONTRACT_VERSION
from cope_benchmark.repeated_v2.trace_exporter_v1 import (
    persistent_ledger_snapshot_v1, planning_problem_v1, progress_certificate_v1,
    public_event_evidence_v1,
)


def test_existing_public_event_and_ledger_project_without_semantic_repair():
    event = PublicEventPayload("event-1", 1, "estimated target pose changed", .7,
                               ("evidence-1",), 3, "detector")
    slot = CommitmentOccurrence(
        "goal:item", "goal:item@1", CommitmentRole.ACHIEVEMENT_GOAL, "inside",
        ("item", "bin"), Lifecycle.SUSPENDED, GroundingValidity.UNKNOWN, 1, "hard",
        "task", "user", evidence_ids=("evidence-1",))
    ledger = PersistentLedger(7, (slot,))
    projected_event = public_event_evidence_v1(event)
    projected_ledger = persistent_ledger_snapshot_v1(ledger)
    assert projected_event.schema_version == TRACE_CONTRACT_VERSION
    assert projected_event.hypothesis == event.hypothesis
    assert projected_ledger.to_dict()["slots"] == [slot.to_dict()]
    assert projected_ledger.revision == 7


def test_existing_planning_problem_projection_preserves_omissions():
    progress = ProgressCertificate("m1", "inside", ("item", "bin"),
                                   Satisfaction.SATISFIED, "verify-1", ("evidence-1",), 2)
    original = PlanningProblem(
        "problem-1", MethodName.FULL_STATE_REGENERATION, 4, (), (), (), (), (), (), (), (),
        (progress,), {"resumable_suffix": []})
    projected = planning_problem_v1(original)
    assert projected.active_goal_occurrence_ids == ()
    assert projected.remaining_goals == ()
    assert projected.progress_certificates == (progress_certificate_v1(progress),)
    assert projected.source_method is MethodName.FULL_STATE_REGENERATION
