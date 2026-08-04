from __future__ import annotations

import json
import os
import stat

import pytest

from cope.formal_recovery import (
    AMBIGUOUS_FAILURE,
    FormalRecoveryError,
    FormalRecoveryLedger,
)


def test_formal_ledger_fsyncs_regular_files_and_directory_entries(tmp_path, monkeypatch):
    modes = []

    def capture(descriptor):
        modes.append(os.fstat(descriptor).st_mode)

    monkeypatch.setattr(os, "fsync", capture)
    ledger = FormalRecoveryLedger(tmp_path / "run", {"run": "v2"}, resume=False)
    ledger.record_intent({
        "sequence_id": "s", "arm": "cope", "event_index": 1,
    })
    assert any(stat.S_ISREG(mode) for mode in modes)
    assert any(stat.S_ISDIR(mode) for mode in modes)


KEY = {"sequence_id": "seq-1", "arm": "cope", "event_index": 1}


def test_resume_distinguishes_new_ambiguous_response_and_result(tmp_path):
    output = tmp_path / "run"
    ledger = FormalRecoveryLedger(output, {"run": "v2"}, resume=False)
    key = ("seq-1", "cope", 1)
    assert ledger.phase(key) == "new"
    ledger.record_intent({**KEY, "input_sha256": "input"})
    assert FormalRecoveryLedger(output, {"run": "v2"}, resume=True).phase(key) == "ambiguous_intent"
    ledger.record_response({**KEY, "diagnostics": {"failure": "", "parsed_output": {"x": 1}}})
    assert FormalRecoveryLedger(output, {"run": "v2"}, resume=True).phase(key) == "response"
    ledger.record_result({**KEY, "provider_called": True, "failure_class": ""})
    assert FormalRecoveryLedger(output, {"run": "v2"}, resume=True).phase(key) == "result"


def test_ambiguous_intent_can_be_closed_without_a_second_response(tmp_path):
    ledger = FormalRecoveryLedger(tmp_path / "run", {"run": "v2"}, resume=False)
    ledger.record_intent(KEY)
    ledger.record_result(
        {**KEY, "provider_called": True, "failure_class": AMBIGUOUS_FAILURE}
    )
    reopened = FormalRecoveryLedger(tmp_path / "run", {"run": "v2"}, resume=True)
    assert reopened.phase(("seq-1", "cope", 1)) == "result"


def test_resume_rejects_metadata_drift_and_duplicate_or_orphan_records(tmp_path):
    output = tmp_path / "run"
    ledger = FormalRecoveryLedger(output, {"run": "v2"}, resume=False)
    ledger.record_intent(KEY)
    with pytest.raises(FormalRecoveryError, match="metadata"):
        FormalRecoveryLedger(output, {"run": "different"}, resume=True)
    with pytest.raises(FormalRecoveryError, match="duplicate"):
        ledger.record_intent(KEY)

    orphan = tmp_path / "orphan"
    FormalRecoveryLedger(orphan, {"run": "v2"}, resume=False)
    (orphan / "02_PROVIDER_TRACES.txt").write_text(json.dumps(KEY) + "\n")
    with pytest.raises(FormalRecoveryError, match="lacks a durable call intent"):
        FormalRecoveryLedger(orphan, {"run": "v2"}, resume=True)


def test_torn_line_is_rejected(tmp_path):
    output = tmp_path / "run"
    FormalRecoveryLedger(output, {"run": "v2"}, resume=False)
    (output / "04_CALL_INTENTS.txt").write_text(json.dumps(KEY))
    with pytest.raises(FormalRecoveryError, match="torn final line"):
        FormalRecoveryLedger(output, {"run": "v2"}, resume=True)
