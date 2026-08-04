"""Durable at-most-once ledger for formal provider calls."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from cope.types import canonical_json


CELL_FIELDS = ("sequence_id", "arm", "event_index")
AMBIGUOUS_FAILURE = "ambiguous_interrupted_call_no_retry"
INFRASTRUCTURE_FAILURE_MARKERS = (
    "provider_timeout", "provider_transport_outage", "provider_http_",
    AMBIGUOUS_FAILURE,
)
INFRASTRUCTURE_STOP_FILE = "05_INFRASTRUCTURE_STOP.txt"


class FormalRecoveryError(RuntimeError):
    pass


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def cell_key(payload: Mapping[str, Any]) -> tuple[str, str, int]:
    try:
        key = (
            str(payload["sequence_id"]),
            str(payload["arm"]),
            int(payload["event_index"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalRecoveryError("journal record has an invalid cell key") from exc
    if not key[0] or not key[1] or key[2] not in (1, 2):
        raise FormalRecoveryError("journal record has a noncanonical cell key")
    return key


def _append_fsynced(path: Path, payload: Mapping[str, Any]) -> None:
    existed = path.exists()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(dict(payload)) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    if not existed:
        _fsync_directory(path.parent)


def _write_exclusive_fsynced(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(canonical_json(dict(payload)) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)


def is_infrastructure_failure(failure_class: Any) -> bool:
    text = str(failure_class)
    return any(marker in text for marker in INFRASTRUCTURE_FAILURE_MARKERS)


def freeze_infrastructure_stop(
    output_dir: Path, *, failure_class: str, cell: Mapping[str, Any],
) -> Path:
    path = output_dir / INFRASTRUCTURE_STOP_FILE
    _write_exclusive_fsynced(path, {
        "schema": "formal-infrastructure-stop-v1",
        "gate": "INVALID_INFRASTRUCTURE_FAILURE",
        "failure_class": failure_class,
        "cell": {field: cell[field] for field in CELL_FIELDS},
        "resume_forbidden": True,
        "provider_calls_after_stop": 0,
    })
    return path


def _load_unique(path: Path, label: str) -> dict[tuple[str, str, int], dict[str, Any]]:
    records: dict[tuple[str, str, int], dict[str, Any]] = {}
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.endswith("\n"):
                raise FormalRecoveryError(f"{label} has a torn final line")
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise FormalRecoveryError(
                    f"{label} line {line_number} is not valid JSON"
                ) from exc
            if not isinstance(payload, dict):
                raise FormalRecoveryError(f"{label} line {line_number} is not an object")
            key = cell_key(payload)
            if key in records:
                raise FormalRecoveryError(f"{label} contains duplicate cell {key}")
            records[key] = payload
    return records


class FormalRecoveryLedger:
    """Intent -> response -> result journal with strict resume validation."""

    def __init__(self, output_dir: Path, metadata: Mapping[str, Any], *, resume: bool) -> None:
        self.output_dir = output_dir
        self.metadata_path = output_dir / "00_RUN_METADATA.txt"
        self.result_path = output_dir / "01_EVENT_JOURNAL.txt"
        self.response_path = output_dir / "02_PROVIDER_TRACES.txt"
        self.intent_path = output_dir / "04_CALL_INTENTS.txt"
        frozen = dict(metadata)
        if resume:
            if not output_dir.is_dir() or not self.metadata_path.is_file():
                raise FormalRecoveryError("resume directory lacks frozen run metadata")
            try:
                recorded = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise FormalRecoveryError("frozen run metadata is invalid") from exc
            if canonical_json(recorded) != canonical_json(frozen):
                raise FormalRecoveryError("resume metadata does not match the frozen run")
        else:
            if output_dir.exists():
                raise FileExistsError(output_dir)
            output_dir.mkdir(parents=True, exist_ok=False)
            _fsync_directory(output_dir.parent)
            _write_exclusive_fsynced(self.metadata_path, frozen)
        self.intents = _load_unique(self.intent_path, "call-intent journal")
        self.responses = _load_unique(self.response_path, "provider-response journal")
        self.results = _load_unique(self.result_path, "event-result journal")
        self._validate_cross_journal_state()

    def _validate_cross_journal_state(self) -> None:
        if not set(self.responses).issubset(self.intents):
            raise FormalRecoveryError("a provider response lacks a durable call intent")
        for key, result in self.results.items():
            if not bool(result.get("provider_called", False)):
                continue
            if key not in self.intents:
                raise FormalRecoveryError("a called result lacks a durable call intent")
            ambiguous = AMBIGUOUS_FAILURE in str(result.get("failure_class", ""))
            if ambiguous:
                if key in self.responses:
                    raise FormalRecoveryError("an ambiguous result has a provider response")
            elif key not in self.responses:
                raise FormalRecoveryError("a called result lacks a durable provider response")

    def record_intent(self, payload: Mapping[str, Any]) -> None:
        record = dict(payload)
        key = cell_key(record)
        if key in self.intents or key in self.responses or key in self.results:
            raise FormalRecoveryError(f"cannot duplicate call intent for {key}")
        _append_fsynced(self.intent_path, record)
        self.intents[key] = record

    def record_response(self, payload: Mapping[str, Any]) -> None:
        record = dict(payload)
        key = cell_key(record)
        if key not in self.intents:
            raise FormalRecoveryError(f"provider response lacks intent for {key}")
        if key in self.responses:
            raise FormalRecoveryError(f"cannot duplicate provider response for {key}")
        _append_fsynced(self.response_path, record)
        self.responses[key] = record

    def record_result(self, payload: Mapping[str, Any]) -> None:
        record = dict(payload)
        key = cell_key(record)
        if key in self.results:
            raise FormalRecoveryError(f"cannot duplicate event result for {key}")
        if bool(record.get("provider_called", False)):
            if key not in self.intents:
                raise FormalRecoveryError(f"called result lacks intent for {key}")
            ambiguous = AMBIGUOUS_FAILURE in str(record.get("failure_class", ""))
            if ambiguous:
                if key in self.responses:
                    raise FormalRecoveryError(f"ambiguous result has response for {key}")
            elif key not in self.responses:
                raise FormalRecoveryError(f"called result lacks response for {key}")
        _append_fsynced(self.result_path, record)
        self.results[key] = record

    def phase(self, key: tuple[str, str, int]) -> str:
        if key in self.results:
            return "result"
        if key in self.responses:
            return "response"
        if key in self.intents:
            return "ambiguous_intent"
        return "new"
