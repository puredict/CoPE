from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from cope.types import canonical_json, stable_hash


SCHEMA = "generic-compact-transaction-v1"


class CompactTransactionError(ValueError):
    pass


class CompactTransactionRejected(CompactTransactionError):
    def __init__(self, message: str, receipt: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.receipt = copy.deepcopy(dict(receipt))


@dataclass(frozen=True)
class CompactTransactionResult:
    post_state: dict[str, Any]
    proposal: dict[str, Any]
    receipt: dict[str, Any]
    directive: str


def _without_history(state: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in state.items() if key != "action_history"}


def proposal_from_verbose_carrier(carrier: Mapping[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "event_id", "base_version", "writes"}
    if set(carrier) != required or carrier.get("schema_version") != "generic-transaction-carrier-v1":
        raise CompactTransactionError("verbose carrier is noncanonical")
    writes = []
    for item in carrier["writes"]:
        address = str(item["address"])
        writes.append(
            {
                "op": "add" if "/+/" in address else "replace",
                "path": address,
                "value": copy.deepcopy(item["value"]),
            }
        )
    return {
        "schema_version": SCHEMA,
        "base_version": int(carrier["base_version"]),
        "event_id": str(carrier["event_id"]),
        "writes": writes,
    }


def parse_proposal(
    value: Mapping[str, Any], state: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Any]:
    required = {"schema_version", "base_version", "event_id", "writes"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise CompactTransactionError("compact proposal fields are noncanonical")
    if value.get("schema_version") != SCHEMA:
        raise CompactTransactionError("compact proposal schema mismatch")
    if int(value.get("base_version", -1)) != int(state["state_version"]):
        raise CompactTransactionError("compact proposal base version mismatch")
    if value.get("event_id") != event.get("event_id"):
        raise CompactTransactionError("compact proposal event ID mismatch")
    writes = value.get("writes")
    if not isinstance(writes, list) or len(writes) > 64:
        raise CompactTransactionError("compact proposal writes must be a bounded list")
    paths = []
    for item in writes:
        if not isinstance(item, Mapping) or set(item) != {"op", "path", "value"}:
            raise CompactTransactionError("compact write fields are noncanonical")
        if item["op"] not in {"add", "replace"}:
            raise CompactTransactionError("compact write operation is unsupported")
        path = str(item["path"])
        if not path.startswith("/") or "//" in path or path.endswith("/"):
            raise CompactTransactionError("compact write path is malformed")
        parts = path.removeprefix("/").split("/")
        root_projection = len(parts) == 1 and parts[0] in {
            "current_goal",
            "plan",
            "pending_restorations",
            "state_version",
            "evidence_versions",
        }
        record_add = len(parts) == 3 and parts[0] in {"commitments", "entities"} and parts[1] == "+"
        record_update = len(parts) == 3 and parts[0] == "commitments" and parts[1] != "+"
        if not (root_projection or record_add or record_update):
            raise CompactTransactionError("compact write path is not allowlisted")
        paths.append(path)
    if len(set(paths)) != len(paths):
        raise CompactTransactionError("compact proposal contains duplicate paths")
    return copy.deepcopy(dict(value))


def _record_by_id(rows: list[dict[str, Any]], record_id: str) -> dict[str, Any]:
    selected = [row for row in rows if row.get("id") == record_id]
    if len(selected) != 1:
        raise CompactTransactionError(f"unknown or duplicate stable record {record_id!r}")
    return selected[0]


def _apply_write(staged: dict[str, Any], write: Mapping[str, Any]) -> None:
    op = str(write["op"])
    path = str(write["path"])
    value = copy.deepcopy(write["value"])
    parts = path.removeprefix("/").split("/")
    if len(parts) == 1 and parts[0] in {
        "current_goal",
        "plan",
        "pending_restorations",
        "state_version",
        "evidence_versions",
    }:
        if op != "replace":
            raise CompactTransactionError("root projection requires replace")
        staged[parts[0]] = value
        return
    if len(parts) == 3 and parts[0] == "commitments" and parts[1] == "+":
        if op != "add" or not isinstance(value, Mapping) or value.get("id") != parts[2]:
            raise CompactTransactionError("commitment add is malformed")
        if any(row.get("id") == parts[2] for row in staged["commitments"]):
            raise CompactTransactionError("commitment add duplicates stable ID")
        staged["commitments"].append(value)
        return
    if len(parts) == 3 and parts[0] == "entities" and parts[1] == "+":
        if op != "add" or not isinstance(value, Mapping) or value.get("id") != parts[2]:
            raise CompactTransactionError("entity add is malformed")
        if any(row.get("id") == parts[2] for row in staged["entities"]):
            raise CompactTransactionError("entity add duplicates stable ID")
        staged["entities"].append(value)
        return
    if len(parts) == 3 and parts[0] == "commitments" and parts[1] != "+":
        if op != "replace":
            raise CompactTransactionError("commitment field update requires replace")
        record = _record_by_id(staged["commitments"], parts[1])
        if parts[2] not in record:
            raise CompactTransactionError("commitment field does not exist")
        record[parts[2]] = value
        return
    raise CompactTransactionError(f"compact write path is not allowed: {path}")


def execute_compact_transaction(
    proposal: Mapping[str, Any],
    state: Mapping[str, Any],
    event: Mapping[str, Any],
    validator: Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], str],
    *,
    staged_fault: str | None = None,
) -> CompactTransactionResult:
    caller_before = canonical_json(state)
    before = _without_history(state)
    started = time.perf_counter_ns()
    receipt = {
        "schema_version": "generic-compact-transaction-receipt-v1",
        "event_id": event.get("event_id"),
        "read_version": int(state["state_version"]),
        "before_sha256": stable_hash(before),
        "staged_sha256": None,
        "after_sha256": None,
        "changed_paths": [],
        "validator_calls": 0,
        "validator_passed": False,
        "published": False,
        "rolled_back": False,
        "rejection_class": None,
        "rejection_stage": None,
        "parse_materialize_ns": 0,
        "validate_ns": 0,
        "commit_ns": 0,
    }
    rejection_stage = "parser"
    try:
        parsed = parse_proposal(proposal, state, event)
        rejection_stage = "materializer"
        staged = copy.deepcopy(before)
        for write in parsed["writes"]:
            _apply_write(staged, write)
        if staged_fault == "drop_progress_ledger":
            staged["progress_ledger"] = []
        elif staged_fault == "retain_illegal_executing_action":
            staged["plan"] = copy.deepcopy(before["plan"])
        elif staged_fault is not None:
            raise CompactTransactionError(f"unknown staged fault {staged_fault!r}")
        receipt["changed_paths"] = [item["path"] for item in parsed["writes"]]
        receipt["staged_sha256"] = stable_hash(staged)
        receipt["parse_materialize_ns"] = time.perf_counter_ns() - started
        validate_started = time.perf_counter_ns()
        rejection_stage = "semantic_validator"
        receipt["validator_calls"] = 1
        directive = validator(staged, state, event)
        receipt["validate_ns"] = time.perf_counter_ns() - validate_started
        receipt["validator_passed"] = True
        commit_started = time.perf_counter_ns()
        post_state = copy.deepcopy(staged)
        receipt["after_sha256"] = stable_hash(post_state)
        receipt["published"] = True
        receipt["commit_ns"] = time.perf_counter_ns() - commit_started
    except Exception as exc:
        if not receipt["parse_materialize_ns"]:
            receipt["parse_materialize_ns"] = time.perf_counter_ns() - started
        receipt["rolled_back"] = True
        receipt["rejection_class"] = type(exc).__name__
        receipt["rejection_stage"] = rejection_stage
        if canonical_json(state) != caller_before:
            raise RuntimeError("compact transaction mutated caller state on rejection") from exc
        raise CompactTransactionRejected(str(exc), receipt) from exc
    if canonical_json(state) != caller_before:
        raise RuntimeError("compact transaction mutated caller state on success")
    return CompactTransactionResult(post_state, parsed, receipt, directive)
