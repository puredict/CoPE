import csv
import json

import pytest

from cope.formal_artifact_validation import (
    FormalArtifactError, validate_event_results_artifacts,
)


FIELDS = ("sequence_id", "arm", "event_index", "value")


def artifacts(tmp_path, *, csv_value=True, journal_value=True):
    run = tmp_path / "run"
    run.mkdir()
    rows = [{
        "sequence_id": "s", "arm": "cope", "event_index": 1,
        "value": csv_value,
    }]
    result = run / "03_EVENT_RESULTS.csv"
    with result.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    (run / "00_RUN_METADATA.txt").write_text(
        json.dumps({"manifest_sha256": "abc"}) + "\n"
    )
    (run / "01_EVENT_JOURNAL.txt").write_text(json.dumps({
        "sequence_id": "s", "arm": "cope", "event_index": 1,
        "value": journal_value,
    }) + "\n")
    with result.open(newline="") as handle:
        parsed = list(csv.DictReader(handle))
    return result, parsed


def test_formal_artifacts_require_exact_csv_journal_rendering(tmp_path):
    result, rows = artifacts(tmp_path)
    validate_event_results_artifacts(
        event_results=result, csv_rows=rows, result_fields=FIELDS,
        expected_manifest_sha256="abc",
    )


def test_formal_artifacts_reject_csv_journal_drift(tmp_path):
    result, rows = artifacts(tmp_path, csv_value=True, journal_value=False)
    with pytest.raises(FormalArtifactError, match="diverges from journal"):
        validate_event_results_artifacts(
            event_results=result, csv_rows=rows, result_fields=FIELDS,
            expected_manifest_sha256="abc",
        )


def test_formal_artifacts_reject_manifest_or_torn_journal(tmp_path):
    result, rows = artifacts(tmp_path)
    with pytest.raises(FormalArtifactError, match="manifest hash mismatch"):
        validate_event_results_artifacts(
            event_results=result, csv_rows=rows, result_fields=FIELDS,
            expected_manifest_sha256="wrong",
        )
    (result.parent / "01_EVENT_JOURNAL.txt").write_text("{}")
    with pytest.raises(FormalArtifactError, match="torn final line"):
        validate_event_results_artifacts(
            event_results=result, csv_rows=rows, result_fields=FIELDS,
            expected_manifest_sha256="abc",
        )


def test_formal_artifacts_reject_called_result_without_intent_response(tmp_path):
    result, rows = artifacts(tmp_path)
    rows[0]["provider_called"] = "True"
    with result.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=(*FIELDS, "provider_called"), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    journal = result.parent / "01_EVENT_JOURNAL.txt"
    journal.write_text(json.dumps({
        "sequence_id": "s", "arm": "cope", "event_index": 1,
        "value": True, "provider_called": True,
    }) + "\n")
    with pytest.raises(FormalArtifactError, match="called result lacks a durable call intent"):
        validate_event_results_artifacts(
            event_results=result, csv_rows=rows,
            result_fields=(*FIELDS, "provider_called"),
            expected_manifest_sha256="abc",
        )
