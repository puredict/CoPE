"""Bind formal analysis CSVs to their durable runner journals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from cope.formal_recovery import cell_key


class FormalArtifactError(ValueError):
    pass


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    return str(value)


def validate_event_results_artifacts(
    *, event_results: Path, csv_rows: Sequence[Mapping[str, str]],
    result_fields: Sequence[str], expected_manifest_sha256: str,
) -> None:
    """Require the analysis CSV to be an exact rendering of its fsync journal."""
    run_dir = event_results.parent
    metadata_path = run_dir / "00_RUN_METADATA.txt"
    journal_path = run_dir / "01_EVENT_JOURNAL.txt"
    if not metadata_path.is_file() or not journal_path.is_file():
        raise FormalArtifactError("formal result lacks colocated metadata or event journal")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FormalArtifactError("formal run metadata is invalid JSON") from exc
    if not isinstance(metadata, dict) or metadata.get("manifest_sha256") != expected_manifest_sha256:
        raise FormalArtifactError("formal run metadata manifest hash mismatch")

    records: dict[tuple[str, str, int], dict[str, Any]] = {}
    with journal_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.endswith("\n"):
                raise FormalArtifactError("formal event journal has a torn final line")
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise FormalArtifactError(
                    f"formal event journal line {line_number} is invalid JSON"
                ) from exc
            if not isinstance(record, dict) or set(record) != set(result_fields):
                raise FormalArtifactError("formal event journal record schema mismatch")
            key = cell_key(record)
            if key in records:
                raise FormalArtifactError("formal event journal contains a duplicate cell")
            records[key] = record

    csv_by_key: dict[tuple[str, str, int], Mapping[str, str]] = {}
    for row in csv_rows:
        if set(row) != set(result_fields):
            raise FormalArtifactError("formal result CSV schema mismatch")
        key = cell_key(row)
        if key in csv_by_key:
            raise FormalArtifactError("formal result CSV contains a duplicate cell")
        csv_by_key[key] = row
    if set(csv_by_key) != set(records):
        raise FormalArtifactError("formal result CSV and event journal cells differ")
    for key, row in csv_by_key.items():
        rendered = {field: _csv_text(records[key][field]) for field in result_fields}
        if dict(row) != rendered:
            raise FormalArtifactError(f"formal result CSV diverges from journal at {key}")
