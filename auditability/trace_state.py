from __future__ import annotations

import copy
from typing import Any

from auditability.common import content_hash


def canonical_slots(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for slot in slots:
        cleaned.append(
            {
                key: copy.deepcopy(value)
                for key, value in slot.items()
                if key not in {"state_hash", "recorded_hash", "policy_step"}
            }
        )
    return sorted(cleaned, key=lambda row: str(row.get("id", "")))


def state_hash(slots_or_state: list[dict[str, Any]] | dict[str, Any]) -> str:
    if isinstance(slots_or_state, dict):
        slots = slots_or_state.get("slots", [])
    else:
        slots = slots_or_state
    if not isinstance(slots, list):
        raise ValueError("state slots must be a list")
    return content_hash(canonical_slots(slots))


def replay_patch(
    before_slots: list[dict[str, Any]], patch: dict[str, Any]
) -> list[dict[str, Any]]:
    slots = copy.deepcopy(before_slots)
    op = str(patch.get("op") or patch.get("operation") or "").lower()
    target = patch.get("target_slot_id") or patch.get("slot_id")
    changes = copy.deepcopy(patch.get("changes", {}))
    if op == "add":
        added = copy.deepcopy(patch.get("slot") or patch.get("after_slot"))
        if not isinstance(added, dict):
            raise ValueError("add patch requires slot/after_slot")
        slots.append(added)
        return slots
    index = next(
        (position for position, slot in enumerate(slots) if slot.get("id") == target),
        None,
    )
    if index is None:
        raise KeyError(f"target slot does not exist: {target}")
    if op in {"remove", "delete"}:
        del slots[index]
        return slots
    default_status = {
        "override": "overridden",
        "suspend": "suspended",
        "expire": "expired",
        "restore": "active",
    }.get(op)
    if default_status is not None:
        changes.setdefault("status", default_status)
    if op not in {"override", "suspend", "expire", "restore", "update"}:
        raise ValueError(f"unsupported patch operation: {op}")
    slots[index].update(changes)
    return slots
