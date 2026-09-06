"""Persistent lineage state transitions and independent validators."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .models import (
    PATCH_SCHEMA,
    STATE_SCHEMA,
    VALID_KINDS,
    VALID_MODES,
    LineageEvent,
    WorkflowSlot,
    WorkflowState,
    canonical_json,
)
from .operations import validate_operation


class StateValidationError(ValueError):
    pass


def _append_history(
    slot: WorkflowSlot,
    event: LineageEvent,
    operation: str,
    mode_after: str,
    detail: str,
) -> WorkflowSlot:
    entry = {
        "seq": len(slot.history) + 1,
        "event_id": event.event_id,
        "operation": operation,
        "mode_before": slot.mode,
        "mode_after": mode_after,
        "detail": detail,
    }
    return replace(slot, mode=mode_after, history=slot.history + (entry,))


def _lineage_fields(raw: Mapping[str, Any]) -> Tuple[Any, str, int, List[str]]:
    required = {"parent_id", "root_id", "depth", "child_ids"}
    missing = sorted(required - set(raw))
    extra = sorted(set(raw) - required)
    if missing or extra:
        raise StateValidationError(
            f"lineage fields missing={missing} extra={extra}"
        )
    parent = raw["parent_id"]
    if parent is not None and not isinstance(parent, str):
        raise StateValidationError("lineage.parent_id must be string or null")
    if not isinstance(raw["root_id"], str):
        raise StateValidationError("lineage.root_id must be a string")
    if not isinstance(raw["depth"], int) or raw["depth"] < 0:
        raise StateValidationError("lineage.depth must be a non-negative integer")
    if not isinstance(raw["child_ids"], list) or not all(
        isinstance(item, str) for item in raw["child_ids"]
    ):
        raise StateValidationError("lineage.child_ids must be an array of strings")
    if len(set(raw["child_ids"])) != len(raw["child_ids"]):
        raise StateValidationError("lineage.child_ids contains duplicates")
    return parent, raw["root_id"], raw["depth"], list(raw["child_ids"])


def validate_state(state: WorkflowState, critical_logical_id: str) -> List[str]:
    errors: List[str] = []
    if state.schema_version != STATE_SCHEMA:
        errors.append(f"wrong schema_version {state.schema_version!r}")
    if state.revision < 0:
        errors.append("negative revision")
    for slot in state.slots.values():
        if not slot.slot_id:
            errors.append("empty slot_id")
        if slot.kind not in VALID_KINDS:
            errors.append(f"{slot.slot_id}: invalid kind {slot.kind!r}")
        if slot.mode not in VALID_MODES:
            errors.append(f"{slot.slot_id}: invalid mode {slot.mode!r}")
        if slot.priority not in {"hard", "soft"}:
            errors.append(f"{slot.slot_id}: invalid priority {slot.priority!r}")
        try:
            parent, root_id, depth, children = _lineage_fields(slot.lineage)
        except StateValidationError as exc:
            errors.append(f"{slot.slot_id}: {exc}")
            continue
        if root_id not in state.slots:
            errors.append(f"{slot.slot_id}: missing root {root_id!r}")
        if parent is None:
            if root_id != slot.slot_id or depth != 0:
                errors.append(f"{slot.slot_id}: malformed root lineage")
        else:
            ancestor = state.slots.get(parent)
            if ancestor is None:
                errors.append(f"{slot.slot_id}: missing parent {parent!r}")
            else:
                if slot.slot_id not in ancestor.lineage.get("child_ids", []):
                    errors.append(f"{slot.slot_id}: parent lacks inverse child edge")
                if ancestor.lineage.get("root_id") != root_id:
                    errors.append(f"{slot.slot_id}: root differs from parent root")
                if ancestor.lineage.get("depth") != depth - 1:
                    errors.append(f"{slot.slot_id}: depth differs from parent depth + 1")
        for child_id in children:
            child = state.slots.get(child_id)
            if child is None:
                errors.append(f"{slot.slot_id}: missing child {child_id!r}")
            elif child.lineage.get("parent_id") != slot.slot_id:
                errors.append(f"{slot.slot_id}: child {child_id!r} lacks inverse parent edge")
        seqs = [entry.get("seq") for entry in slot.history]
        if seqs != list(range(1, len(seqs) + 1)):
            errors.append(f"{slot.slot_id}: history sequence is not contiguous")
        history_fields = {
            "seq", "event_id", "operation", "mode_before", "mode_after", "detail"
        }
        for index, entry in enumerate(slot.history):
            if set(entry) != history_fields:
                errors.append(
                    f"{slot.slot_id}: history[{index}] fields differ from schema"
                )
            if entry.get("mode_after") not in VALID_MODES:
                errors.append(
                    f"{slot.slot_id}: history[{index}] has invalid mode_after"
                )
            if entry.get("mode_before") is not None and entry.get("mode_before") not in VALID_MODES:
                errors.append(
                    f"{slot.slot_id}: history[{index}] has invalid mode_before"
                )

    critical = [
        slot for slot in state.slots.values()
        if slot.logical_id == critical_logical_id and slot.kind == "workflow"
    ]
    carriers = [slot for slot in critical if slot.mode in {"active", "suspended"}]
    if len(carriers) != 1:
        errors.append(
            f"critical workflow must have exactly one live carrier, got {len(carriers)}"
        )
    return errors


def _parse_patch(raw: Mapping[str, Any], event: LineageEvent, revision: int) -> List[Dict[str, Any]]:
    required = {"schema_version", "event_id", "base_revision", "ops"}
    missing = sorted(required - set(raw))
    extra = sorted(set(raw) - required)
    if missing or extra:
        raise StateValidationError(f"patch fields missing={missing} extra={extra}")
    if raw["schema_version"] != PATCH_SCHEMA:
        raise StateValidationError(f"wrong patch schema {raw['schema_version']!r}")
    if raw["event_id"] != event.event_id:
        raise StateValidationError("patch event_id does not match input event")
    if raw["base_revision"] != revision:
        raise StateValidationError("patch base_revision is stale")
    if not isinstance(raw["ops"], list):
        raise StateValidationError("patch.ops must be an array")
    if not all(isinstance(item, Mapping) for item in raw["ops"]):
        raise StateValidationError("every patch operation must be an object")
    for item in raw["ops"]:
        try:
            validate_operation(item)
        except ValueError as exc:
            raise StateValidationError(str(exc)) from exc
    return deepcopy([dict(item) for item in raw["ops"]])


def apply_patch_document(
    state: WorkflowState,
    raw: Mapping[str, Any],
    event: LineageEvent,
    critical_logical_id: str,
) -> WorkflowState:
    """Apply model-selected typed operations to the persistent state.

    Lineage bookkeeping and lifecycle history are framework-owned. The model
    chooses only the operation and target; this is the architectural behavior
    CoPE claims as its advantage.
    """

    ops = _parse_patch(raw, event, state.revision)
    # Frozen records still contain mutable nested dictionaries. A transaction
    # owns a deep snapshot so both failed and successful updates cannot leak
    # mutations into the caller's prior state or model output document.
    slots = deepcopy(state.slots)
    for op in ops:
        name = op.get("op")
        if name == "suspend":
            sid = str(op["slot_id"])
            slot = slots.get(sid)
            if slot is None or slot.kind != "workflow" or slot.mode != "active":
                raise StateValidationError(f"cannot suspend {sid!r} from its current mode")
            slots[sid] = _append_history(slot, event, "Suspend", "suspended", event.reason)
        elif name == "restore":
            sid = str(op["slot_id"])
            slot = slots.get(sid)
            if slot is None or slot.kind != "workflow" or slot.mode != "suspended":
                raise StateValidationError(f"cannot restore {sid!r} from its current mode")
            slots[sid] = _append_history(slot, event, "Restore", "active", event.reason)
        elif name == "override":
            sid = str(op["slot_id"])
            old = slots.get(sid)
            if old is None or old.kind != "workflow" or old.mode not in {"active", "suspended"}:
                raise StateValidationError(f"cannot override {sid!r} from its current mode")
            new_raw = op["new_slot"]
            new_id = str(new_raw["slot_id"])
            if new_id in slots:
                raise StateValidationError(f"override slot {new_id!r} already exists")
            old_children = list(old.lineage["child_ids"])
            old_children.append(new_id)
            old_with_edge = replace(
                old, lineage={**old.lineage, "child_ids": old_children}
            )
            slots[sid] = _append_history(
                old_with_edge, event, "Override", "overridden", event.reason
            )
            new_slot = WorkflowSlot(
                slot_id=new_id,
                logical_id=str(new_raw["logical_id"]),
                kind="workflow",
                mode="active",
                priority=str(new_raw["priority"]),
                grounding=str(new_raw["grounding"]),
                payload=dict(new_raw["payload"]),
                lineage={
                    "parent_id": sid,
                    "root_id": old.lineage["root_id"],
                    "depth": int(old.lineage["depth"]) + 1,
                    "child_ids": [],
                },
                history=(),
            )
            slots[new_id] = _append_history(
                new_slot, event, "InsertOverride", "active", event.reason
            )
        elif name == "restore_root":
            sid = str(op["from_slot_id"])
            current = slots.get(sid)
            if current is None or current.kind != "workflow":
                raise StateValidationError(f"unknown workflow {sid!r}")
            path: List[str] = []
            seen = set()
            cursor = current
            while cursor.lineage["parent_id"] is not None:
                if cursor.slot_id in seen:
                    raise StateValidationError("cycle while traversing root lineage")
                seen.add(cursor.slot_id)
                path.append(cursor.slot_id)
                cursor = slots[cursor.lineage["parent_id"]]
            for descendant_id in path:
                descendant = slots[descendant_id]
                if descendant.mode != "expired":
                    slots[descendant_id] = _append_history(
                        descendant, event, "ExpireDetour", "expired", event.reason
                    )
            root = slots[cursor.slot_id]
            slots[root.slot_id] = _append_history(
                root, event, "RestoreRoot", "active", event.reason
            )
        else:
            raise StateValidationError(f"unsupported patch operation {name!r}")

    candidate = WorkflowState(revision=state.revision + 1, slots=slots)
    errors = validate_state(candidate, critical_logical_id)
    if errors:
        raise StateValidationError("; ".join(errors))
    return candidate


def validate_regenerated_transition(
    previous: WorkflowState,
    candidate: WorkflowState,
    event: LineageEvent,
    critical_logical_id: str,
) -> List[str]:
    """Validate a complete model-emitted replacement without an oracle answer.

    The validator checks schema/lifecycle preservation and graph consistency,
    but intentionally does not require the event's *correct* semantic answer.
    A coherent yet wrong regeneration remains executable and fails the actual
    task, which keeps task completion separate from syntax validation.
    """

    errors = validate_state(candidate, critical_logical_id)
    if candidate.revision != previous.revision + 1:
        errors.append(
            f"revision {candidate.revision} != expected {previous.revision + 1}"
        )
    expected_ids = set(previous.slots)
    if event.kind == "override_current" and event.new_slot is not None:
        expected_ids.add(str(event.new_slot["slot_id"]))
    if set(candidate.slots) != expected_ids:
        errors.append(
            "full state must emit exactly every prior slot plus the registered new slot"
        )

    for sid, old in previous.slots.items():
        new = candidate.slots.get(sid)
        if new is None:
            continue
        if new.history[: len(old.history)] != old.history:
            errors.append(f"{sid}: lifecycle history prefix was lost or rewritten")
        immutable = ("slot_id", "logical_id", "kind", "priority", "grounding", "payload")
        if old.kind in {"order_archive", "safety"}:
            old_dict, new_dict = old.to_dict(), new.to_dict()
            if any(old_dict[key] != new_dict[key] for key in immutable):
                errors.append(f"{sid}: immutable archived/safety content changed")
            if old.mode != new.mode or old.lineage != new.lineage or old.history != new.history:
                errors.append(f"{sid}: untouched archived/safety state changed")

    touched = [
        slot for slot in candidate.slots.values()
        if slot.history and slot.history[-1].get("event_id") == event.event_id
    ]
    if not touched:
        errors.append("no lifecycle record refers to the current event")
    return sorted(set(errors))


def state_semantic_match(candidate: WorkflowState, oracle: WorkflowState) -> bool:
    return canonical_json(candidate.to_dict()) == canonical_json(oracle.to_dict())


def active_plan(
    state: WorkflowState,
    critical_logical_id: str,
    completed_actions: Sequence[Mapping[str, Any]] = (),
) -> List[Dict[str, str]]:
    """Compile the active plan after an optional exact completed-action prefix.

    Completion records must contain the same object, target and role as the
    corresponding initial actions. An object name alone is not proof that an
    action for the restored occurrence was completed. Conflicting or reordered
    records fail closed instead of silently dropping actions. This supports
    unit-level partial-completion checks; the current physical runner does not
    yet interrupt execution and supply a nonempty completion ledger.
    """
    active = [
        slot for slot in state.slots.values()
        if slot.logical_id == critical_logical_id
        and slot.kind == "workflow"
        and slot.mode == "active"
    ]
    if len(active) != 1:
        raise StateValidationError(f"expected one active critical workflow, got {len(active)}")
    raw_plan = active[0].payload.get("plan")
    if not isinstance(raw_plan, list):
        raise StateValidationError("active workflow payload has no plan array")
    plan: List[Dict[str, str]] = []
    for index, action in enumerate(raw_plan):
        if not isinstance(action, Mapping) or set(action) != {"object", "target", "role"}:
            raise StateValidationError(f"plan action {index} has invalid fields")
        plan.append({key: str(action[key]) for key in ("object", "target", "role")})
    if sorted(action["object"] for action in plan) != ["butter", "milk", "yogurt"]:
        raise StateValidationError("plan must place butter, milk, and yogurt exactly once")
    if any(action["target"] not in {"basket_A", "basket_B", "basket_C"} for action in plan):
        raise StateValidationError("plan contains an unknown basket")
    completed = list(completed_actions)
    if any(
        not isinstance(action, Mapping)
        or set(action) != {"object", "target", "role"}
        for action in completed
    ):
        raise StateValidationError("completed actions must have object,target,role fields")
    if len(completed) > len(plan) or completed != plan[: len(completed)]:
        raise StateValidationError("completed actions are not an exact prefix of the active plan")
    return plan[len(completed) :]
