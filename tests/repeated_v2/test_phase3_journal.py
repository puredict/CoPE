from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
import os
from pathlib import Path
import stat

import pytest

from cope_benchmark.repeated_v2.integrity import RunIntegrityError, inspect_integrity
from cope_benchmark.repeated_v2.journal import (
    AMBIGUOUS_CALL, AmbiguousCallError, DuplicateCellError, DurableJournal,
    JournalError, OwnershipError, ProtocolDriftError, SensitivePayloadError,
    SnapshotError, canonical_json, cell_key, stable_hash,
)


KEY = ("controlled", "master-1", "cope", 1)
KEY2 = ("end_to_end", "master-1", "cope", 8)
META = {"git_sha": "abc", "config_hash": "def", "provider_model_id": "test-only"}


def _journal(path, **kwargs):
    return DurableJournal(path, frozen_metadata=META, **kwargs)


def _rejected_owner(path, queue):
    try:
        with _journal(path):
            queue.put("acquired")
    except JournalError as exc:
        queue.put(exc.status)


def _crash_after_invoke(path):
    def invoke(request):
        marker = Path(path) / "provider-call-marker.txt"
        with marker.open("a") as handle:
            handle.write("called\n")
            handle.flush()
            os.fsync(handle.fileno())
        os._exit(73)

    with _journal(path) as journal:
        journal.call_once(KEY, {"instruction": "move"}, invoke)


def test_key_is_protocol_master_method_event_and_accepts_all_events():
    assert cell_key("A/master-1/cope/8") == ("controlled", "master-1", "cope", 8)
    assert cell_key("B/master-1/cope/8") == ("end_to_end", "master-1", "cope", 8)
    assert cell_key(dict(zip(("protocol", "master_episode_id", "method", "event_index"), KEY))) == KEY
    for key in (("C", "m", "x", 1), ("A", "m", "x", True),
                ("A", "m", "x", 9), ("A", "m/a", "x", 1),
                ("A", "m", "x", 1.5), "A/m/x/01"):
        with pytest.raises(JournalError):
            cell_key(key)


def test_freeze_required_before_call_and_snapshot(tmp_path):
    with DurableJournal(tmp_path) as journal:
        with pytest.raises(JournalError, match="freeze"):
            journal.call_once(KEY, {}, lambda _: pytest.fail("must not call"))
        with pytest.raises(JournalError, match="freeze"):
            journal.save_snapshot(KEY, {})
        journal.freeze_metadata(META)
        assert journal.call_once(KEY, {}, lambda _: {"ok": True}) == {"ok": True}


def test_reopen_replays_response_without_a_provider_retry_or_duplicate_result(tmp_path):
    calls = []
    with _journal(tmp_path) as journal:
        assert journal.phase(KEY) == "new"
        response = journal.call_once(KEY, {"x": [1]}, lambda req: calls.append(req) or {"y": [2]})
        response["y"].append(3)
        assert journal.phase(KEY) == "response"
    with _journal(tmp_path) as resumed:
        assert resumed.call_once(KEY, {"x": [1]}, lambda _: pytest.fail("retry")) == {"y": [2]}
        resumed.record_result(KEY, {"status": "OK", "provider_called": True})
        with pytest.raises(DuplicateCellError):
            resumed.record_result(KEY, {"status": "OK"})
    with _journal(tmp_path) as resumed:
        assert resumed.phase(KEY) == "result"
        assert resumed.call_once(KEY, {"x": [1]}, lambda _: pytest.fail("retry")) == {"y": [2]}
    assert calls == [{"x": [1]}]


@pytest.mark.parametrize("stage,called,replayable", [
    ("before_atomic_commit:intent", False, False),
    ("after_atomic_commit:intent", False, False),
    ("after_intent", False, False),
    ("after_invoke", True, False),
    ("before_atomic_commit:response", True, False),
    ("after_atomic_commit:response", True, True),
    ("after_response", True, True),
])
def test_failure_injection_call_publication_boundaries(tmp_path, stage, called, replayable):
    calls = []

    def crash(where):
        if where == stage:
            raise RuntimeError("simulated crash")

    with _journal(tmp_path, failure_injector=crash) as journal:
        with pytest.raises(RuntimeError, match="simulated crash"):
            journal.call_once(KEY, {"x": 1}, lambda _: calls.append(1) or {"ok": True})
    assert bool(calls) == called
    with _journal(tmp_path) as resumed:
        if replayable:
            assert resumed.call_once(KEY, {"x": 1}, lambda _: pytest.fail("retry")) == {"ok": True}
        elif stage == "before_atomic_commit:intent":
            assert resumed.phase(KEY) == "new"
            resumed.call_once(KEY, {"x": 1}, lambda _: calls.append(1) or {})
        else:
            with pytest.raises(AmbiguousCallError):
                resumed.call_once(KEY, {"x": 1}, lambda _: pytest.fail("retry"))
    assert len(calls) <= 1


def test_real_process_death_releases_lock_and_never_repeats_ambiguous_call(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    worker = ctx.Process(target=_crash_after_invoke, args=(str(tmp_path),))
    worker.start()
    worker.join(15)
    assert worker.exitcode == 73
    with _journal(tmp_path) as resumed:
        with pytest.raises(AmbiguousCallError):
            resumed.call_once(KEY, {"instruction": "move"}, lambda _: pytest.fail("retry"))
        resumed.record_result(KEY, {"status": AMBIGUOUS_CALL, "provider_called": True})
    assert (tmp_path / "provider-call-marker.txt").read_text() == "called\n"


def test_provider_exception_becomes_ambiguous_and_cannot_be_hidden(tmp_path):
    with _journal(tmp_path) as journal:
        def failed(_):
            raise TimeoutError("provider disconnected")
        with pytest.raises(TimeoutError):
            journal.call_once(KEY, {}, failed)
        with pytest.raises(AmbiguousCallError):
            journal.call_once(KEY, {}, lambda _: pytest.fail("retry"))
        with pytest.raises(JournalError):
            journal.record_result(KEY, {"status": "OK", "provider_called": False})
        with pytest.raises(AmbiguousCallError):
            journal.record_result(KEY, {"status": "OK"})
        journal.record_result(KEY, {"status": AMBIGUOUS_CALL})
        assert not inspect_integrity(journal, [KEY], require_snapshots=False).valid


def test_thread_contention_calls_provider_once(tmp_path):
    calls = []
    with _journal(tmp_path) as journal:
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda _: journal.call_once(
                KEY, {}, lambda _: calls.append(1) or {"result": "once"}), range(20)))
    assert calls == [1]
    assert all(response == {"result": "once"} for response in responses)


def test_process_owner_lock_and_explicit_close(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    with _journal(tmp_path):
        with pytest.raises(OwnershipError):
            _journal(tmp_path)
        queue = ctx.Queue()
        child = ctx.Process(target=_rejected_owner, args=(str(tmp_path), queue))
        child.start()
        child.join(15)
        assert child.exitcode == 0
        assert queue.get(timeout=2) == "BLOCKED_RUN_OWNERSHIP"
    journal = _journal(tmp_path)
    journal.close()
    with pytest.raises(OwnershipError):
        journal.phase(KEY)


def test_metadata_drift_durably_stops_future_calls(tmp_path):
    with _journal(tmp_path) as journal:
        journal.call_once(KEY, {}, lambda _: {})
        with pytest.raises(ProtocolDriftError):
            journal.verify_metadata({**META, "git_sha": "changed"})
        with pytest.raises(ProtocolDriftError):
            journal.call_once(KEY2, {}, lambda _: pytest.fail("after drift"))
    with pytest.raises(ProtocolDriftError):
        _journal(tmp_path)


def test_changed_request_is_protocol_drift(tmp_path):
    with _journal(tmp_path) as journal:
        journal.call_once(KEY, {"x": 1}, lambda _: {})
        with pytest.raises(ProtocolDriftError):
            journal.call_once(KEY, {"x": 2}, lambda _: pytest.fail("retry"))


def test_on_disk_frozen_metadata_tamper_stops_before_call(tmp_path):
    with _journal(tmp_path) as journal:
        journal.metadata_path.write_text("{}\n")
        with pytest.raises(ProtocolDriftError):
            journal.call_once(KEY, {}, lambda _: pytest.fail("tampered"))


@pytest.mark.parametrize("payload", [
    {"nested": [{"api_key": "secret"}]}, {"Authorization": "private"},
    {"refresh_token": "secret"}, {"clientSecret": "secret"},
    {"OPENAI_API_KEY": "secret"}, {"provider_credentials": {"value": "secret"}},
    {"url": "https://user:password@example.test"},
    {"url": "https://example.test?api_key=secret"},
    {"text": "Bearer private"}, {"text": "sk-123456789012345678901234"},
])
def test_credentials_rejected_before_any_payload_hits_disk(tmp_path, payload):
    with _journal(tmp_path) as journal:
        before = set(tmp_path.rglob("*"))
        with pytest.raises(SensitivePayloadError):
            journal.call_once(KEY, payload, lambda _: pytest.fail("secret"))
        assert set(tmp_path.rglob("*")) == before
        assert journal.phase(KEY) == "new"


def test_response_secrets_are_not_persisted_and_intent_becomes_ambiguous(tmp_path):
    with _journal(tmp_path) as journal:
        with pytest.raises(SensitivePayloadError):
            journal.call_once(KEY, {"input_tokens": 5}, lambda _: {"api_key": "hidden-secret"})
        with pytest.raises(AmbiguousCallError):
            journal.call_once(KEY, {"input_tokens": 5}, lambda _: pytest.fail("retry"))
    assert not any("hidden-secret" in p.read_text() for p in tmp_path.rglob("*") if p.is_file())


def test_atomic_snapshots_are_verified_immutable_and_have_boundary_labels(tmp_path):
    with _journal(tmp_path) as journal:
        original = {"simulator": {"qpos": [1, 2]}, "method_state": ["persistent"]}
        digest = journal.save_snapshot(KEY, original, label="pre")
        original["simulator"]["qpos"].append(3)
        assert len(digest) == 64
        assert journal.load_snapshot(KEY, label="pre")["simulator"]["qpos"] == [1, 2]
        with pytest.raises(DuplicateCellError):
            journal.save_snapshot(KEY, {}, label="pre")
        journal.save_snapshot(KEY, {"advanced": True}, label="post")
        assert journal.load_snapshot(KEY) == {"advanced": True}
        baseline = (*KEY[:3], 0)
        journal.save_snapshot(baseline, {"initial": True})
        assert journal.load_snapshot(baseline) == {"initial": True}
        with pytest.raises(SnapshotError):
            journal.load_snapshot(KEY2)
        snapshot = next((journal.root / "snapshots" / "pre").glob("*.json"))
        snapshot.write_text(snapshot.read_text().replace("persistent", "tampered"))
        with pytest.raises(SnapshotError):
            journal.load_snapshot(KEY, label="pre")


@pytest.mark.parametrize("stage,available", [
    ("before_atomic_commit:snapshot", False),
    ("after_atomic_commit:snapshot", True), ("after_snapshot", True),
])
def test_snapshot_crash_is_wholly_present_or_absent(tmp_path, stage, available):
    def crash(where):
        if where == stage:
            raise RuntimeError("crash")
    with _journal(tmp_path, failure_injector=crash) as journal:
        with pytest.raises(RuntimeError, match="crash"):
            journal.save_snapshot(KEY, {"event": 1})
    with _journal(tmp_path) as resumed:
        if available:
            assert resumed.load_snapshot(KEY) == {"event": 1}
        else:
            with pytest.raises(SnapshotError):
                resumed.load_snapshot(KEY)


def test_result_crash_does_not_duplicate_results(tmp_path):
    def crash(where):
        if where == "after_result":
            raise RuntimeError("crash")
    with _journal(tmp_path, failure_injector=crash) as journal:
        journal.call_once(KEY, {}, lambda _: {})
        with pytest.raises(RuntimeError, match="crash"):
            journal.record_result(KEY, {"success": True})
    with _journal(tmp_path) as resumed:
        assert len(resumed.records("results")) == 1
        with pytest.raises(DuplicateCellError):
            resumed.record_result(KEY, {"success": True})


def test_integrity_requires_exact_cells_and_verified_snapshots(tmp_path):
    with _journal(tmp_path) as journal:
        journal.call_once(KEY, {}, lambda _: {})
        journal.record_result(KEY, {"success": True})
        incomplete = inspect_integrity(journal, [KEY, KEY2])
        assert incomplete.status == "INVALID_RUN"
        assert incomplete.missing == ("end_to_end/master-1/cope/8",)
        assert incomplete.missing_snapshots == ("controlled/master-1/cope/1",)
        with pytest.raises(RunIntegrityError):
            incomplete.require_valid()
        journal.save_snapshot(KEY, {"boundary": 1})
        report = journal.inspect_integrity([KEY])
        assert report.valid and report.status == "VALID"
        assert report.as_dict()["result_count"] == 1
        assert not journal.inspect_integrity([KEY, KEY]).valid
        unexpected = journal.inspect_integrity([KEY2])
        assert unexpected.unexpected == ("controlled/master-1/cope/1",)


def test_no_provider_result_is_valid_but_cannot_gain_a_later_call(tmp_path):
    with _journal(tmp_path) as journal:
        journal.record_result(KEY, {"provider_called": False, "success": False})
        journal.save_snapshot(KEY, {"method_state": {}})
        assert journal.inspect_integrity([KEY]).valid
        with pytest.raises(DuplicateCellError):
            journal.call_once(KEY, {}, lambda _: pytest.fail("late call"))


def test_episode_and_event_getters_are_separate_and_snapshot_exists_is_verified(tmp_path):
    episode = (*KEY[:3], 0)
    with _journal(tmp_path) as journal:
        assert journal.get_episode(episode) is None
        assert journal.event_result(KEY) is None
        assert not journal.snapshot_exists(KEY, label="completed")
        journal.record_episode(episode, {"dynamic_success": True})
        assert journal.get_episode(episode) == {"dynamic_success": True}
        assert journal.read_records("episodes") == {episode: {"dynamic_success": True}}
        assert journal.read_records("results") == {}
        with pytest.raises(DuplicateCellError):
            journal.record_episode(episode, {"dynamic_success": False})
        with pytest.raises(JournalError):
            journal.record_episode(KEY, {})
        pending = {"pending_result": {"provider_called": False}}
        journal.save_snapshot(KEY, pending, label="completed")
        assert journal.snapshot_exists(KEY, label="completed")
        journal.record_result(KEY, journal.load_snapshot(KEY, label="completed")["pending_result"])
        assert journal.event_result(KEY) == {"provider_called": False}
        assert journal.inspect_integrity([KEY], snapshot_label="completed").valid
        path = next((journal.root / "snapshots" / "completed").glob("*.json"))
        path.write_text("{}\n")
        with pytest.raises(SnapshotError):
            journal.snapshot_exists(KEY, label="completed")


def test_reopen_corrupt_metadata_is_durable_protocol_drift(tmp_path):
    with _journal(tmp_path) as journal:
        metadata = journal.metadata_path
    metadata.write_text("{}\n")
    with pytest.raises(ProtocolDriftError):
        _journal(tmp_path)
    assert (tmp_path / "journal" / "protocol_drift_stop.json").is_file()


def test_corrupt_or_orphan_records_prevent_resume(tmp_path):
    with _journal(tmp_path) as journal:
        journal.call_once(KEY, {}, lambda _: {})
        response = next((journal.root / "responses").glob("*.json"))
        response.write_text(response.read_text()[:-1])
    with pytest.raises(JournalError, match="truncated"):
        _journal(tmp_path)


def test_duplicate_physical_records_invalidate_analysis(tmp_path):
    with _journal(tmp_path) as journal:
        journal.record_result(KEY, {"provider_called": False})
        path = next((journal.root / "results").glob("*.json"))
        (path.parent / "duplicate.json").write_bytes(path.read_bytes())
        assert not journal.inspect_integrity([KEY], require_snapshots=False).valid


def test_file_and_directory_entries_are_fsynced(tmp_path, monkeypatch):
    modes = []
    original_fsync = os.fsync
    def capture(fd):
        modes.append(os.fstat(fd).st_mode)
        original_fsync(fd)
    monkeypatch.setattr(os, "fsync", capture)
    with _journal(tmp_path / "run") as journal:
        journal.call_once(KEY, {}, lambda _: {})
        journal.record_result(KEY, {"success": True})
        journal.save_snapshot(KEY, {"event": 1})
    assert any(stat.S_ISREG(mode) for mode in modes)
    assert any(stat.S_ISDIR(mode) for mode in modes)


@pytest.mark.parametrize("tamper", [None, "missing_source", "future_source", "wrong_hash",
                                   "nonfailure_source", "wrong_failure", "called",
                                   "claimed_success", "pending_result_mismatch"])
def test_unreached_result_requires_verified_failed_source_boundary(tmp_path, tamper):
    source_key = KEY
    unreachable_key = (*KEY[:3], 2)
    source_result = {"status": "METHOD_TIMEOUT", "success": False, "provider_called": False}
    if tamper == "nonfailure_source":
        source_result["status"] = "COMPLETED"
    snapshot = {"index": 1, "delivered": 1, "pending_result": source_result.copy()}
    if tamper == "pending_result_mismatch":
        snapshot["pending_result"]["status"] = "COMPLETED"
    unreachable = {"status": "EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE", "success": False,
                   "high_level_calls": 0, "prior_failure": "METHOD_TIMEOUT",
                   "source_boundary_event_index": 1,
                   "source_boundary_sha256": stable_hash(snapshot)}
    if tamper == "missing_source":
        unreachable.pop("source_boundary_event_index")
    elif tamper == "future_source":
        unreachable["source_boundary_event_index"] = 2
    elif tamper == "wrong_hash":
        unreachable["source_boundary_sha256"] = "0" * 64
    elif tamper == "wrong_failure":
        unreachable["prior_failure"] = "METHOD_REJECTED_TERMINATED"
    elif tamper == "called":
        unreachable["high_level_calls"] = 1
    elif tamper == "claimed_success":
        unreachable["success"] = True
    with _journal(tmp_path) as journal:
        journal.record_result(source_key, source_result)
        journal.save_snapshot(source_key, snapshot, label="completed")
        journal.record_result(unreachable_key, unreachable)
        report = journal.inspect_integrity([source_key, unreachable_key], snapshot_label="completed")
        assert report.valid is (tamper is None)
        if tamper:
            assert report.errors


def test_integrity_scope_isolates_trajectories_in_shared_journal(tmp_path):
    with _journal(tmp_path) as journal:
        journal.record_result(KEY, {"provider_called": False})
        journal.save_snapshot(KEY, {"boundary": 1})
        journal.record_result(KEY2, {"provider_called": False})
        assert not journal.inspect_integrity([KEY]).valid
        report = journal.inspect_integrity([KEY], scope=KEY[:3])
        assert report.valid and report.result_count == 1 and report.expected_count == 1
        assert journal.inspect_integrity([KEY], scope=("A", *KEY[1:3])).valid
        with pytest.raises(JournalError, match="scope"):
            journal.inspect_integrity([KEY, KEY2], scope=KEY[:3])
        assert not journal.inspect_integrity([KEY2], scope=KEY2[:3]).valid


def test_response_crash_preserves_original_invocation_timing_on_replay(tmp_path, monkeypatch):
    from cope_benchmark.repeated_v2 import journal as journal_module
    clock = {"now": 10.0}
    monkeypatch.setattr(journal_module.time, "monotonic", lambda: clock["now"])
    response = {"text": "exact provider payload", "output_tokens": 3}

    def invoke(_):
        clock["now"] += 2.75
        return response

    def crash(stage):
        if stage == "after_response":
            raise RuntimeError("response persisted before process death")

    with _journal(tmp_path, failure_injector=crash) as journal:
        with pytest.raises(RuntimeError, match="response persisted"):
            journal.call_once(KEY, {"instruction": "move"}, invoke)
    clock["now"] = 9000.0
    with _journal(tmp_path) as resumed:
        assert resumed.call_once(KEY, {"instruction": "move"}, lambda _: pytest.fail("repeat")) == response
        assert resumed.invocation_seconds(KEY) == 2.75
        envelope = resumed.read_records("responses")[KEY]
        assert envelope["response"] == response
        assert envelope["invocation_seconds"] == 2.75


def test_legacy_response_without_timing_is_unknown_not_zero(tmp_path):
    with _journal(tmp_path) as journal:
        request = {"instruction": "move"}
        common = {"request_sha256": stable_hash(request)}
        journal._write(journal._path("intents", KEY), "intent", {**common, "request": request}, KEY)
        journal._write(journal._path("responses", KEY), "response", {**common, "response": {"ok": True}}, KEY)
    with _journal(tmp_path) as resumed:
        assert resumed.call_once(KEY, request, lambda _: pytest.fail("repeat")) == {"ok": True}
        assert resumed.invocation_seconds(KEY) is None
