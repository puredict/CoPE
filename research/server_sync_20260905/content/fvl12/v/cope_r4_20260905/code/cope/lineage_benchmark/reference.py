"""Independent dictionary-based reference for the registered R3/R4 events.

This evaluator intentionally does not import the typed patch executor, its
history helper, or the oracle patch generator. Sharing serialization records
does not share transition logic. Hand-derived trajectory tests also check the
reference so agreement alone is not treated as a proof of correctness.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from .models import LineageEvent, WorkflowState


def reference_transition(
    state: WorkflowState,
    event: LineageEvent,
    critical_logical_id: str,
) -> WorkflowState:
    """Apply the input event's prescribed semantics to a fresh deep dictionary.

    Used only to score a candidate or construct offline development references;
    never use this return value to repair a method's committed runtime state.
    Preconditions raise ValueError when a prior erroneous state makes the
    prescribed transition undefined.
    """
    document = deepcopy(state.to_dict())
    slots = {slot["slot_id"]: slot for slot in document["slots"]}
    current = slots.get(event.current_slot_id)
    if (
        current is None
        or current["kind"] != "workflow"
        or current["logical_id"] != critical_logical_id
    ):
        raise ValueError("reference event does not address the critical workflow")

    def record(slot: Dict[str, Any], operation: str, mode: str) -> None:
        slot["history"].append({
            "seq": len(slot["history"]) + 1,
            "event_id": event.event_id,
            "operation": operation,
            "mode_before": slot["mode"],
            "mode_after": mode,
            "detail": event.reason,
        })
        slot["mode"] = mode

    if event.kind == "suspend_current":
        if current["mode"] != "active":
            raise ValueError("reference suspend requires an active workflow")
        record(current, "Suspend", "suspended")
    elif event.kind == "restore_current":
        if current["mode"] != "suspended":
            raise ValueError("reference restore requires a suspended workflow")
        record(current, "Restore", "active")
    elif event.kind == "override_current":
        if current["mode"] not in {"active", "suspended"}:
            raise ValueError("reference override requires a live workflow")
        child_data = deepcopy(event.new_slot)
        if not isinstance(child_data, dict):
            raise ValueError("reference override requires a new slot")
        child_id = child_data["slot_id"]
        if child_id in slots:
            raise ValueError("reference override occurrence already exists")
        current["lineage"]["child_ids"].append(child_id)
        record(current, "Override", "overridden")
        child = {
            "slot_id": child_id,
            "logical_id": child_data["logical_id"],
            "kind": "workflow",
            "mode": "active",
            "priority": child_data["priority"],
            "grounding": child_data["grounding"],
            "payload": child_data["payload"],
            "lineage": {
                "parent_id": current["slot_id"],
                "root_id": current["lineage"]["root_id"],
                "depth": current["lineage"]["depth"] + 1,
                "child_ids": [],
            },
            "history": [],
        }
        record(child, "InsertOverride", "active")
        slots[child_id] = child
    elif event.kind == "restore_root":
        cursor = current
        visited = set()
        while cursor["lineage"]["parent_id"] is not None:
            if cursor["slot_id"] in visited:
                raise ValueError("reference lineage contains a cycle")
            visited.add(cursor["slot_id"])
            if cursor["mode"] != "expired":
                record(cursor, "ExpireDetour", "expired")
            parent_id = cursor["lineage"]["parent_id"]
            if parent_id not in slots:
                raise ValueError("reference lineage contains a missing parent")
            cursor = slots[parent_id]
        if cursor["slot_id"] != current["lineage"]["root_id"]:
            raise ValueError("reference lineage root_id disagrees with parent chain")
        record(cursor, "RestoreRoot", "active")
    else:
        raise ValueError(f"unsupported reference event kind {event.kind!r}")

    document["revision"] += 1
    document["slots"] = [slots[key] for key in sorted(slots)]
    return WorkflowState.from_dict(document)
