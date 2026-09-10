"""Versioned, deterministic occurrence identity allocation."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

OCCURRENCE_ALLOCATOR_VERSION = "cope-exp1-occurrence-allocator/v1"


def occurrence_number(family_key: str, occurrence_id: str) -> int:
    match = re.fullmatch(re.escape(family_key) + r"@([1-9][0-9]*)", occurrence_id)
    if match is None:
        raise ValueError("occurrence ID must be family_key@positive-integer")
    return int(match.group(1))


class OccurrenceAllocatorV1:
    """Monotone allocator; it never mutates an Experiment-1 ledger."""

    version = OCCURRENCE_ALLOCATOR_VERSION

    def __init__(self, existing: Iterable[Mapping[str, object]] = ()) -> None:
        self._maximum: dict[str, int] = {}
        for slot in existing:
            family_key = slot.get("family_key")
            occurrence_id = slot.get("occurrence_id")
            if type(family_key) is not str or type(occurrence_id) is not str:
                raise ValueError("existing slots require string family_key and occurrence_id")
            number = occurrence_number(family_key, occurrence_id)
            self._maximum[family_key] = max(self._maximum.get(family_key, 0), number)

    def allocate(self, family_key: str) -> str:
        if type(family_key) is not str or not family_key.strip() or "@" in family_key:
            raise ValueError("family key must be nonempty and cannot contain @")
        number = self._maximum.get(family_key, 0) + 1
        self._maximum[family_key] = number
        return f"{family_key}@{number}"

    def snapshot(self) -> dict[str, int]:
        return dict(sorted(self._maximum.items()))
