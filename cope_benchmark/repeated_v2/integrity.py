"""Integrity-first eligibility checks for repeated-interruption event cells."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from .journal import (
    AMBIGUOUS_CALL, DurableJournal, JournalError, KeyInput, cell_key, key_string, stable_hash,
)


@dataclass(frozen=True)
class IntegrityReport:
    status: str
    valid: bool
    expected_count: int
    result_count: int
    missing: tuple[str, ...] = ()
    duplicates: tuple[str, ...] = ()
    unexpected: tuple[str, ...] = ()
    ambiguous: tuple[str, ...] = ()
    missing_snapshots: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def require_valid(self) -> None:
        if not self.valid:
            raise RunIntegrityError(self)


class RunIntegrityError(JournalError):
    status = "INVALID_RUN"

    def __init__(self, report: IntegrityReport) -> None:
        self.report = report
        super().__init__("event-cell completeness or provenance verification failed")


def inspect_integrity(journal: DurableJournal, expected_cells: Iterable[KeyInput], *,
                      require_snapshots: bool = True,
                      snapshot_label: str = "post",
                      scope: tuple[str, str, str] | None = None) -> IntegrityReport:
    """Validate the exact preregistered cell set before any outcome analysis.

    A no-provider method still needs a result and verified event snapshot. Missing
    cells, unexpected attempted calls, ambiguous calls, and duplicate manifest
    expectations all invalidate the run. A scope checks one protocol/master/method
    trajectory in a shared journal; every expected cell must belong to that scope.
    This function never deletes a result.
    """
    expected_list = [cell_key(key) for key in expected_cells]
    if scope is not None:
        scope = cell_key((*scope, 0))[:3]
        if any(key[:3] != scope for key in expected_list):
            raise JournalError("expected cell does not belong to the integrity scope")
    expected = set(expected_list)
    duplicates = tuple(sorted(key_string(key) for key, n in Counter(expected_list).items()
                              if n > 1))
    errors: list[str] = []
    try:
        with journal._owned():
            journal._check_frozen()
            journal._validate_records()
            intents = journal.records("intents")
            responses = journal.records("responses")
            results = journal.records("results")
            if scope is not None:
                intents = {key: value for key, value in intents.items() if key[:3] == scope}
                responses = {key: value for key, value in responses.items() if key[:3] == scope}
                results = {key: value for key, value in results.items() if key[:3] == scope}
    except JournalError as exc:
        return IntegrityReport("INVALID_RUN", False, len(expected), 0,
                               duplicates=duplicates, errors=(str(exc),))
    actual = set(results)
    missing = tuple(sorted(key_string(key) for key in expected - actual))
    unexpected = tuple(sorted(key_string(key) for key in
                              (actual | set(intents) | set(responses)) - expected))
    ambiguous = tuple(sorted(key_string(key) for key in
                             (set(intents) - set(responses)) |
                             {key for key, value in results.items()
                              if value.get("status") == AMBIGUOUS_CALL}))
    missing_snapshots: list[str] = []
    if require_snapshots:
        for key in sorted(actual & expected):
            try:
                result = results[key]
                if result.get("status") == "EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE":
                    source_index = result.get("source_boundary_event_index")
                    if type(source_index) is not int or not 0 <= source_index < key[3]:
                        raise JournalError("unreached cell lacks a prior source boundary")
                    source_key = (*key[:3], source_index)
                    source = journal.load_snapshot(source_key, label=snapshot_label)
                    if result.get("source_boundary_sha256") != stable_hash(source):
                        raise JournalError("unreached cell source boundary hash mismatch")
                    if source_key not in actual:
                        raise JournalError("unreached cell source boundary has no durable result")
                    source_result = results[source_key]
                    source_status = source_result.get("status")
                    if (not isinstance(source_status, str) or not source_status
                            or source_status in {"COMPLETED", "COMPLETE", "SUCCESS", "VALID",
                                                 "EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE"}):
                        raise JournalError("unreached cell source is not a reached failure boundary")
                    if result.get("prior_failure") != source_status:
                        raise JournalError("unreached cell failure differs from its source boundary")
                    if (source.get("index") != source_index or source.get("delivered") != source_index
                            or source.get("pending_result") != source_result):
                        raise JournalError("unreached cell source snapshot does not bind its durable result")
                    if (result.get("success") is not False or result.get("high_level_calls") != 0
                            or key in intents or key in responses):
                        raise JournalError("unreached cell cannot claim success or adaptation calls")
                    if any(other[:3] == key[:3] and other[3] > source_index
                           and value.get("status") != "EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE"
                           for other, value in results.items()):
                        raise JournalError("unreached cell does not reference the final reached boundary")
                else:
                    journal.load_snapshot(key, label=snapshot_label)
            except JournalError as exc:
                missing_snapshots.append(key_string(key))
                errors.append(str(exc))
    valid = not any((missing, duplicates, unexpected, ambiguous, missing_snapshots, errors))
    return IntegrityReport("VALID" if valid else "INVALID_RUN", valid,
                           len(expected), len(actual), missing, duplicates, unexpected,
                           ambiguous, tuple(missing_snapshots), tuple(errors))
