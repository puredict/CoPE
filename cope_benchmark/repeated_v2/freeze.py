"""Fail-closed formal freeze and whole-master deterministic sharding.

No audit result is accepted merely because it says ``passed: true``. A freeze
binds raw calibration/development/pilot records, a JUnit report, its committed
test sources, and producer provenance. Digests establish integrity, not the
truth of a remote provider's claims or cryptographic authenticity of an audit.
Production audit provenance must therefore be reviewed before it is supplied.

``build_freeze_bundle`` performs no provider calls and writes no files.
``validate_frozen_bundle(bundle, current_identity=callable)`` is the runner hook:
invoke immediately before every formal external call and at every resume.
``formal_call_guard`` additionally checks on leaving a call; callers must keep
the journalled response even when this post-call check detects drift.

Artifacts are role -> path or list of paths. Evidence lives inside the repository;
installed implementations and checkpoints may be existing external paths. Symlink
mapping and resolved bytes are both frozen, including Hugging Face snapshots. Runtime
outputs belong in research/ or docs/. Identity metadata is exact, public,
non-secret provider/model/revision/checkpoint/component metadata. Credentials
must never be included. JSON-encoded TXT is supported throughout.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import csv
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Iterable, Mapping, Sequence
import xml.etree.ElementTree as ET


SCHEMA_VERSION = "repeated_v2_formal_freeze_v1"
GATE_SCHEMA_VERSION = "repeated_v2_gate_evidence_v1"
NON_ORACLE_METHODS = (
    "cope_typed_edit", "generic_persistent_edit", "full_state_regeneration",
    "full_history_replan", "rag_replan", "summary_memory_replan",
    "skill_local_replan", "classical_execution_monitor",
)
COMPARATORS = NON_ORACLE_METHODS[2:]
ORACLE_METHOD = "oracle_persistent_update"
REQUIRED_CHECKS = (
    "catalog_and_calibration", "schedule_legality_and_exact_counts",
    "occurrence_reissue", "semantic_information_parity", "recursive_leakage",
    "schemas_and_parsers", "compiler_purity", "event_injection_isolation",
    "fresh_observation", "dynamic_evaluator", "wrong_occurrence_and_stale_restore",
    "atomic_rejection", "journal_resume_at_most_once", "formal_adapter_gates",
    "statistics_and_claim_decision",
)
REQUIRED_ARTIFACTS = (
    "config", "catalog", "manifest", "prompts", "schemas", "gate_report",
    "junit_report", "gate_tests", "calibration_records", "development_records",
    "pilot_controlled_records", "pilot_end_to_end_records", "reasoner_implementation",
    "detector_implementation", "verifier_implementation", "compiler_implementation",
    "backend_implementation", "retriever_implementation", "vla_implementation",
    "vla_checkpoint", "analysis_implementation", "calibration_traces",
    "development_traces", "pilot_controlled_journals", "pilot_end_to_end_journals",
)
IDENTITY_COMPONENTS = ("reasoner", "vla", "detector", "verifier", "compiler", "backend", "retriever")
BAD_PROVIDER = re.compile(r"(?:^|[^a-z])(fake|mock|scripted|oracle|fixture|stub|dummy)(?:$|[^a-z])", re.I)
HEX256 = re.compile(r"[0-9a-f]{64}\Z")
_FILE_HASH_CACHE: dict[tuple[Any, ...], str] = {}


class FreezeBlocked(ValueError):
    """A prerequisite is absent or malformed; no formal calls are authorized."""

    status = "BLOCKED_FORMAL_FREEZE"

    def __init__(self, reasons: str | Sequence[str]):
        self.reasons = [reasons] if isinstance(reasons, str) else list(reasons)
        super().__init__("; ".join(self.reasons))


class ProtocolDrift(FreezeBlocked):
    status = "INVALID_PROTOCOL_DRIFT"


def _canonical(value: Any) -> str:
    # This module can run before the upstream canonical/schema packages arrive.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise FreezeBlocked(message)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)
    _require(result.returncode == 0, f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def _git_identity(root: Path) -> dict[str, str]:
    # Tracked modifications always block. New reports in the output roots are
    # allowed, but untracked implementation/config/checkpoint files are not.
    _require(not _git(root, "diff", "--name-only", "HEAD"), "BLOCKED_DIRTY_TRACKED_FILES")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    _require(all(Path(p).parts[0] in {"research", "docs"} for p in untracked), "BLOCKED_UNCOMMITTED_CODE")
    return {"sha": _git(root, "rev-parse", "HEAD"), "tree_sha": _git(root, "rev-parse", "HEAD^{tree}")}


def _sha_file(path: Path) -> str:
    _require(path.is_file(), f"missing artifact: {path}")
    before = path.stat()
    def signature(stat) -> tuple[int, ...]:
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns
    key = (str(path.resolve(strict=True)), *signature(before))
    value = _FILE_HASH_CACHE.get(key)
    if value is None:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        value = digest.hexdigest()
    after = path.stat()
    _require(signature(before) == signature(after),
             f"artifact changed during hashing: {path}")
    # Never trust supplied hashes or persist this cache. ctime detects same-size
    # edits even if mtime is restored; inode detects atomic replacement. Link
    # mapping is always inspected independently by _fingerprint.
    _FILE_HASH_CACHE[key] = value
    return value


def _fingerprint(path: Path) -> dict[str, Any]:
    links: list[dict[str, str]] = []
    def resolve(source: Path, ancestors: frozenset[Path] = frozenset()) -> Path:
        # Record every symlink component, including external directory aliases.
        current = Path(source.anchor)
        for part in source.parts[1:]:
            current = current / part
            if current.is_symlink():
                _require(current not in ancestors, f"symlink cycle: {source}")
                target = os.readlink(current)
                candidate = Path(os.path.abspath(current.parent / target)) if not Path(target).is_absolute() else Path(target)
                resolved_target = resolve(candidate, ancestors | {current})
                entry = {"path": str(current), "target": target, "resolved_target": str(resolved_target)}
                if entry not in links:
                    links.append(entry)
                current = resolved_target
        try:
            resolved = current.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise FreezeBlocked(f"unresolved artifact: {source}") from error
        return resolved
    original = path
    resolved = resolve(path)
    if resolved.is_dir():
        entries: list[dict[str, str]] = []
        def walk(source: Path, relative: Path, ancestors: frozenset[Path]) -> None:
            target = resolve(source)
            if target.is_dir():
                _require(target not in ancestors, f"directory symlink cycle: {source}")
                for child in sorted(source.iterdir()):
                    walk(child, relative / child.name, ancestors | {target})
            else:
                _require(target.is_file(), f"unsupported artifact type: {source}")
                entries.append({"relative_path": str(relative), "sha256": _sha_file(target)})
        walk(path, Path(), frozenset())
        _require(entries, f"empty artifact directory: {path}")
        entries.sort(key=lambda entry: entry["relative_path"])
        # Same content identity as phase-3 checkpoint_sha256: sorted relative
        # names, NUL separator, binary per-file digests. Link mapping is bound
        # separately by the role inventory, without changing model byte identity.
        tree_digest = hashlib.sha256()
        for entry in entries:
            tree_digest.update(entry["relative_path"].encode("utf-8") + b"\0")
            tree_digest.update(bytes.fromhex(entry["sha256"]))
        result = {"path": str(original), "resolved_path": str(resolved), "kind": "directory",
                  "sha256": tree_digest.hexdigest(), "files": entries}
    else:
        result = {"path": str(original), "resolved_path": str(resolved), "kind": "file", "sha256": _sha_file(resolved)}
    result["symlinks"] = sorted(links, key=lambda item: (item["path"], item["target"]))
    _require(all(Path(link["path"]).is_symlink() and os.readlink(link["path"]) == link["target"] and
                 str(Path(link["path"]).resolve(strict=True)) == link["resolved_target"] for link in links),
             "symlink changed during artifact hashing")
    return result


def artifact_inventory(repo_root: str | Path, artifact_paths: Mapping[str, Any]) -> dict[str, Any]:
    """Hash actual bytes. Missing inputs fail; no placeholder digests are made."""
    root = Path(repo_root).resolve()
    result = {}
    for role, supplied in sorted(artifact_paths.items()):
        values = [supplied] if isinstance(supplied, (str, Path)) else list(supplied)
        _require(values, f"empty artifact role: {role}")
        paths = []
        for value in values:
            raw = Path(value).expanduser()
            raw = raw if raw.is_absolute() else root / raw
            path = Path(os.path.abspath(raw))
            _require(role == "vla_checkpoint" or role.endswith("_implementation") or path.resolve().is_relative_to(root), f"artifact outside repo: {role}")
            paths.append(path)
        _require(len(paths) == len(set(paths)), f"duplicate artifact path: {role}")
        files = [_fingerprint(p) for p in sorted(paths)]
        result[role] = {"entries": files, "sha256": _digest(files)}
    return result


def _load(path: str | Path) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for k, value in pairs:
            _require(k not in result, f"duplicate JSON key: {k}")
            result[k] = value
        return result
    def strict(text: str) -> Any:
        parsed = json.loads(text, object_pairs_hook=unique, parse_constant=lambda v: (_ for _ in ()).throw(FreezeBlocked(f"nonfinite JSON: {v}")))
        _canonical(parsed)  # Also rejects exponent overflow, e.g. 1e999.
        return parsed
    try:
        return strict(text)
    except json.JSONDecodeError:
        if Path(path).suffix in {".yaml", ".yml"}:
            try:
                import yaml
            except ImportError as error:
                raise FreezeBlocked("BLOCKED_YAML_DEPENDENCY_UNAVAILABLE") from error
            class UniqueKeyLoader(yaml.SafeLoader):
                pass
            def construct_mapping(loader, node, deep=False):
                values = []
                for key_node, value_node in node.value:
                    key = loader.construct_object(key_node, deep=deep)
                    _require(isinstance(key, str), "non-string YAML key")
                    values.append((key, loader.construct_object(value_node, deep=deep)))
                return unique(values)
            UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
            value = yaml.load(text, Loader=UniqueKeyLoader)
            _canonical(value)
            return value
        try:
            lines = text.splitlines(keepends=True)
            _require(lines and all(line.endswith("\n") and line.strip() for line in lines), "torn or blank JSONL line")
            values = [strict(line) for line in lines]
            _require(all(isinstance(value, dict) for value in values), "JSONL rows must be objects")
            return values
        except json.JSONDecodeError as error:
            raise FreezeBlocked(f"malformed JSON/JSONL artifact: {path}") from error


def _single(inventory: Mapping[str, Any], role: str) -> Path:
    entries = inventory[role]["entries"]
    _require(len(entries) == 1 and entries[0]["kind"] == "file", f"{role} requires one file")
    return Path(entries[0]["path"])


def _records(value: Any, name: str) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("records", "sessions", "tasks", "episodes"):
            if key in value:
                value = value[key]
                break
    _require(isinstance(value, list) and value and all(isinstance(r, dict) for r in value), f"missing {name} records")
    return value


def _evidence_digests(inventory: Mapping[str, Any], role: str) -> set[str]:
    """Trace references must resolve to actual frozen bytes, never bare hashes."""
    result = set()
    for entry in inventory[role]["entries"]:
        result.add(entry["sha256"])
        if entry["kind"] == "file":
            result.add(entry["sha256"])
        else:
            result.update(item["sha256"] for item in entry["files"])
    return result


def _content_digest(inventory: Mapping[str, Any], role: str) -> str:
    """Checkpoint identity is its byte/tree digest, not a path-wrapper digest."""
    entries = inventory[role]["entries"]
    _require(len(entries) == 1, f"{role} needs a single identity-bearing file/tree")
    return entries[0]["sha256"]


def _master_key(row: Mapping[str, Any]) -> tuple[str, int, int]:
    if "pair_fields" in row:
        _require(isinstance(row["pair_fields"], Mapping), "malformed pair_fields")
        row = row["pair_fields"]
    _require(isinstance(row.get("task_id"), (str, int)) and not isinstance(row.get("task_id"), bool), "missing task_id")
    _require(type(row.get("initial_state_id")) is int and type(row.get("policy_seed")) is int, "missing state/seed")
    return str(row["task_id"]), row["initial_state_id"], row["policy_seed"]


def _journal_key(value: Any) -> tuple[str, str, str, int]:
    fields = ("protocol", "master_episode_id", "method", "event_index")
    parts = [value.get(field) for field in fields] if isinstance(value, Mapping) else list(value)
    _require(len(parts) == 4 and parts[0] in {"controlled", "end_to_end"}, "invalid journal key")
    _require(all(isinstance(v, str) and v and not any(c in v for c in "/\\\n\r") for v in parts[:3]), "invalid journal identifier")
    _require(type(parts[3]) is int and 0 <= parts[3] <= (8 if parts[0] == "controlled" else 4), "invalid journal event index")
    return tuple(parts)


def _production_provenance(row: Mapping[str, Any], identities: Mapping[str, Any], *, name: str) -> None:
    """Bind measured qualification to the admitted implementations and models."""
    actual = row.get("runtime_identities", row.get("identities"))
    _require(actual == identities, f"{name} runtime identity mismatch/missing")
    _require(row.get("fixture") is False, f"{name} fixture provenance missing/forbidden")
    vla = actual["vla"]
    _require(vla.get("learned_policy") is True and vla.get("uses_privileged_state") is False,
             f"{name} requires learned observation-only VLA")


def audit_journal_directory(directory: str | Path, *, expected_cells: Iterable[Any],
                            expected_phase: str, identities: Mapping[str, Any] | None = None,
                            exported_results: Sequence[Mapping[str, Any]] | None = None,
                            freeze_sha256: str | None = None) -> dict[str, Any]:
    """Read phase-3 immutable journals without opening their mutating writer.

    Accept the output directory or its ``journal`` subdirectory. Verify envelopes,
    exact cell sets, request/response pairing and retained completion snapshots.
    An export, when supplied, must equal the raw result payloads exactly. Returned
    results are verified payloads, not imputed cells. Digests establish consistency
    of supplied evidence; they cannot prove an external observation occurred.
    """
    root = Path(directory)
    if (root / "journal").is_dir():
        root = root / "journal"
    _require(root.is_dir(), "raw journal directory unavailable")
    _require(expected_phase in {"pilot", "formal", "development"}, "unsupported journal phase")
    expected_list = [_journal_key(value) for value in expected_cells]
    expected = set(expected_list)
    _require(len(expected) == len(expected_list), "duplicate expected journal cells")
    _require(not (root / "protocol_drift_stop.json").exists(), "journal durably stopped for protocol drift")
    def envelope(path: Path, kind: str, *, key=None, label=None) -> dict[str, Any]:
        _require(path.is_file() and path.read_bytes().endswith(b"\n"), f"missing/torn journal {kind}: {path}")
        value = _load(path)
        _require(isinstance(value, dict), "journal envelope must be an object")
        body = dict(value)
        claimed = body.pop("sha256", None)
        _require(claimed == _digest(body) and body.get("schema") == "cope-repeated-v2-journal-1" and body.get("kind") == kind,
                 f"journal envelope hash/schema/kind mismatch: {path}")
        if key is not None:
            _require(_journal_key(body.get("key", {})) == key, "journal envelope key mismatch")
        if label is not None:
            _require(body.get("label") == label, "journal snapshot label mismatch")
        _require(isinstance(body.get("payload"), dict), "journal payload must be an object")
        return body
    metadata = envelope(root / "frozen_metadata.json", "metadata")["payload"]
    frozen = metadata.get("status") == "FROZEN" and metadata.get("schema_version") == SCHEMA_VERSION
    if expected_phase == "formal":
        _require(frozen and freeze_sha256 is not None and metadata.get("bundle_sha256") == freeze_sha256,
                 "formal journal lacks expected frozen bundle")
        body = dict(metadata)
        _require(body.pop("bundle_sha256", None) == _digest(body), "journal frozen bundle digest mismatch")
    else:
        _require(metadata.get("phase") == expected_phase and metadata.get("fixture") is False,
                 "journal qualification phase/fixture provenance mismatch")
    if identities is not None:
        _require(metadata.get("identities", metadata.get("runtime_identities")) == identities,
                 "journal runtime identity mismatch/missing")
    collections: dict[str, dict[tuple, dict[str, Any]]] = {}
    for plural in ("intents", "responses", "results", "episodes"):
        _require((root / plural).is_dir(), f"missing journal collection: {plural}")
        found: dict[tuple, dict[str, Any]] = {}
        for path in sorted((root / plural).glob("*.json")):
            record = envelope(path, plural[:-1])
            key = _journal_key(record.get("key", {}))
            _require(key not in found, f"duplicate raw journal {plural} cell")
            _require(path.name == _digest(list(key)) + ".json", "journal filename/key mismatch")
            found[key] = record["payload"]
        collections[plural] = found
    intents, responses, results, episodes = (collections[k] for k in ("intents", "responses", "results", "episodes"))
    _require(set(results) == expected, "raw journal missing/unexpected result cells")
    _require(set(intents) == set(responses) and set(intents) <= expected, "raw journal ambiguous/orphan/unexpected call")
    trajectory_keys = {(*key[:3], 0) for key in expected}
    _require(trajectory_keys <= expected, "expected journal cells omit K0 baseline")
    _require(set(episodes) == trajectory_keys, "raw journal missing/unexpected terminal episode")
    for key, intent in intents.items():
        _require(key[3] != 0 and intent.get("request_sha256") == _digest(intent.get("request")), "journal request digest mismatch/K0 call")
        _require(responses[key].get("request_sha256") == intent["request_sha256"] and "response" in responses[key],
                 "journal response/request mismatch")
        _require(key[2] != "classical_execution_monitor" and not key[2].startswith("oracle"), "non-generative method called reasoner")
        if identities is not None:
            request = intent.get("request", {})
            config = request.get("config", {}) if isinstance(request, Mapping) else {}
            expected_reasoner = identities["reasoner"]
            _require(config.get("provider") == expected_reasoner["provider_id"] and config.get("model") == expected_reasoner["model_id"],
                     "raw journal request provider/model mismatch")
            _require(config.get("semantic_retries") == 0 and config.get("temperature") == 0,
                     "raw journal reasoner retry/temperature mismatch")
            _require(isinstance(request.get("messages"), list) and request["messages"], "raw journal exact prompt missing")
            response = responses[key]["response"]
            _require(isinstance(response, Mapping) and response.get("fixture") is False,
                     "raw journal response lacks non-fixture provenance")
    valid_statuses = {"COMPLETED", "METHOD_TIMEOUT", "METHOD_TERMINATED_BEFORE_REQUIRED_EVENT",
                      "METHOD_REJECTED_TERMINATED", "METHOD_PLANNING_FAILURE", "METHOD_COMPILATION_FAILURE",
                      "METHOD_ADAPTATION_FAILURE", "METHOD_RECOVERY_EXECUTION_FAILURE", "EVENT_TRIGGER_WINDOW_MISSED",
                      "EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE"}
    def provenance(payload: Mapping[str, Any], key: tuple, *, episode: bool = False) -> None:
        _require(all(payload.get(field) == value for field, value in zip(("protocol", "master_episode_id", "method"), key[:3])),
                 "journal payload/record identity mismatch")
        if not episode:
            _require(payload.get("event_index") == key[3], "journal result event index mismatch")
        _require(payload.get("phase") == expected_phase and payload.get("fixture") is False, "raw journal phase/fixture mismatch")
        _require(payload.get("status") in valid_statuses and type(payload.get("success")) is bool, "raw journal missing/invalid outcome")
        _require(payload.get("final_active_task_success_after_last_event") is payload["success"], "journal primary outcome mismatch")
        if payload["status"] != "COMPLETED":
            _require(payload["success"] is False, "failed journal cell claims success")
        if key[2] == ORACLE_METHOD:
            _require(payload.get("privileged") is True and payload.get("evidence_admissibility") == "diagnostic_oracle",
                     "oracle journal row lacks explicit diagnostic provenance")
        else:
            _require(payload.get("privileged") is not True and payload.get("evidence_admissibility") != "diagnostic_oracle",
                     "non-oracle journal row claims privileged provenance")
        if freeze_sha256 is not None:
            _require(payload.get("freeze_sha256") == freeze_sha256, "raw journal freeze identity mismatch")
    snapshots: dict[tuple[tuple, str], Mapping[str, Any]] = {}
    _require((root / "snapshots").is_dir(), "raw journal snapshots unavailable")
    for path in sorted((root / "snapshots").rglob("*.json")):
        record = envelope(path, "snapshot")
        key, label = _journal_key(record.get("key", {})), record.get("label")
        _require(key in expected and isinstance(label, str) and path.parent.name == label and path.name == _digest(list(key)) + ".json",
                 "raw journal unexpected/misnamed snapshot")
        _require((key, label) not in snapshots, "duplicate raw journal snapshot")
        snapshots[key, label] = record["payload"]
    def boundary(key: tuple) -> Mapping[str, Any]:
        choices = [snapshots[key, label] for label in ("completed", "post") if (key, label) in snapshots]
        _require(choices, f"raw journal missing completion snapshot: {key}")
        # Runner completion snapshots carry the exact result they committed.
        completed = snapshots.get((key, "completed"))
        if completed is not None:
            _require(completed.get("pending_result") == results[key], "snapshot/result payload mismatch")
            return completed
        return choices[0]
    for key, result in results.items():
        provenance(result, key)
        called = key in intents
        _require(result.get("provider_called", called) is called, "result provider-called state mismatch")
        _require(type(result.get("high_level_calls")) is int and result["high_level_calls"] == int(called), "result/raw provider call count mismatch")
        if result["status"] == "EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE":
            source_index = result.get("source_boundary_event_index")
            _require(type(source_index) is int and 0 <= source_index < key[3] and not called, "invalid unreached source/call")
            source_key = (*key[:3], source_index)
            _require(source_key in results and results[source_key]["status"] != "COMPLETED", "unreached cell lacks retained failed source result")
            _require(result.get("source_boundary_sha256") == _digest(boundary(source_key)), "unreached source boundary hash mismatch")
        else:
            boundary(key)
    for key, episode in episodes.items():
        provenance(episode, key, episode=True)
        final_index = max(k[3] for k in expected if k[:3] == key[:3])
        _require(episode["success"] is results[(*key[:3], final_index)]["success"], "episode/final result outcome mismatch")
        if "action_trace" in episode:
            _require(episode.get("action_trace_sha256") == _digest(episode["action_trace"]), "episode action trace hash mismatch")
    verified = [results[key] for key in sorted(results)]
    if exported_results is not None:
        exported = [dict(row) for row in exported_results]
        _require(sorted(map(_canonical, exported)) == sorted(map(_canonical, verified)), "exported results differ from immutable journal payloads")
    return {"status": "VALID", "expected_count": len(expected), "result_count": len(results),
            "results": verified, "metadata": metadata, "journal_root": str(root),
            "intents": intents, "responses": responses,
            "trajectory_identities": [{"protocol": key[0], "master_episode_id": key[1], "method": key[2],
                                        "identity": boundary(key).get("identity", {})} for key in sorted(trajectory_keys)]}


def _include_retained_auxiliary_cells(directory: str | Path, expected: Sequence[tuple], *,
                                       optional_methods: Sequence[str] = (ORACLE_METHOD,)) -> list[tuple]:
    """Retain allowed auxiliary arms when present; never remove their cells."""
    root = Path(directory)
    if (root / "journal").is_dir():
        root = root / "journal"
    present = set()
    for path in (root / "results").glob("*.json"):
        record = _load(path)
        _require(isinstance(record, Mapping) and isinstance(record.get("key"), Mapping), "raw journal envelope/key unavailable")
        if record["key"].get("method") in optional_methods:
            present.add(record["key"]["method"])
    auxiliary = {(key[0], key[1], method, key[3]) for key in expected for method in present}
    return list(expected) + sorted(auxiliary - set(expected))


def _validate_development_journals(records: Sequence[Mapping[str, Any]], inventory: Mapping[str, Any],
                                    identities: Mapping[str, Any]) -> None:
    entries = inventory["development_traces"]["entries"]
    _require(all(entry["kind"] == "directory" for entry in entries), "BLOCKED_DEVELOPMENT_TRACE_SCHEMA_UNAVAILABLE: raw journal directories required")
    by_digest = {entry["sha256"]: entry for entry in entries}
    _require(len(by_digest) == len(entries), "duplicate development raw journal")
    grouped: dict[str, list[Mapping[str, Any]]] = {digest: [] for digest in by_digest}
    for row in records:
        _production_provenance(row, identities, name="development")
        _require(row.get("trace_sha256") in by_digest, "development raw journal provenance missing")
        _require(row.get("information_condition") == "evidence_matched", "development comparator selection requires primary information condition")
        grouped[row["trace_sha256"]].append(row)
    for journal_digest, summaries in grouped.items():
        _require(summaries, "unreferenced development raw journal")
        expected = [("end_to_end", row["master_episode_id"], row["method"], index) for row in summaries for index in range(5)]
        expected = _include_retained_auxiliary_cells(by_digest[journal_digest]["path"], expected,
                                                       optional_methods=(*NON_ORACLE_METHODS[:2], ORACLE_METHOD))
        audit = audit_journal_directory(by_digest[journal_digest]["path"], expected_cells=expected,
                                         expected_phase="development", identities=identities)
        lookup = {(row["master_episode_id"], row["method"]): row for row in summaries}
        for result in audit["results"]:
            _require(result.get("information_condition") == "evidence_matched", "development raw information condition mismatch")
            if result["event_index"] != 4:
                continue
            if result["method"] not in COMPARATORS:
                continue
            summary = lookup[result["master_episode_id"], result["method"]]
            _require(result["success"] is summary.get("success"), "development summary/raw K4 outcome mismatch")
            corruption = [source["history_corruption"] for source in (result, result.get("metrics", {}), result.get("evaluation", {}))
                          if isinstance(source, Mapping) and "history_corruption" in source]
            _require(corruption and all(value == corruption[0] for value in corruption),
                     "BLOCKED_DEVELOPMENT_TRACE_SCHEMA_UNAVAILABLE: missing/contradictory raw history_corruption")
            value = corruption[0]
            measured = len(value) if isinstance(value, (list, dict)) else int(value) if type(value) is bool else value
            _require(type(measured) in (int, float) and math.isfinite(measured) and measured >= 0 and summary.get("history_corruption") == measured,
                     "development summary/raw history corruption mismatch")
        for trajectory in audit["trajectory_identities"]:
            if trajectory["method"] not in COMPARATORS:
                continue
            summary = lookup[trajectory["master_episode_id"], trajectory["method"]]
            pair = _master_key(summary)
            _require(trajectory["identity"].get("initial_state_id") == pair[1] and trajectory["identity"].get("seed") == pair[2],
                     "development raw snapshot/summary initial-state or seed mismatch")


def deterministic_shards(records: Sequence[Mapping[str, Any]], *, shard_count: int = 8) -> list[list[dict[str, Any]]]:
    """SHA256(master_episode_id) modulo 8; never split a master across arms/K."""
    _require(shard_count == 8, "formal sharding is preregistered as exactly 8 ways")
    shards: list[list[dict[str, Any]]] = [[] for _ in range(shard_count)]
    masters: dict[str, tuple[str, int, int]] = {}
    seen_rows: set[str] = set()
    for source in records:
        row = copy.deepcopy(dict(source))
        master = row.get("master_episode_id")
        _require(isinstance(master, str) and bool(master.strip()), "missing master_episode_id")
        if "pair_fields" in row or all(k in row for k in ("task_id", "initial_state_id", "policy_seed")):
            identity = _master_key(row)
            _require(master not in masters or masters[master] == identity, f"inconsistent master identity: {master}")
            masters[master] = identity
        row_digest = _digest(row)
        _require(row_digest not in seen_rows, f"duplicate manifest record: {master}")
        seen_rows.add(row_digest)
        owner = int(hashlib.sha256(master.encode("utf-8")).hexdigest(), 16) % shard_count
        shards[owner].append(row)
    for shard in shards:
        shard.sort(key=lambda r: (r["master_episode_id"], _canonical(r)))
    return shards


def _validate_config(config: Mapping[str, Any]) -> None:
    _require(config.get("methods", {}).get("non_oracle") == list(NON_ORACLE_METHODS), "non-oracle method registry drift")
    task = config.get("task_selection", {})
    _require(task.get("formal_state_ids") == [0, 1, 2, 3, 4] and task.get("formal_policy_seeds") == [11, 29, 47], "formal grid drift")
    _require(not set(task.get("calibration_policy_seeds", [])).intersection(task["formal_policy_seeds"]), "calibration/formal seeds overlap")
    _require(task.get("calibration_state_ids") == [0, 1, 2, 3, 4] and task.get("calibration_policy_seeds") == [101, 131], "calibration grid drift")
    _require(task.get("clean_success_interval") == [0.40, 0.95] and task.get("forbid_selection_by_method_difference") is True, "task selection contract drift")
    primary = config.get("primary_analysis", {})
    required = {"protocol": "end_to_end", "checkpoint": 4, "success_margin_vs_nonpersistent": 0.10,
                "generic_noninferiority_margin": -0.05, "bootstrap_replicates": 10000, "alpha": 0.05,
                "multiple_testing": "holm", "cluster_unit": "master_episode_id"}
    _require(all(primary.get(k) == v for k, v in required.items()), "primary statistical preregistration drift")
    reasoner = config.get("reasoner", {})
    _require(reasoner.get("semantic_retries") == 0 and reasoner.get("calls_per_event") == 1 and reasoner.get("record_exact_prompts") is True, "reasoner call/retry contract drift")
    for protocol, count, checkpoints in (("controlled", 8, [0, 1, 2, 4, 8]), ("end_to_end", 4, [0, 1, 2, 4])):
        p = config.get("protocols", {}).get(protocol, {})
        _require(p.get("event_count") == count and p.get("checkpoints") == checkpoints, f"{protocol} checkpoint contract drift")


def _validate_identities(identities: Mapping[str, Any], inventory: Mapping[str, Any]) -> None:
    def check_secrets(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                _require(not re.search(r"api.?key|password|secret|credential|access.?token", str(key), re.I), "credentials forbidden in frozen identity")
                check_secrets(child)
        elif isinstance(value, (tuple, list)):
            for child in value:
                check_secrets(child)
    check_secrets(identities)
    _require(set(identities) == set(IDENTITY_COMPONENTS), "missing/unexpected identity components")
    for component in IDENTITY_COMPONENTS:
        value = identities[component]
        _require(isinstance(value, dict) and all(isinstance(value.get(k), str) and value[k].strip() for k in ("provider_id", "version")), f"missing {component} identity/version")
        _require(value.get("implementation_sha256") == inventory[f"{component}_implementation"]["sha256"], f"{component} implementation hash mismatch")
    reasoner, vla = identities["reasoner"], identities["vla"]
    for component in (reasoner, vla):
        _require(not BAD_PROVIDER.search(component["provider_id"]), "BLOCKED_FAKE_OR_PRIVILEGED_PROVIDER")
        _require(isinstance(component.get("model_id"), str) and component["model_id"].strip(), "missing model ID")
        _require(not BAD_PROVIDER.search(component["model_id"]), "BLOCKED_FAKE_OR_PRIVILEGED_MODEL")
        _require(isinstance(component.get("model_revision"), str) and component["model_revision"].strip() and component["model_revision"].lower() not in {"latest", "main", "unknown"}, "unpinned model revision")
        _require(HEX256.fullmatch(component.get("model_sha256", "")), "missing model digest")
        _require(isinstance(component.get("model_digest_provenance"), str) and len(component["model_digest_provenance"].strip()) >= 10, "missing model digest provenance")
    _require(vla.get("learned_policy") is True and vla.get("uses_privileged_state") is False, "BLOCKED_VLA_ADAPTER_UNAVAILABLE")
    _require(vla.get("checkpoint_sha256") == _content_digest(inventory, "vla_checkpoint"), "VLA checkpoint hash mismatch")


def _validate_upstream_design(root: Path, config: Mapping[str, Any], catalog_data: Any,
                              manifest: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Execute committed phase-1 semantic validators; no supplied pass flags."""
    try:
        from .config import validate_config
        from .manifest import expected_counts, validate_manifest
        from .task_catalog import TaskCatalog, select_eligible_tasks
    except ImportError as error:
        raise FreezeBlocked("BLOCKED_PHASE1_VALIDATORS_UNAVAILABLE") from error
    try:
        errors = validate_config(config)
        _require(not errors, "INVALID_PROTOCOL_CONFIG: " + "; ".join(errors))
        catalog = TaskCatalog.from_dict(catalog_data)
        selected = select_eligible_tasks(catalog, allow_synthetic=False)
        revisions = {row.get("source_commit") for row in manifest}
        _require(len(revisions) == 1, "manifest requires one committed producer revision")
        revision = next(iter(revisions))
        _require(isinstance(revision, str) and bool(re.fullmatch(r"[0-9a-f]{40}", revision)), "invalid manifest producer SHA")
        _git(root, "merge-base", "--is-ancestor", revision, "HEAD")
        validation = validate_manifest(manifest, config, catalog, source_commit=revision, allow_synthetic=False)
        _require(validation.get("errors") == [] and validation.get("missing") == [] and
                 validation.get("duplicate") == [] and validation.get("unexpected") == [],
                 f"manifest semantic validation failed: {validation}")
        counts = expected_counts(len(selected), config)
        counts["event_level_reasoner_calls"] = {
            "per_condition": {protocol: counts["unique_master_sessions"] * 7 * spec["event_count"]
                              for protocol, spec in config["protocols"].items()},
            "generative_non_oracle_methods": 7,
            "classical_and_oracle_calls_per_event": 0,
        }
        counts["event_level_reasoner_calls"]["all_conditions_total"] = (
            sum(counts["event_level_reasoner_calls"]["per_condition"].values()) * len(counts["information_conditions"]))
        return [task.to_dict() for task in selected], counts
    except (TypeError, ValueError, KeyError) as error:
        if isinstance(error, FreezeBlocked):
            raise
        raise FreezeBlocked(str(error)) from error


def _validate_audit(root: Path, inventory: Mapping[str, Any]) -> None:
    report = _load(_single(inventory, "gate_report"))
    _require(isinstance(report, dict) and report.get("schema_version") == GATE_SCHEMA_VERSION, "unsupported gate evidence schema")
    provenance = report.get("provenance", {})
    _require(isinstance(provenance.get("producer_command"), list) and provenance["producer_command"] and all(isinstance(v, str) and v for v in provenance["producer_command"]), "missing gate producer command")
    revision = provenance.get("producer_git_sha", "")
    _require(bool(re.fullmatch(r"[0-9a-f]{40}", revision)), "missing audit producer git SHA")
    _git(root, "merge-base", "--is-ancestor", revision, "HEAD")
    sources = inventory["gate_tests"]["entries"]
    _require(all(s["kind"] == "file" for s in sources), "gate_tests requires explicit source files")
    source_names: set[str] = set()
    for source in sources:
        path = Path(source["path"])
        relative = str(path.relative_to(root))
        _require(_git(root, "hash-object", str(path)) == _git(root, "rev-parse", f"{revision}:{relative}"), "audit source differs from producer revision")
        source_names.update(n.name for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_"))
    try:
        junit = ET.parse(_single(inventory, "junit_report")).getroot()
    except ET.ParseError as error:
        raise FreezeBlocked("malformed JUnit report") from error
    cases = list(junit.iter("testcase"))
    _require(cases and all(not any(c.find(t) is not None for t in ("failure", "error", "skipped")) for c in cases), "upstream tests failed/errored/skipped")
    case_names = [c.attrib.get("name", "") for c in cases]
    _require(all(n.split("[")[0] in source_names for n in case_names), "test report lacks matching committed test source")
    checks = report.get("checks", {})
    _require(set(checks) == set(REQUIRED_CHECKS), "incomplete upstream gate coverage")
    for check in REQUIRED_CHECKS:
        ids = checks[check]
        _require(isinstance(ids, list) and ids and all(isinstance(n, str) and n in case_names for n in ids), f"gate lacks concrete test cases: {check}")
    expected_inputs = {k: v["sha256"] for k, v in inventory.items() if k != "gate_report"}
    _require(report.get("input_sha256") == expected_inputs, "audit input hashes do not match current inputs")


def select_primary_comparator(development_records: Sequence[Mapping[str, Any]], *, formal_keys: Iterable[tuple[str, int, int]] = (),
                              identities: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Dev K=4 success, then lower corruption, then lexical name; no formal data."""
    forbidden = set(formal_keys)
    paired: dict[str, dict[str, Mapping[str, Any]]] = {m: {} for m in COMPARATORS}
    for row in development_records:
        if identities is not None:
            _production_provenance(row, identities, name="development")
        _require(row.get("phase") == "development" and row.get("protocol") == "end_to_end" and row.get("checkpoint") == 4, "comparator selection requires only development VLA K=4")
        _require(_master_key(row) not in forbidden, "development/formal split overlap")
        method, master = row.get("method"), row.get("master_episode_id")
        _require(method in paired and isinstance(master, str) and master, "invalid development comparator/master")
        _require(master not in paired[method], "duplicate development cell")
        _require(type(row.get("success")) is bool, "missing development outcome")
        corruption = row.get("history_corruption")
        _require(type(corruption) in (int, float) and math.isfinite(corruption) and corruption >= 0, "missing development corruption")
        paired[method][master] = row
    master_ids = set(paired[COMPARATORS[0]])
    _require(master_ids and all(set(rows) == master_ids for rows in paired.values()), "incomplete paired development split")
    for master in master_ids:
        _require(len({_master_key(rows[master]) for rows in paired.values()}) == 1, "development pairing identity mismatch")
    ranking = [{"method": m, "n": len(rows), "successes": sum(r["success"] for r in rows.values()),
                "history_corruption": sum(r["history_corruption"] for r in rows.values())} for m, rows in paired.items()]
    ranking.sort(key=lambda r: (-r["successes"], r["history_corruption"], r["method"]))
    return {"method": ranking[0]["method"], "rule": "success_desc_corruption_asc_lexical_asc", "ranking": ranking,
            "master_episode_ids": sorted(master_ids), "development_sha256": _digest(list(development_records))}


def _validate_records(root: Path, config: Mapping[str, Any], inventory: Mapping[str, Any], identities: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    catalog_data = _load(_single(inventory, "catalog"))
    catalog = _records(catalog_data, "catalog")
    manifest = _records(_load(_single(inventory, "manifest")), "manifest")
    selected, counts = _validate_upstream_design(root, config, catalog_data, manifest)
    _require(8 <= len(selected) <= 10, "BLOCKED_INSUFFICIENT_ELIGIBLE_TASKS")
    tasks = {str(r.get("task_id")) for r in selected}
    all_tasks = {str(r.get("task_id")) for r in catalog}
    _require(len(all_tasks) == len(catalog) and "None" not in all_tasks, "duplicate/missing catalog task")
    calibration = _records(_load(_single(inventory, "calibration_records")), "calibration")
    expected = {(t, state, seed) for t in all_tasks for state in [0, 1, 2, 3, 4] for seed in [101, 131]}
    if isinstance(catalog_data, dict):
        embedded = [r for task in catalog for r in task.get("calibration_records", [])]
        _require(sorted(map(_canonical, embedded)) == sorted(map(_canonical, calibration)), "raw calibration differs from task selection evidence")
    observed: dict[tuple[str, int, int], bool] = {}
    for row in calibration:
        key = _master_key(row)
        _require(key in expected and key not in observed, "unexpected/duplicate calibration cell")
        _require(type(row.get("success")) is bool and row.get("phase", "calibration") == "calibration", "invalid calibration outcome")
        privileged = row.get("privileged_policy_state", row.get("uses_privileged_state"))
        _require(row.get("learned_policy") is True and privileged is False and row.get("checkpoint_sha256") == identities["vla"]["checkpoint_sha256"], "calibration policy provenance mismatch")
        policy = row.get("policy_id", row.get("provider_id"))
        trace = row.get("evidence_sha256", row.get("trace_sha256"))
        _require(policy == identities["vla"]["provider_id"] and trace in _evidence_digests(inventory, "calibration_traces"), "missing calibration trace provenance")
        observed[key] = row["success"]
    _require(set(observed) == expected, "BLOCKED_INCOMPLETE_CALIBRATION")
    _require(all(0.40 <= sum(v for k, v in observed.items() if k[0] == t) / 10 <= 0.95 for t in tasks), "BLOCKED_CLEAN_SUCCESS_OUTSIDE_INTERVAL")
    expected_formal = {(t, state, seed) for t in tasks for state in [0, 1, 2, 3, 4] for seed in [11, 29, 47]}
    keys = [_master_key(row) for row in manifest]
    _require(len(keys) == len(set(keys)) and set(keys) == expected_formal, "formal manifest exact master grid mismatch")
    masters = [r.get("master_episode_id") for r in manifest]
    _require(all(isinstance(m, str) and m for m in masters) and len(masters) == len(set(masters)), "duplicate/missing master IDs")
    for protocol, count in (("controlled", 8), ("end_to_end", 4)):
        pilots = _records(_load(_single(inventory, f"pilot_{protocol}_records")), f"{protocol} pilot")
        seen = set()
        raw_entries = inventory[f"pilot_{protocol}_journals"]["entries"]
        _require(all(entry["kind"] == "directory" for entry in raw_entries), "pilot requires raw journal directories, not summary files")
        raw_by_digest = {entry["sha256"]: entry for entry in raw_entries}
        _require(len(raw_by_digest) == len(raw_entries), "duplicate raw pilot journal")
        grouped: dict[str, list[Mapping[str, Any]]] = {digest: [] for digest in raw_by_digest}
        for row in pilots:
            _require(row.get("phase") == "pilot" and row.get("protocol") == protocol and row.get("status") == "COMPLETE", "pilot incomplete/wrong protocol")
            _require(row.get("method") in NON_ORACLE_METHODS and row.get("event_indices") == list(range(1, count + 1)), "pilot coverage incomplete")
            _require(row.get("integrity_status") == "VALID" and row.get("missing_cells") == 0 and row.get("duplicate_cells") == 0 and row.get("unexpected_cells") == 0, "pilot integrity failed")
            _require(_master_key(row) not in expected_formal, "pilot/formal split overlap")
            _require(row.get("master_episode_id") not in masters, "pilot/formal master ID overlap")
            _production_provenance(row, identities, name=f"pilot {protocol}")
            _require(row.get("journal_sha256") in raw_by_digest, "pilot journal provenance missing")
            grouped[row["journal_sha256"]].append(row)
            condition = row.get("information_condition")
            _require(condition in {"evidence_matched", "token_matched"}, "pilot information condition missing")
            key = (condition, row.get("master_episode_id"), row["method"])
            _require(key not in seen, "duplicate pilot trajectory")
            seen.add(key)
        for condition, master in {(c, m) for c, m, _ in seen}:
            _require({method for c, m, method in seen if (c, m) == (condition, master)} == set(NON_ORACLE_METHODS), "unpaired pilot methods")
        for journal_digest, summaries in grouped.items():
            _require(summaries, "unreferenced pilot journal artifact")
            conditions = {row["information_condition"] for row in summaries}
            _require(len(conditions) == 1, "one raw journal cannot mix information conditions")
            expected_cells = [(protocol, row["master_episode_id"], row["method"], index)
                              for row in summaries for index in range(count + 1)]
            expected_cells = _include_retained_auxiliary_cells(raw_by_digest[journal_digest]["path"], expected_cells)
            audit = audit_journal_directory(raw_by_digest[journal_digest]["path"], expected_cells=expected_cells,
                                             expected_phase="pilot", identities=identities)
            _require(all(result.get("information_condition") in conditions for result in audit["results"]),
                     "pilot raw journal/summary information condition mismatch")
            summaries_by_key = {(row["master_episode_id"], row["method"]): row for row in summaries}
            for trajectory in audit["trajectory_identities"]:
                if trajectory["method"] == ORACLE_METHOD:
                    continue
                summary = summaries_by_key[trajectory["master_episode_id"], trajectory["method"]]
                identity = trajectory["identity"]
                pair = _master_key(summary)
                _require(identity.get("initial_state_id") == pair[1] and identity.get("seed") == pair[2],
                         "pilot raw snapshot/summary initial-state or seed mismatch")
    dev = _records(_load(_single(inventory, "development_records")), "development")
    _validate_development_journals(dev, inventory, identities)
    comparator = select_primary_comparator(dev, formal_keys=expected_formal, identities=identities)
    _require(not set(comparator["master_episode_ids"]).intersection(masters), "development/formal master ID overlap")
    return manifest, comparator, counts


def build_freeze_bundle(*, repo_root: str | Path, artifact_paths: Mapping[str, Any], identities: Mapping[str, Any], phase3_sha: str) -> dict[str, Any]:
    """Return a reviewable freeze only if all inputs/gates validate.

    See REQUIRED_ARTIFACTS, REQUIRED_CHECKS and tests for the evidence contract.
    Freeze runs after the analysis-code commit, with phase3_sha an ancestor.
    This deliberately does not manufacture missing pilot/calibration evidence.
    """
    root = Path(repo_root).resolve()
    missing = sorted(set(REQUIRED_ARTIFACTS).difference(artifact_paths))
    _require(not missing, f"BLOCKED_MISSING_FREEZE_ARTIFACTS: {', '.join(missing)}")
    git = _git_identity(root)
    _require(bool(re.fullmatch(r"[0-9a-f]{40}", phase3_sha)), "missing phase-3 SHA")
    _git(root, "merge-base", "--is-ancestor", phase3_sha, git["sha"])
    inventory = artifact_inventory(root, artifact_paths)
    config = _load(_single(inventory, "config"))
    _require(isinstance(config, dict), "malformed config")
    _validate_config(config)
    _validate_identities(identities, inventory)
    _validate_audit(root, inventory)
    manifest, comparator, counts = _validate_records(root, config, inventory, identities)
    shards = deterministic_shards(manifest)
    bundle = {"schema_version": SCHEMA_VERSION, "status": "FROZEN", "repo_root": str(root),
              "git": git, "phase3_sha": phase3_sha, "artifacts": inventory,
              "identities": copy.deepcopy(dict(identities)), "primary_comparator": comparator,
              "expected_counts": counts, "shard_count": 8,
              "shards": [{"shard_id": i, "master_episode_ids": [r["master_episode_id"] for r in rows],
                          "manifest_sha256": _digest(rows)} for i, rows in enumerate(shards)],
              "evidence_limit": "Digests bind provenance and bytes; they do not authenticate a remote model or independently establish that reported observations occurred."}
    bundle["bundle_sha256"] = _digest(bundle)
    validate_static_frozen_bundle(bundle)
    return bundle


def validate_frozen_bundle(frozen_bundle: Mapping[str, Any], *, current_identity: Callable[[], Mapping[str, Any]], repo_root: str | Path | None = None) -> None:
    """Fail with INVALID_PROTOCOL_DRIFT on any changed binding; return None on pass.

    Re-read bytes both before and after the live-identity callback to reject a
    mutation during validation. This is a boundary check, not a filesystem lock
    or an atomic transaction with a remote provider. The runner should also use
    the context manager when it can durably retain a response before checking.
    """
    try:
        bundle = copy.deepcopy(dict(frozen_bundle))
        digest = bundle.pop("bundle_sha256", None)
        _require(digest == _digest(bundle), "freeze bundle digest mismatch")
        _require(bundle.get("schema_version") == SCHEMA_VERSION and bundle.get("status") == "FROZEN", "no authorized frozen bundle")
        root = Path(repo_root or bundle["repo_root"]).resolve()
        _require(str(root) == bundle["repo_root"], "freeze repository relocation requires a new freeze")
        _require(_git_identity(root) == bundle["git"], "git SHA/tree or cleanliness drift")
        paths = {role: [e["path"] for e in record["entries"]] for role, record in bundle["artifacts"].items()}
        _require(artifact_inventory(root, paths) == bundle["artifacts"], "frozen input bytes drift")
        live = copy.deepcopy(dict(current_identity()))
        _require(live == bundle["identities"], "provider/model/checkpoint/backend identity drift")
        _validate_bound_protocol(bundle, root, live)
        _require(artifact_inventory(root, paths) == bundle["artifacts"], "input changed during live identity check")
        _require(_git_identity(root) == bundle["git"], "git changed during validation")
    except ProtocolDrift:
        raise
    except (FreezeBlocked, KeyError, TypeError, ValueError, OSError, RuntimeError) as error:
        raise ProtocolDrift(str(error)) from error


def _validate_bound_protocol(bundle: Mapping[str, Any], root: Path, identities: Mapping[str, Any]) -> None:
    """Shared evidence checks; runtime and historical git policies remain separate."""
    _require(set(REQUIRED_ARTIFACTS).issubset(bundle["artifacts"]), "missing required frozen artifact roles")
    _validate_identities(identities, bundle["artifacts"])
    _require(bool(re.fullmatch(r"[0-9a-f]{40}", bundle["phase3_sha"])), "missing phase-3 SHA")
    _git(root, "merge-base", "--is-ancestor", bundle["phase3_sha"], bundle["git"]["sha"])
    config = _load(_single(bundle["artifacts"], "config"))
    _validate_config(config)
    _validate_audit(root, bundle["artifacts"])
    manifest, comparator, counts = _validate_records(root, config, bundle["artifacts"], identities)
    _require(comparator == bundle["primary_comparator"] and counts == bundle["expected_counts"], "frozen comparator/count evidence mismatch")
    _require(bundle["shard_count"] == 8, "frozen shard count drift")
    shards = deterministic_shards(manifest)
    expected_shards = [{"shard_id": i, "master_episode_ids": [row["master_episode_id"] for row in rows],
                        "manifest_sha256": _digest(rows)} for i, rows in enumerate(shards)]
    _require(expected_shards == bundle["shards"], "frozen shard ownership differs from manifest")


def validate_static_frozen_bundle(frozen_bundle: Mapping[str, Any], *, repo_root: str | Path | None = None) -> None:
    """Verify exact-HEAD frozen evidence for no-call/empty-shard bookkeeping.

    No live provider or model is loaded, probed, or claimed. This check cannot
    authorize any runtime or external call: nonempty execution still requires
    ``validate_frozen_bundle`` with a real live-identity callback.
    """
    try:
        bundle = copy.deepcopy(dict(frozen_bundle))
        digest = bundle.pop("bundle_sha256", None)
        _require(digest == _digest(bundle), "freeze bundle digest mismatch")
        _require(bundle.get("schema_version") == SCHEMA_VERSION and bundle.get("status") == "FROZEN", "no authorized frozen bundle")
        root = Path(repo_root or bundle["repo_root"]).resolve()
        _require(str(root) == bundle["repo_root"], "freeze repository relocation requires a new freeze")
        _require(_git_identity(root) == bundle["git"], "git SHA/tree or cleanliness drift")
        paths = {role: [entry["path"] for entry in record["entries"]] for role, record in bundle["artifacts"].items()}
        _require(artifact_inventory(root, paths) == bundle["artifacts"], "frozen input bytes or links drift")
        _validate_bound_protocol(bundle, root, bundle["identities"])
        _require(artifact_inventory(root, paths) == bundle["artifacts"], "input changed during static validation")
        _require(_git_identity(root) == bundle["git"], "git changed during static validation")
    except ProtocolDrift:
        raise
    except (FreezeBlocked, KeyError, TypeError, ValueError, OSError, RuntimeError) as error:
        raise ProtocolDrift(str(error)) from error


ARCHIVED_ARTIFACT_EXTENSIONS = frozenset({".md", ".csv", ".tsv", ".txt", ".json", ".jsonl",
                                          ".yaml", ".yml", ".xml", ".log", ".gz"})


def _archive_artifact(root: Path, relative: str) -> None:
    path = Path(relative)
    _require(not path.is_absolute() and len(path.parts) >= 2 and path.parts[0] in {"research", "docs"} and
             ".." not in path.parts, f"archived commit adds a non-artifact path: {relative}")
    journal_sidecar = path.name == ".journal-owner.lock" or bool(re.fullmatch(r"\.pending-[0-9a-f]{32}", path.name))
    _require(path.suffix.lower() in ARCHIVED_ARTIFACT_EXTENSIONS or journal_sidecar,
             f"archived commit adds unsupported/source file: {relative}")
    if path.suffix.lower() == ".gz" and path.with_suffix("").suffix:
        _require(path.with_suffix("").suffix.lower() in ARCHIVED_ARTIFACT_EXTENSIONS - {".gz"},
                 f"archived commit adds compressed source file: {relative}")
    source = root / path
    _require(source.is_file() and not source.is_symlink() and not (source.stat().st_mode & 0o111),
             f"archived artifact must be a nonexecutable regular file: {relative}")
    with (gzip.open(source, "rb") if path.suffix.lower() == ".gz" else source.open("rb")) as handle:
        prefix = handle.read(8)
    if prefix.startswith(b"\xef\xbb\xbf"):
        prefix = prefix[3:]
    executable_signatures = (b"#!", b"\x7fELF", b"MZ", b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
                             b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe")
    _require(not prefix.startswith(executable_signatures), f"archived artifact contains executable code: {relative}")


def _validate_archived_git(root: Path, frozen_git: Mapping[str, Any]) -> dict[str, str]:
    current = _git_identity(root)
    frozen_sha = frozen_git.get("sha", "")
    _require(isinstance(frozen_sha, str) and bool(re.fullmatch(r"[0-9a-f]{40}", frozen_sha)), "missing frozen git SHA")
    _require(_git(root, "rev-parse", f"{frozen_sha}^{{tree}}") == frozen_git.get("tree_sha"), "frozen git tree mismatch")
    _git(root, "merge-base", "--is-ancestor", frozen_sha, current["sha"])
    raw = _git(root, "diff", "--raw", "--no-abbrev", "--no-renames", "-z", frozen_sha, current["sha"])
    entries = raw.split("\0") if raw else []
    if entries and entries[-1] == "":
        entries.pop()
    _require(len(entries) % 2 == 0, "malformed archived git diff")
    for index in range(0, len(entries), 2):
        header, path = entries[index:index + 2]
        fields = header.split()
        _require(len(fields) == 5 and fields[0] == ":000000" and fields[1] == "100644" and fields[4] == "A",
                 f"archived commits may only add nonexecutable artifacts: {path}")
        _archive_artifact(root, path)
    # Untracked reports are allowed during analysis, under the same artifact
    # restriction. A new source file cannot enter via an output directory.
    for relative in _git(root, "ls-files", "--others", "--exclude-standard").splitlines():
        _archive_artifact(root, relative)
    return current


def validate_archived_bundle(frozen_bundle: Mapping[str, Any], *, repo_root: str | Path | None = None) -> None:
    """Verify historical evidence after a separate result-artifact commit.

    This read-only check authorizes reanalysis only, never an external call. HEAD
    may descend from the frozen commit solely by adding ordinary artifact files
    under research/ or docs/. All original bytes, links, implementations, model
    identities, protocol evidence and shard ownership must still match. Runtime
    admission continues to require ``validate_frozen_bundle`` and exact HEAD.
    """
    try:
        bundle = copy.deepcopy(dict(frozen_bundle))
        digest = bundle.pop("bundle_sha256", None)
        _require(digest == _digest(bundle), "freeze bundle digest mismatch")
        _require(bundle.get("schema_version") == SCHEMA_VERSION and bundle.get("status") == "FROZEN", "no authorized frozen bundle")
        root = Path(repo_root or bundle["repo_root"]).resolve()
        _require(str(root) == bundle["repo_root"], "freeze repository relocation requires a new freeze")
        current = _validate_archived_git(root, bundle["git"])
        paths = {role: [entry["path"] for entry in record["entries"]] for role, record in bundle["artifacts"].items()}
        _require(artifact_inventory(root, paths) == bundle["artifacts"], "frozen input bytes or links drift")
        _validate_bound_protocol(bundle, root, bundle["identities"])
        _require(artifact_inventory(root, paths) == bundle["artifacts"], "input changed during archived validation")
        _require(_validate_archived_git(root, bundle["git"]) == current, "git changed during archived validation")
    except ProtocolDrift:
        raise
    except (FreezeBlocked, KeyError, TypeError, ValueError, OSError, RuntimeError, EOFError) as error:
        raise ProtocolDrift(str(error)) from error


@contextlib.contextmanager
def formal_call_guard(frozen_bundle: Mapping[str, Any], *, current_identity: Callable[[], Mapping[str, Any]]):
    """Validate before/after a formal call; preserve all intents/responses on drift."""
    validate_frozen_bundle(frozen_bundle, current_identity=current_identity)
    try:
        yield
    finally:
        validate_frozen_bundle(frozen_bundle, current_identity=current_identity)


def write_freeze_artifacts(bundle: Mapping[str, Any], *, output_dir: str | Path) -> list[str]:
    """Write a new TXT freeze plus all eight CSV shard ownership files, exclusively."""
    root = Path(bundle["repo_root"])
    output = Path(output_dir).resolve()
    _require(any(output.is_relative_to(root / p) for p in ("research", "docs")), "freeze output must be under research/ or docs/")
    _require(not output.exists(), "refusing to overwrite freeze artifacts")
    validate_static_frozen_bundle(bundle)
    output.mkdir(parents=True, exist_ok=False)
    written = []
    contents = {"FREEZE.txt": _canonical(dict(bundle)) + "\n"}
    for shard in bundle["shards"]:
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["shard_id", "master_episode_id"])
        writer.writerows((shard["shard_id"], master) for master in shard["master_episode_ids"])
        contents[f"SHARD_{shard['shard_id']:02d}.csv"] = stream.getvalue()
    for name, value in contents.items():
        path = output / name
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        written.append(str(path))
    return written
