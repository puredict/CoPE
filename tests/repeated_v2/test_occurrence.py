from dataclasses import replace

import pytest

from cope_benchmark.repeated_v2.canonical import canonical_sha256
from cope_benchmark.repeated_v2.enums import CommitmentRole, GroundingValidity, Lifecycle
from cope_benchmark.repeated_v2.occurrence import OccurrenceAllocator, RevalidationRecord, restore_occurrence_id, validate_occurrences
from cope_benchmark.repeated_v2.schema import CommitmentOccurrence, PersistentLedger


def occurrence(**changes):
    values = dict(family_key="goal:inside:mug:cabinet", occurrence_id="goal:inside:mug:cabinet@1",
                  role=CommitmentRole.ACHIEVEMENT_GOAL, predicate="inside", arguments=("mug", "cabinet"),
                  lifecycle=Lifecycle.ACTIVE, grounding_validity=GroundingValidity.VALID, priority=1,
                  hardness="hard", source="task", authority="user", restore_guard={"reachable": True})
    values.update(changes)
    return CommitmentOccurrence(**values)


def test_reissue_assigns_new_id_and_keeps_retired_occurrence_auditable():
    retired = occurrence(lifecycle=Lifecycle.EXPIRED, retired_event_id="event-1")
    before = retired.sha256
    allocator = OccurrenceAllocator.from_ledger(PersistentLedger(1, (retired,)))
    new_id = allocator.reissue(retired)
    assert new_id == retired.family_key + "@2"
    assert retired.sha256 == before
    assert allocator.reissue(retired) == retired.family_key + "@3"
    validate_occurrences((retired, replace(occurrence(), occurrence_id=new_id)))


def test_allocation_determinism_and_history_maximum_not_slot_order():
    first = occurrence(lifecycle=Lifecycle.EXPIRED, retired_event_id="event-1")
    second = replace(first, occurrence_id=first.family_key + "@7")
    left, right = OccurrenceAllocator((first, second)), OccurrenceAllocator((second, first))
    assert left.allocate(first.family_key) == right.allocate(first.family_key) == first.family_key + "@8"
    assert left.snapshot() == right.snapshot()
    left.snapshot()[first.family_key] = 99
    assert left.allocate(first.family_key).endswith("@9")


def test_allocator_cannot_accept_model_occurrence_id_and_reissue_requires_retirement():
    allocator = OccurrenceAllocator((occurrence(),))
    with pytest.raises(TypeError):
        allocator.allocate(occurrence().family_key, occurrence_id="model-choice")
    with pytest.raises(ValueError, match="retired"):
        allocator.reissue(occurrence(lifecycle=Lifecycle.SUSPENDED))
    with pytest.raises(ValueError, match="trusted history"):
        OccurrenceAllocator().reissue(occurrence(lifecycle=Lifecycle.OVERRIDDEN, retired_event_id="e1"))


def test_exclusive_family_and_identity_validation():
    with pytest.raises(ValueError, match="multiple active"):
        validate_occurrences((occurrence(), occurrence(occurrence_id=occurrence().family_key + "@2")))
    for invalid in ("goal@0", "mismatched@1", occurrence().family_key + "@01"):
        with pytest.raises(ValueError, match="occurrence ID"):
            OccurrenceAllocator((occurrence(occurrence_id=invalid),))


def test_reissue_rejects_forged_retirement_or_historical_gap():
    active = occurrence()
    known_retired = occurrence(occurrence_id=active.family_key + "@5", lifecycle=Lifecycle.EXPIRED, retired_event_id="e1")
    forged = replace(active, lifecycle=Lifecycle.EXPIRED, retired_event_id="invented-event")
    for allocator in (OccurrenceAllocator((active,)), OccurrenceAllocator((known_retired,))):
        with pytest.raises(ValueError, match="trusted history"):
            allocator.reissue(forged)


def validation(slot):
    return RevalidationRecord("v1", slot.occurrence_id, "event-2", 2, 21, 1, True,
                              canonical_sha256(slot.restore_guard), ("fresh-evidence",))


def restore(slot, record):
    return restore_occurrence_id(slot, record, event_id="event-2", event_index=2,
                                 source_revision=1, latest_invalidation_timestamp=20)


def test_restore_preserves_identity_and_never_allocates():
    suspended = occurrence(lifecycle=Lifecycle.SUSPENDED)
    allocator = OccurrenceAllocator((suspended,))
    before = allocator.snapshot()
    assert restore(suspended, validation(suspended)) == suspended.occurrence_id
    assert allocator.snapshot() == before


@pytest.mark.parametrize("changes", [{"success": False}, {"timestamp": 20}, {"event_index": 1},
    {"event_id": "old-event"}, {"source_revision": 0}, {"occurrence_id": "wrong@1"},
    {"restore_guard_sha256": "wrong"}])
def test_restore_requires_fresh_successful_current_guard_evidence(changes):
    suspended = occurrence(lifecycle=Lifecycle.SUSPENDED)
    with pytest.raises(ValueError):
        restore(suspended, replace(validation(suspended), **changes))


@pytest.mark.parametrize("lifecycle", [Lifecycle.ACTIVE, Lifecycle.EXPIRED, Lifecycle.OVERRIDDEN])
def test_retired_goal_cannot_restore(lifecycle):
    item = occurrence(lifecycle=lifecycle, retired_event_id=None if lifecycle is Lifecycle.ACTIVE else "e1")
    with pytest.raises(ValueError, match="only suspended"):
        restore(item, validation(item))
