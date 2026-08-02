from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from cope.types import canonical_json, stable_hash


class TxExecError(ValueError):
    pass


class TransactionRejected(TxExecError):
    def __init__(self, message: str, receipt: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.receipt = copy.deepcopy(dict(receipt))


@dataclass(frozen=True)
class TransactionResult:
    post_state: dict[str, Any]
    carrier: dict[str, Any]
    receipt: dict[str, Any]
    directive: str


def _without_history(state: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in state.items() if key != "action_history"}


def _record(record_id: str, target: str, status: str = "active") -> dict[str, Any]:
    return {
        "id": record_id,
        "predicate": "deliver",
        "grounding": [target, "dock"],
        "lifecycle_status": status,
        "source": "task_owner",
        "owner": "task_owner",
        "authority": 100,
        "valid_from": "genesis",
        "valid_until": "task_end",
        "dependencies": [],
        "support_links": [],
        "override_links": [],
        "supersession_links": [],
    }


def _authorized(state: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
    return bool(
        event.get("issuer") == "task_owner"
        and int(event.get("authority", -1)) >= 100
        and int(event.get("input_state_version", -1)) == int(state["state_version"])
        and event.get("duplicate_delivery") is not True
    )


class _StagingTransaction:
    def __init__(self, state: Mapping[str, Any], event: Mapping[str, Any]) -> None:
        self.before = _without_history(state)
        self.staged = copy.deepcopy(self.before)
        self.event = copy.deepcopy(dict(event))
        self.writes: list[dict[str, Any]] = []

    def write(self, address: str, before: Any, after: Any) -> None:
        self.writes.append(
            {
                "address": address,
                "before_sha256": stable_hash(before),
                "after_sha256": stable_hash(after),
                "value": copy.deepcopy(after),
            }
        )

    def replace_projection(self, name: str, value: Any) -> None:
        before = copy.deepcopy(self.staged[name])
        self.staged[name] = copy.deepcopy(value)
        self.write(f"/{name}", before, value)

    def update_record(self, record_id: str, field: str, value: Any) -> None:
        item = next((row for row in self.staged["commitments"] if row["id"] == record_id), None)
        if item is None:
            raise TxExecError(f"unknown record {record_id!r}")
        before = copy.deepcopy(item[field])
        item[field] = copy.deepcopy(value)
        self.write(f"/commitments/{record_id}/{field}", before, value)

    def insert_record(self, record: Mapping[str, Any]) -> None:
        if any(row["id"] == record["id"] for row in self.staged["commitments"]):
            raise TxExecError(f"duplicate record {record['id']!r}")
        self.staged["commitments"].append(copy.deepcopy(dict(record)))
        self.write(f"/commitments/+/{record['id']}", None, record)

    def insert_entity_if_missing(self, entity_id: str, kind: str) -> None:
        if any(row["id"] == entity_id for row in self.staged["entities"]):
            return
        entity = {"id": entity_id, "kind": kind}
        self.staged["entities"].append(entity)
        self.write(f"/entities/+/{entity_id}", None, entity)

    def finalize_evidence(self) -> None:
        version = int(self.staged["state_version"]) + 1
        evidence = {
            "event_id": self.event["event_id"],
            "world_version": self.event["world_version"],
            "input_state_version": self.event["input_state_version"],
        }
        self.replace_projection("state_version", version)
        self.replace_projection("evidence_versions", evidence)

    def apply_event(self) -> str:
        if not _authorized(self.before, self.event):
            return "authorization_or_version_noop"
        kind = str(self.event["event_type"])
        if kind == "no_op":
            return "authorized_noop"
        if kind == "cancel_commitment":
            self.update_record(self.event["target_id"], "lifecycle_status", "cancelled")
            self.replace_projection(
                "current_goal",
                {"all": [{"predicate": "deliver", "arguments": ["package_a", "dock"]}]},
            )
            self.replace_projection("plan", [])
        elif kind == "replace_commitment":
            self.update_record(self.event["target_id"], "lifecycle_status", "superseded")
            grounding = list(self.event["replacement_grounding"])
            replacement = _record(self.event["replacement_id"], grounding[0])
            replacement["grounding"] = grounding
            replacement["valid_from"] = self.event["event_id"]
            replacement["supersession_links"] = [self.event["target_id"]]
            self.insert_record(replacement)
            self.insert_entity_if_missing(grounding[0], "object")
            self.replace_projection(
                "current_goal",
                {
                    "all": [
                        {"predicate": "deliver", "arguments": ["package_a", "dock"]},
                        {"predicate": "deliver", "arguments": grounding},
                    ]
                },
            )
            self.replace_projection(
                "plan",
                [
                    {
                        "action_id": "place-c",
                        "skill": "place",
                        "arguments": grounding,
                        "status": "pending",
                        "cancellation_reason": None,
                    }
                ],
            )
        elif kind == "activate_override":
            target_id = str(self.event["target_id"])
            override_id = str(self.event["override_id"])
            self.update_record(target_id, "lifecycle_status", "suspended")
            override = _record(override_id, "package_b")
            override["predicate"] = "prohibit_touch"
            override["valid_from"] = self.event["event_id"]
            override["override_links"] = [target_id]
            self.insert_record(override)
            self.replace_projection(
                "current_goal",
                {
                    "all": [
                        {"predicate": "deliver", "arguments": ["package_a", "dock"]},
                        {"predicate": "prohibit_touch", "arguments": ["package_b", "dock"]},
                    ]
                },
            )
            self.replace_projection(
                "pending_restorations", [{"target_id": target_id, "override_id": override_id}]
            )
            if self.event.get("conflicts_with_action"):
                plan = copy.deepcopy(self.staged["plan"])
                for action in plan:
                    if action["status"] == "executing":
                        action["status"] = "cancelled"
                        action["cancellation_reason"] = self.event["cancellation_reason"]
                self.replace_projection("plan", plan)
            else:
                self.replace_projection("plan", [])
        elif kind == "release_override":
            override_id = str(self.event["override_id"])
            target_id = str(self.event["target_id"])
            self.update_record(override_id, "lifecycle_status", "expired")
            self.update_record(target_id, "lifecycle_status", "active")
            grounding = self.event.get("world_facts", {}).get("deliver:b:grounding")
            if grounding:
                grounding = list(grounding)
                self.update_record(target_id, "grounding", grounding)
                self.insert_entity_if_missing(grounding[1], "region")
            else:
                target = next(row for row in self.staged["commitments"] if row["id"] == target_id)
                grounding = list(target["grounding"])
            self.replace_projection(
                "current_goal",
                {
                    "all": [
                        {"predicate": "deliver", "arguments": ["package_a", "dock"]},
                        {"predicate": "deliver", "arguments": grounding},
                    ]
                },
            )
            self.replace_projection("pending_restorations", [])
            self.replace_projection(
                "plan",
                [
                    {
                        "action_id": "place-b",
                        "skill": "place",
                        "arguments": grounding,
                        "status": "pending",
                        "cancellation_reason": None,
                    }
                ],
            )
        elif kind == "irrelevant_world_change":
            pass
        else:
            raise TxExecError(f"unsupported event type {kind!r}")
        self.finalize_evidence()
        return "staged_write"

    def inject_fault(self, fault_id: str) -> None:
        by_id = {row["id"]: row for row in self.staged["commitments"]}
        if fault_id == "F01":
            by_id["deliver:a"]["lifecycle_status"] = "cancelled"
        elif fault_id == "F02":
            self.staged["progress_ledger"] = []
        elif fault_id in {"F03", "F04"}:
            by_id["deliver:b"]["lifecycle_status"] = "cancelled"
            self.staged["plan"] = []
        elif fault_id == "F05":
            by_id["deliver:c"]["grounding"] = ["package_z", "dock"]
        elif fault_id == "F06":
            self.staged["pending_restorations"] = copy.deepcopy(self.before["pending_restorations"])
        elif fault_id == "F07":
            self.staged["plan"] = copy.deepcopy(self.before["plan"])
        elif fault_id == "F08":
            return
        else:
            raise TxExecError(f"unknown fault {fault_id!r}")
        self.write(f"/__fault__/{fault_id}", None, "injected_before_validation")


def execute_transaction(
    state: Mapping[str, Any],
    event: Mapping[str, Any],
    validator: Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], str],
    *,
    fault_id: str | None = None,
) -> TransactionResult:
    caller_before = canonical_json(state)
    started = time.perf_counter_ns()
    tx = _StagingTransaction(state, event)
    decision = tx.apply_event()
    if fault_id:
        tx.inject_fault(fault_id)
    staged_at = time.perf_counter_ns()
    before_hash = stable_hash(tx.before)
    staged_hash = stable_hash(tx.staged)
    carrier = {
        "schema_version": "generic-transaction-carrier-v1",
        "event_id": event["event_id"],
        "base_version": int(state["state_version"]),
        "writes": copy.deepcopy(tx.writes),
    }
    receipt = {
        "schema_version": "generic-transaction-receipt-v1",
        "event_id": event["event_id"],
        "actor": event.get("issuer"),
        "authority": event.get("authority"),
        "read_version": int(state["state_version"]),
        "proposed_version": int(tx.staged["state_version"]),
        "decision": decision,
        "changed_addresses": [row["address"] for row in tx.writes],
        "before_sha256": before_hash,
        "staged_sha256": staged_hash,
        "after_sha256": None,
        "validator_calls": 0,
        "validator_passed": False,
        "published": False,
        "rolled_back": False,
        "fault_id": fault_id,
        "stage_ns": staged_at - started,
        "validate_ns": 0,
        "commit_ns": 0,
    }
    validate_started = time.perf_counter_ns()
    try:
        if fault_id == "F08":
            raise RuntimeError("forced validator exception")
        receipt["validator_calls"] = 1
        directive = validator(tx.staged, state, event)
        receipt["validator_passed"] = True
    except Exception as exc:
        receipt["validate_ns"] = time.perf_counter_ns() - validate_started
        receipt["rolled_back"] = True
        receipt["rejection_class"] = type(exc).__name__
        receipt["rejection_message"] = str(exc)
        if canonical_json(state) != caller_before:
            raise RuntimeError("caller-visible pre-state mutated during rejected transaction") from exc
        raise TransactionRejected(str(exc), receipt) from exc
    receipt["validate_ns"] = time.perf_counter_ns() - validate_started
    commit_started = time.perf_counter_ns()
    post_state = copy.deepcopy(tx.staged)
    receipt["after_sha256"] = stable_hash(post_state)
    receipt["published"] = True
    receipt["commit_ns"] = time.perf_counter_ns() - commit_started
    if canonical_json(state) != caller_before:
        raise RuntimeError("caller-visible pre-state mutated during commit")
    return TransactionResult(post_state, carrier, receipt, directive)

