"""Trusted deterministic identity allocation, distinct from lifecycle mutation.

No operation here applies a model proposal or changes a ledger. Allocation is
kernel-owned, so a model requests a family and cannot choose its final ID.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .canonical import canonical_sha256
from .enums import CommitmentRole, Lifecycle
from .schema import CommitmentOccurrence, PersistentLedger, Record


def occurrence_number(family_key: str, occurrence_id: str) -> int:
    match = re.fullmatch(re.escape(family_key) + r"@([1-9][0-9]*)", occurrence_id)
    if match is None:
        raise ValueError("occurrence ID must be its family key followed by @positive-integer")
    return int(match.group(1))


def validate_occurrences(occurrences: Iterable[CommitmentOccurrence], *, exclusive_families: Iterable[str] | None = None) -> None:
    slots = tuple(occurrences)
    exclusive = set(exclusive_families) if exclusive_families is not None else {
        s.family_key for s in slots if s.role is CommitmentRole.ACHIEVEMENT_GOAL
    }
    seen: set[str] = set()
    active: set[str] = set()
    for slot in slots:
        occurrence_number(slot.family_key, slot.occurrence_id)
        if slot.occurrence_id in seen:
            raise ValueError("duplicate occurrence ID")
        seen.add(slot.occurrence_id)
        if slot.lifecycle is Lifecycle.ACTIVE and slot.family_key in exclusive:
            if slot.family_key in active:
                raise ValueError("exclusive goal family has multiple active occurrences")
            active.add(slot.family_key)


class OccurrenceAllocator:
    def __init__(self, existing: Iterable[CommitmentOccurrence] = ()) -> None:
        slots = tuple(existing)
        validate_occurrences(slots)
        self._known = {slot.occurrence_id: slot for slot in slots}
        self._maximum: dict[str, int] = {}
        for slot in slots:
            self._maximum[slot.family_key] = max(
                self._maximum.get(slot.family_key, 0), occurrence_number(slot.family_key, slot.occurrence_id)
            )

    @classmethod
    def from_ledger(cls, ledger: PersistentLedger) -> "OccurrenceAllocator":
        return cls(ledger.slots)

    def allocate(self, family_key: str) -> str:
        if type(family_key) is not str or not family_key.strip() or "@" in family_key:
            raise ValueError("family key must be nonempty and cannot contain @")
        number = self._maximum.get(family_key, 0) + 1
        self._maximum[family_key] = number
        return f"{family_key}@{number}"

    def reissue(self, retired: CommitmentOccurrence) -> str:
        if retired.lifecycle not in (Lifecycle.EXPIRED, Lifecycle.OVERRIDDEN):
            raise ValueError("reissue requires a retired occurrence; suspension requires restoration")
        if self._known.get(retired.occurrence_id) != retired:
            raise ValueError("reissued occurrence must belong to allocator's trusted history")
        return self.allocate(retired.family_key)

    def snapshot(self) -> dict[str, int]:
        return dict(sorted(self._maximum.items()))


@dataclass(frozen=True)
class RevalidationRecord(Record):
    validation_id: str
    occurrence_id: str
    event_id: str
    event_index: int
    timestamp: int
    source_revision: int
    success: bool
    restore_guard_sha256: str
    evidence_ids: tuple[str, ...]

    def _validate(self) -> None:
        if not self.evidence_ids or self.event_index < 1:
            raise ValueError("revalidation requires evidence and an event index")


def restore_occurrence_id(
    occurrence: CommitmentOccurrence, validation: RevalidationRecord, *,
    event_id: str, event_index: int, source_revision: int,
    latest_invalidation_timestamp: int,
) -> str:
    """Check a verifier-owned fresh guard certificate and retain the same ID.

    This helper does not perform a state transition. The later atomic kernel
    must obtain this certificate from its trusted verifier, never the model.
    """
    if occurrence.lifecycle is not Lifecycle.SUSPENDED:
        raise ValueError("only suspended occurrences may be restored; reissue retired goals")
    if not occurrence.restore_guard:
        raise ValueError("restore requires an explicit guard")
    if not validation.success or validation.occurrence_id != occurrence.occurrence_id:
        raise ValueError("unsuccessful or wrong-occurrence revalidation")
    if (validation.event_id, validation.event_index, validation.source_revision) != (event_id, event_index, source_revision):
        raise ValueError("stale revalidation event or revision")
    if validation.timestamp <= latest_invalidation_timestamp:
        raise ValueError("restore requires fresh post-invalidation evidence")
    if validation.restore_guard_sha256 != canonical_sha256(occurrence.restore_guard):
        raise ValueError("revalidation does not certify the current restore guard")
    return occurrence.occurrence_id
