"""Crash-safe, exclusively owned intent -> response -> result journal.

An intent is durable *before* an external call.  An intent without a durable
response is ambiguous, even when the process died before reaching the network.
It is never retried.  Event snapshots and records are immutable JSON objects;
the runtime, not this storage layer, decides what constitutes an event boundary.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time
from typing import Any
from urllib.parse import parse_qsl, urlsplit
import uuid


SCHEMA = "cope-repeated-v2-journal-1"
INVALID_PROTOCOL_DRIFT = "INVALID_PROTOCOL_DRIFT"
AMBIGUOUS_CALL = "BLOCKED_AMBIGUOUS_CALL"
CELL_FIELDS = ("protocol", "master_episode_id", "method", "event_index")
CellKey = tuple[str, str, str, int]
KeyInput = str | Sequence[Any] | Mapping[str, Any]


class JournalError(RuntimeError):
    status = "INVALID_JOURNAL"

    def __init__(self, message: str) -> None:
        super().__init__(f"{self.status}: {message}")


class AmbiguousCallError(JournalError):
    status = AMBIGUOUS_CALL


class DuplicateCellError(JournalError):
    status = "INVALID_DUPLICATE_CELL"


class ProtocolDriftError(JournalError):
    status = INVALID_PROTOCOL_DRIFT


class OwnershipError(JournalError):
    status = "BLOCKED_RUN_OWNERSHIP"


class SnapshotError(JournalError):
    status = "INVALID_SNAPSHOT"


class SensitivePayloadError(JournalError):
    status = "INVALID_SECRET_PAYLOAD"


_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "apikey", "authorization", "proxyauthorization",
    "secret", "secrets", "credentials", "credential", "accesstoken",
    "refreshtoken", "idtoken", "authtoken", "bearertoken", "privatekey",
    "clientsecret", "accesskey", "secretkey", "sessiontoken", "cookie",
    "setcookie", "xapikey", "awssecretaccesskey", "awsaccesskeyid", "token",
})
_CREDENTIAL_VALUE = re.compile(
    r"(?:\bBearer\s+\S+|\bsk-[A-Za-z0-9_-]{16,}|-----BEGIN [^-]*PRIVATE KEY-----)",
    re.IGNORECASE,
)


def _sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return normalized in _SENSITIVE_KEYS or normalized.endswith((
        "apikey", "accesstoken", "refreshtoken", "clientsecret", "privatekey",
        "secretaccesskey", "authorization", "password", "passwd", "credentials",
    ))


def reject_credentials(value: Any) -> None:
    """Reject credential-bearing fields; token counts and model IDs are safe.

    Error messages intentionally contain neither field values nor payload text.
    Secrets belong only in the invoke callback's in-memory client configuration.
    """
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise JournalError("JSON object keys must be strings")
            if _sensitive_key(key):
                raise SensitivePayloadError("credential-bearing field rejected")
            reject_credentials(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            reject_credentials(item)
    elif isinstance(value, str):
        if _CREDENTIAL_VALUE.search(value):
            raise SensitivePayloadError("credential-bearing value rejected")
        if "://" in value:
            try:
                parsed = urlsplit(value)
                if parsed.username is not None or parsed.password is not None:
                    raise SensitivePayloadError("URL credentials rejected")
                if any(_sensitive_key(key) for key, _ in parse_qsl(parsed.query)):
                    raise SensitivePayloadError("URL credential parameters rejected")
            except ValueError:
                pass  # Invalid URLs remain ordinary JSON strings.


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise JournalError("payload must be finite, JSON-serializable data") from exc


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _json_copy(value: Any) -> Any:
    reject_credentials(value)
    return json.loads(canonical_json(value))


def cell_key(value: KeyInput, *, allow_zero: bool = True) -> CellKey:
    if isinstance(value, Mapping):
        try:
            parts = [value[field] for field in CELL_FIELDS]
        except KeyError as exc:
            raise JournalError("cell key lacks required fields") from exc
    elif isinstance(value, str):
        parts = value.split("/")
    elif isinstance(value, Sequence):
        parts = list(value)
    else:
        raise JournalError("invalid cell key type")
    if len(parts) != 4:
        raise JournalError("cell key must have four components")
    if any(not isinstance(p, str) or not p or "/" in p or "\\" in p
           or any(ord(c) < 32 for c in p) for p in parts[:3]):
        raise JournalError("invalid cell key identifier")
    index = parts[3]
    if isinstance(index, str) and re.fullmatch(r"[0-8]", index):
        index = int(index)
    if isinstance(index, bool) or not isinstance(index, int):
        raise JournalError("event_index must be an integer")
    if index not in range(0 if allow_zero else 1, 9):
        raise JournalError("event_index must be within the protocol event range")
    protocols = {"A": "controlled", "B": "end_to_end",
                 "controlled": "controlled", "end_to_end": "end_to_end"}
    if parts[0] not in protocols:
        raise JournalError("protocol must be controlled/A or end_to_end/B")
    return protocols[parts[0]], parts[1], parts[2], index


def key_string(value: KeyInput) -> str:
    return "/".join(map(str, cell_key(value)))


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _mkdir_durable(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise JournalError("journal directory is not a directory")
        return
    _mkdir_durable(path.parent)
    try:
        path.mkdir()
    except FileExistsError:
        if not path.is_dir():
            raise JournalError("journal directory creation collided")
    _fsync_directory(path.parent)


def _decode_json(path: Path) -> dict[str, Any]:
    def no_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise JournalError("record contains duplicate JSON fields")
            result[key] = value
        return result

    try:
        data = path.read_bytes()
        if not data.endswith(b"\n"):
            raise JournalError("record is truncated or lacks its commit newline")
        record = json.loads(data, object_pairs_hook=no_duplicate_fields,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                JournalError("record contains nonfinite data")))
    except (OSError, ValueError, UnicodeError) as exc:
        raise JournalError("record cannot be read as valid JSON") from exc
    if not isinstance(record, dict):
        raise JournalError("record is not a JSON object")
    reject_credentials(record)
    if record.get("schema") != SCHEMA:
        raise JournalError("record schema mismatch")
    recorded_hash = record.pop("sha256", None)
    if recorded_hash != stable_hash(record):
        raise JournalError("record hash verification failed")
    record["sha256"] = recorded_hash
    return record


class DurableJournal:
    """One process owns a run directory until close; threads serialize mutations.

    ``invoke(request)`` must make one provider attempt, with transport retries
    disabled by the provider adapter. Responses are cached and returned on resume.
    ``failure_injector(stage)`` is an optional test hook; raising simulates a crash.
    """

    def __init__(self, output_dir: str | Path, *,
                 frozen_metadata: Mapping[str, Any] | None = None,
                 failure_injector: Callable[[str], None] | None = None) -> None:
        self.output_dir = Path(output_dir).resolve()
        self.root = self.output_dir / "journal"
        self._thread_lock = threading.RLock()
        self._pid = os.getpid()
        self._failure_injector = failure_injector
        self._closed = False
        self._lock_fd: int | None = None
        self._frozen: dict[str, Any] | None = None
        _mkdir_durable(self.output_dir)
        lock_path = self.output_dir / ".journal-owner.lock"
        self._lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(self._lock_fd)
            self._lock_fd = None
            raise OwnershipError("another process owns this run") from exc
        try:
            os.ftruncate(self._lock_fd, 0)
            os.write(self._lock_fd, (str(self._pid) + "\n").encode())
            os.fsync(self._lock_fd)
            _fsync_directory(self.output_dir)
            for relative in ("", "intents", "responses", "results", "episodes", "snapshots"):
                _mkdir_durable(self.root / relative)
            self.metadata_path = self.root / "frozen_metadata.json"
            self.stop_path = self.root / "protocol_drift_stop.json"
            if self.metadata_path.exists():
                try:
                    record = self._read(self.metadata_path, "metadata")
                except JournalError:
                    self._stop_for_drift("frozen metadata is corrupted")
                self._frozen = record["payload"]
            if frozen_metadata is not None:
                self.freeze_metadata(frozen_metadata)
            self._validate_records()
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> DurableJournal:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        with self._thread_lock:
            if self._lock_fd is not None:
                # An inherited handle must never unlock the parent's flock.
                if os.getpid() == self._pid:
                    fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
                self._lock_fd = None
            self._closed = True

    @contextmanager
    def _owned(self):
        with self._thread_lock:
            if self._closed or self._lock_fd is None or os.getpid() != self._pid:
                raise OwnershipError("journal is closed or belongs to another process")
            yield

    def _inject(self, stage: str) -> None:
        if self._failure_injector is not None:
            self._failure_injector(stage)

    def _write(self, path: Path, kind: str, payload: Any,
               key: CellKey | None = None, *, label: str | None = None) -> dict[str, Any]:
        record = {"schema": SCHEMA, "kind": kind, "payload": _json_copy(payload)}
        if key is not None:
            record["key"] = dict(zip(CELL_FIELDS, key))
        if label is not None:
            record["label"] = label
        reject_credentials(record)
        record["sha256"] = stable_hash(record)
        _mkdir_durable(path.parent)
        temporary = path.parent / (".pending-" + uuid.uuid4().hex)
        # Hard-link publication gives atomic, exclusive creation without replacing
        # an existing experiment record, including after an interrupted commit.
        with temporary.open("x", encoding="utf-8") as handle:
            os.chmod(temporary, 0o600)
            handle.write(canonical_json(record) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._inject("before_atomic_commit:" + kind)
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise DuplicateCellError("immutable record already exists") from exc
        _fsync_directory(path.parent)
        self._inject("after_atomic_commit:" + kind)
        # Pending files are not records; leave crashed writes as forensic evidence.
        temporary.unlink()
        _fsync_directory(path.parent)
        return record

    def _read(self, path: Path, kind: str, key: CellKey | None = None,
              *, label: str | None = None) -> dict[str, Any]:
        record = _decode_json(path)
        if record.get("kind") != kind:
            raise JournalError("record kind mismatch")
        if key is not None and cell_key(record.get("key", {})) != key:
            raise JournalError("record cell key mismatch")
        if label is not None and record.get("label") != label:
            raise SnapshotError("snapshot boundary label mismatch")
        return record

    def _path(self, kind: str, key: CellKey) -> Path:
        return self.root / kind / (stable_hash(list(key)) + ".json")

    def freeze_metadata(self, metadata: Mapping[str, Any]) -> str:
        """Freeze once; all later comparisons must match, even before a call."""
        with self._owned():
            frozen = _json_copy(dict(metadata))
            if self._frozen is not None:
                self.verify_metadata(frozen)
            elif self.records("intents"):
                raise ProtocolDriftError("call intents exist without frozen metadata")
            else:
                self._write(self.metadata_path, "metadata", frozen)
                self._frozen = frozen
            return stable_hash(frozen)

    def verify_metadata(self, metadata: Mapping[str, Any]) -> None:
        with self._owned():
            supplied = _json_copy(dict(metadata))
            try:
                recorded = self._read(self.metadata_path, "metadata")["payload"]
            except JournalError:
                self._stop_for_drift("frozen metadata is missing or corrupted")
            if self.stop_path.exists():
                raise ProtocolDriftError("run is durably stopped for protocol drift")
            if self._frozen is None or recorded != self._frozen or supplied != recorded:
                self._stop_for_drift("current metadata differs from frozen metadata")

    def _stop_for_drift(self, reason: str) -> None:
        if not self.stop_path.exists():
            self._write(self.stop_path, "stop", {"status": INVALID_PROTOCOL_DRIFT,
                                               "reason": reason})
        raise ProtocolDriftError(reason)

    def _check_frozen(self) -> None:
        if self._frozen is None:
            raise JournalError("freeze run metadata before making a call")
        self.verify_metadata(self._frozen)

    def records(self, kind: str) -> dict[CellKey, dict[str, Any]]:
        """Read and verify immutable phase records; returned payloads are copies."""
        with self._owned():
            if kind not in {"intents", "responses", "results", "episodes"}:
                raise JournalError("unknown record collection")
            found: dict[CellKey, dict[str, Any]] = {}
            for path in sorted((self.root / kind).glob("*.json")):
                record = self._read(path, kind[:-1])
                key = cell_key(record.get("key", {}))
                if key in found:
                    raise DuplicateCellError("duplicate cell in record collection")
                if path != self._path(kind, key):
                    raise JournalError("record filename does not match its cell key")
                found[key] = record["payload"]
            return found

    def read_records(self, kind: str) -> dict[CellKey, dict[str, Any]]:
        return self.records(kind)

    def event_result(self, key: KeyInput) -> dict[str, Any] | None:
        with self._owned():
            parsed = cell_key(key)
            path = self._path("results", parsed)
            return self._read(path, "result", parsed)["payload"] if path.exists() else None

    def record_episode(self, key: KeyInput, payload: Mapping[str, Any]) -> None:
        with self._owned():
            parsed = cell_key(key)
            if parsed[3] != 0:
                raise JournalError("episode record key must use event_index zero")
            self._check_frozen()
            self._write(self._path("episodes", parsed), "episode", dict(payload), parsed)
            self._inject("after_episode")

    def get_episode(self, key: KeyInput) -> dict[str, Any] | None:
        with self._owned():
            parsed = cell_key(key)
            if parsed[3] != 0:
                raise JournalError("episode record key must use event_index zero")
            path = self._path("episodes", parsed)
            return self._read(path, "episode", parsed)["payload"] if path.exists() else None

    def _validate_records(self) -> None:
        intents = self.records("intents")
        responses = self.records("responses")
        results = self.records("results")
        for key in self.records("episodes"):
            if key[3] != 0:
                raise JournalError("episode record has a nonzero event_index")
        if intents and self._frozen is None:
            raise ProtocolDriftError("durable intents lack frozen metadata")
        for key, payload in intents.items():
            cell_key(key, allow_zero=False)
            if payload.get("request_sha256") != stable_hash(payload.get("request")):
                raise JournalError("call intent request hash mismatch")
        for key, payload in responses.items():
            if key not in intents:
                raise JournalError("response lacks durable intent")
            if payload.get("request_sha256") != intents[key]["request_sha256"]:
                raise JournalError("response does not match durable request")
            self._invocation_seconds(payload)
        for key, payload in results.items():
            self._validate_result(key, payload, intents, responses)

    @staticmethod
    def _validate_result(key: CellKey, result: Any, intents: Mapping,
                         responses: Mapping) -> None:
        if not isinstance(result, Mapping):
            raise JournalError("event result must be a JSON object")
        called = result.get("provider_called", key in intents)
        if key in intents and called is False:
            raise JournalError("result denies an existing provider call intent")
        if called and key not in intents:
            raise JournalError("called result lacks durable intent")
        ambiguous = result.get("status") == AMBIGUOUS_CALL
        if key in intents and key not in responses and not ambiguous:
            raise AmbiguousCallError("result lacks durable provider response")
        if ambiguous and (key not in intents or key in responses):
            raise JournalError("ambiguous result has an incompatible call state")

    def phase(self, key: KeyInput) -> str:
        with self._owned():
            parsed = cell_key(key)
            for kind, phase in (("results", "result"), ("responses", "response"),
                                ("intents", "ambiguous_intent")):
                path = self._path(kind, parsed)
                if path.exists():
                    self._read(path, kind[:-1], parsed)
                    return phase
            return "new"

    def call_once(self, key: KeyInput, request: Any, invoke: Callable[[Any], Any]) -> Any:
        with self._owned():
            parsed = cell_key(key, allow_zero=False)
            durable_request = _json_copy(request)
            self._check_frozen()
            request_hash = stable_hash(durable_request)
            intent_path = self._path("intents", parsed)
            response_path = self._path("responses", parsed)
            if intent_path.exists():
                intent = self._read(intent_path, "intent", parsed)["payload"]
                if intent["request_sha256"] != request_hash:
                    self._stop_for_drift("request changed for an existing call cell")
                if response_path.exists():
                    response = self._read(response_path, "response", parsed)["payload"]
                    if response["request_sha256"] != request_hash:
                        raise JournalError("response request hash mismatch")
                    return response["response"]
                raise AmbiguousCallError("intent has no durable response; retry forbidden")
            if response_path.exists():
                raise JournalError("orphan response exists for this cell")
            if self._path("results", parsed).exists():
                raise DuplicateCellError("completed event cell cannot acquire a new call")
            self._write(intent_path, "intent", {"request": durable_request,
                        "request_sha256": request_hash}, parsed)
            self._inject("after_intent")
            started_at = time.monotonic()
            response = invoke(_json_copy(durable_request))
            invocation_seconds = time.monotonic() - started_at
            self._inject("after_invoke")
            durable_response = _json_copy(response)
            self._write(response_path, "response", {"response": durable_response,
                        "request_sha256": request_hash,
                        "invocation_seconds": invocation_seconds}, parsed)
            self._inject("after_response")
            return durable_response

    @staticmethod
    def _invocation_seconds(response: Mapping[str, Any]) -> float | None:
        value = response.get("invocation_seconds")
        if value is None:
            return None  # Older durable responses have unknown timing, never zero.
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise JournalError("response invocation timing must be finite and nonnegative")
        return float(value)

    def invocation_seconds(self, key: KeyInput) -> float | None:
        """Read original call duration on both first execution and response replay.

        Timing belongs to the durable envelope; the provider response remains exact.
        It measures the invoke callback, including its immediate admission checks.
        """
        with self._owned():
            parsed = cell_key(key, allow_zero=False)
            self._check_frozen()
            path = self._path("responses", parsed)
            if not path.exists():
                return None
            response = self._read(path, "response", parsed)["payload"]
            return self._invocation_seconds(response)

    def record_result(self, key: KeyInput, result: Mapping[str, Any]) -> None:
        with self._owned():
            parsed = cell_key(key)
            self._check_frozen()
            durable_result = _json_copy(dict(result))
            path = self._path("results", parsed)
            if path.exists():
                raise DuplicateCellError("completed event cell cannot be duplicated")
            phases = []
            for kind in ("intents", "responses"):
                phase_path = self._path(kind, parsed)
                phases.append({parsed: self._read(phase_path, kind[:-1], parsed)["payload"]}
                              if phase_path.exists() else {})
            self._validate_result(parsed, durable_result, *phases)
            self._write(path, "result", durable_result, parsed)
            self._inject("after_result")

    @staticmethod
    def _label(label: str) -> str:
        if not isinstance(label, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", label):
            raise SnapshotError("invalid snapshot boundary label")
        return label

    def save_snapshot(self, key: KeyInput, payload: Any, *, label: str = "post") -> str:
        with self._owned():
            parsed = cell_key(key)
            self._check_frozen()
            boundary = self._label(label)
            path = self.root / "snapshots" / boundary / (stable_hash(list(parsed)) + ".json")
            record = self._write(path, "snapshot", payload, parsed, label=boundary)
            self._inject("after_snapshot")
            return record["sha256"]

    def load_snapshot(self, key: KeyInput, *, label: str = "post") -> Any:
        with self._owned():
            parsed = cell_key(key)
            self._check_frozen()
            boundary = self._label(label)
            path = self.root / "snapshots" / boundary / (stable_hash(list(parsed)) + ".json")
            try:
                return self._read(path, "snapshot", parsed, label=boundary)["payload"]
            except JournalError as exc:
                raise SnapshotError("event-boundary snapshot failed verification") from exc

    def snapshot_exists(self, key: KeyInput, *, label: str = "post") -> bool:
        """An existing corrupted snapshot raises rather than appearing absent."""
        with self._owned():
            parsed = cell_key(key)
            boundary = self._label(label)
            path = self.root / "snapshots" / boundary / (stable_hash(list(parsed)) + ".json")
            if not path.exists():
                return False
            self.load_snapshot(parsed, label=boundary)
            return True

    def inspect_integrity(self, expected_cells, **kwargs):
        from .integrity import inspect_integrity
        return inspect_integrity(self, expected_cells, **kwargs)
