from __future__ import annotations

import copy
from typing import Any, Mapping

from cope.types import canonical_json


PATCH_SCHEMA = "cope-typed-minimum-patch-v1"


class GenericTypedInterpreterError(ValueError):
    pass


def _state_without_history(state: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in state.items() if key != "action_history"}


def _one(rows: list[dict[str, Any]], record_id: str, kind: str) -> dict[str, Any]:
    selected = [row for row in rows if row.get("id") == record_id]
    if len(selected) != 1:
        raise GenericTypedInterpreterError(f"{kind} stable ID is unknown or duplicated: {record_id!r}")
    return selected[0]


def _remove_goal_atom(state: dict[str, Any], predicate: str, grounding: list[str]) -> None:
    atoms = state["current_goal"]["all"]
    matches = [
        index for index, atom in enumerate(atoms)
        if atom.get("predicate") == predicate and atom.get("arguments") == grounding
    ]
    if len(matches) != 1:
        raise GenericTypedInterpreterError("target goal atom is unknown or duplicated")
    del atoms[matches[0]]


def _append_goal_atom(state: dict[str, Any], predicate: str, grounding: list[str]) -> None:
    atom = {"predicate": predicate, "arguments": list(grounding)}
    if atom in state["current_goal"]["all"]:
        raise GenericTypedInterpreterError("new goal atom already exists")
    state["current_goal"]["all"].append(atom)


def _authorized(state: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
    return bool(
        event.get("issuer") == "task_owner"
        and int(event.get("authority", -1)) >= 100
        and int(event.get("input_state_version", -1)) == int(state["state_version"])
        and event.get("duplicate_delivery") is not True
    )


def _validate_operation(operation: Any, event: Mapping[str, Any]) -> str:
    if not isinstance(operation, Mapping) or not isinstance(operation.get("op"), str):
        raise GenericTypedInterpreterError("typed operation must be an object with an operation name")
    name = operation["op"]
    fields = {
        "cancel_commitment": {"op", "target_id"},
        "replace_commitment": {"op", "target_id", "replacement_id"},
        "activate_override": {"op", "target_id", "override_id"},
        "release_override": {"op", "target_id", "override_id"},
        "cancel_executing_action": {"op", "action_id"},
        "acknowledge_event": {"op"},
    }
    if name not in fields or set(operation) != fields[name]:
        raise GenericTypedInterpreterError("typed operation fields are unsupported or noncanonical")

    event_type = event.get("event_type")
    allowed = {
        "cancel_commitment": {"cancel_commitment"},
        "replace_commitment": {"replace_commitment"},
        "activate_override": {"activate_override", "cancel_executing_action"},
        "release_override": {"release_override"},
        "irrelevant_world_change": {"acknowledge_event"},
        "no_op": set(),
    }
    if event_type not in allowed or name not in allowed[event_type]:
        raise GenericTypedInterpreterError("operation type is not licensed by this event type")
    if "target_id" in operation and operation["target_id"] != event.get("target_id"):
        raise GenericTypedInterpreterError("operation target does not match the event target")
    if "replacement_id" in operation and operation["replacement_id"] != event.get("replacement_id"):
        raise GenericTypedInterpreterError("replacement stable ID does not match the event")
    if "override_id" in operation and operation["override_id"] != event.get("override_id"):
        raise GenericTypedInterpreterError("override stable ID does not match the event")
    if name == "cancel_executing_action" and not event.get("conflicts_with_action"):
        raise GenericTypedInterpreterError("action cancellation lacks an event conflict")
    return name


def _apply_cancel(state: dict[str, Any], operation: Mapping[str, Any]) -> None:
    target = _one(state["commitments"], str(operation["target_id"]), "commitment")
    if target.get("lifecycle_status") != "active":
        raise GenericTypedInterpreterError("only an active commitment may be cancelled")
    target["lifecycle_status"] = "cancelled"
    _remove_goal_atom(state, str(target["predicate"]), list(target["grounding"]))
    state["plan"] = []


def _apply_replace(state: dict[str, Any], operation: Mapping[str, Any], event: Mapping[str, Any]) -> None:
    target = _one(state["commitments"], str(operation["target_id"]), "commitment")
    if target.get("lifecycle_status") != "active":
        raise GenericTypedInterpreterError("only an active commitment may be superseded")
    replacement_id = str(operation["replacement_id"])
    if any(row.get("id") == replacement_id for row in state["commitments"]):
        raise GenericTypedInterpreterError("replacement stable ID already exists")
    grounding = event.get("replacement_grounding")
    if not isinstance(grounding, list) or len(grounding) != 2:
        raise GenericTypedInterpreterError("replacement grounding is missing or malformed")
    old_grounding = list(target["grounding"])
    target["lifecycle_status"] = "superseded"
    replacement = copy.deepcopy(target)
    replacement.update({
        "id": replacement_id,
        "predicate": "deliver",
        "grounding": list(grounding),
        "lifecycle_status": "active",
        "valid_from": event["event_id"],
        "override_links": [],
        "supersession_links": [operation["target_id"]],
    })
    state["commitments"].append(replacement)
    entity_id = grounding[0]
    if not any(row.get("id") == entity_id for row in state["entities"]):
        state["entities"].append({"id": entity_id, "kind": "object"})
    _remove_goal_atom(state, "deliver", old_grounding)
    _append_goal_atom(state, "deliver", list(grounding))
    state["plan"] = [{
        "action_id": "place-c",
        "skill": "place",
        "arguments": list(grounding),
        "status": "pending",
        "cancellation_reason": None,
    }]


def _apply_activate(state: dict[str, Any], operation: Mapping[str, Any], event: Mapping[str, Any]) -> None:
    target = _one(state["commitments"], str(operation["target_id"]), "commitment")
    if target.get("lifecycle_status") != "active":
        raise GenericTypedInterpreterError("only an active commitment may be suspended")
    override_id = str(operation["override_id"])
    if any(row.get("id") == override_id for row in state["commitments"]):
        raise GenericTypedInterpreterError("override stable ID already exists")
    grounding = list(target["grounding"])
    target["lifecycle_status"] = "suspended"
    override = copy.deepcopy(target)
    override.update({
        "id": override_id,
        "predicate": "prohibit_touch",
        "lifecycle_status": "active",
        "valid_from": event["event_id"],
        "override_links": [operation["target_id"]],
        "supersession_links": [],
    })
    state["commitments"].append(override)
    _remove_goal_atom(state, "deliver", grounding)
    _append_goal_atom(state, "prohibit_touch", grounding)
    state["pending_restorations"].append({
        "target_id": operation["target_id"],
        "override_id": override_id,
    })
    if not event.get("conflicts_with_action"):
        state["plan"] = []


def _apply_cancel_action(state: dict[str, Any], operation: Mapping[str, Any], event: Mapping[str, Any]) -> None:
    action_id = str(operation["action_id"])
    selected = [row for row in state["plan"] if row.get("action_id") == action_id]
    if len(selected) != 1 or selected[0].get("status") != "executing":
        raise GenericTypedInterpreterError("action cancellation target is not uniquely executing")
    if not any(
        row.get("override_id") == event.get("override_id")
        for row in state["pending_restorations"]
    ):
        raise GenericTypedInterpreterError("action cancellation requires an applied conflicting override")
    reason = event.get("cancellation_reason")
    if not isinstance(reason, str) or not reason:
        raise GenericTypedInterpreterError("action cancellation reason is missing")
    selected[0]["status"] = "cancelled"
    selected[0]["cancellation_reason"] = reason


def _apply_release(state: dict[str, Any], operation: Mapping[str, Any], event: Mapping[str, Any]) -> None:
    target = _one(state["commitments"], str(operation["target_id"]), "commitment")
    override = _one(state["commitments"], str(operation["override_id"]), "override")
    if target.get("lifecycle_status") != "suspended" or override.get("lifecycle_status") != "active":
        raise GenericTypedInterpreterError("release lifecycle preconditions do not hold")
    if operation["target_id"] not in override.get("override_links", []):
        raise GenericTypedInterpreterError("override does not protect the requested target")
    old_override_grounding = list(override["grounding"])
    override["lifecycle_status"] = "expired"
    target["lifecycle_status"] = "active"
    grounding = event.get("world_facts", {}).get("deliver:b:grounding")
    if grounding is not None:
        if not isinstance(grounding, list) or len(grounding) != 2:
            raise GenericTypedInterpreterError("released grounding is malformed")
        target["grounding"] = list(grounding)
        region_id = grounding[1]
        if not any(row.get("id") == region_id for row in state["entities"]):
            state["entities"].append({"id": region_id, "kind": "region"})
    _remove_goal_atom(state, "prohibit_touch", old_override_grounding)
    _append_goal_atom(state, "deliver", list(target["grounding"]))
    restoration = {"target_id": operation["target_id"], "override_id": operation["override_id"]}
    if state["pending_restorations"].count(restoration) != 1:
        raise GenericTypedInterpreterError("release restoration record is unknown or duplicated")
    state["pending_restorations"].remove(restoration)
    state["plan"] = [{
        "action_id": "place-b",
        "skill": "place",
        "arguments": list(target["grounding"]),
        "status": "pending",
        "cancellation_reason": None,
    }]


def apply_generic_typed_patch(
    patch: Mapping[str, Any], state: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Any]:
    caller_before = canonical_json(state)
    required = {"schema_version", "input_state_version", "event_id", "operations"}
    if not isinstance(patch, Mapping) or set(patch) != required or patch.get("schema_version") != PATCH_SCHEMA:
        raise GenericTypedInterpreterError("typed patch fields or schema are noncanonical")
    if int(patch.get("input_state_version", -1)) != int(state["state_version"]):
        raise GenericTypedInterpreterError("typed patch input version mismatch")
    if patch.get("event_id") != event.get("event_id"):
        raise GenericTypedInterpreterError("typed patch event ID mismatch")
    operations = patch.get("operations")
    if not isinstance(operations, list) or len(operations) > 16:
        raise GenericTypedInterpreterError("typed operations must be a bounded list")
    if len({canonical_json(item) for item in operations}) != len(operations):
        raise GenericTypedInterpreterError("typed patch contains a duplicate operation")

    staged = _state_without_history(state)
    if not _authorized(state, event):
        if operations:
            raise GenericTypedInterpreterError("unauthorized, stale, or duplicate event cannot carry operations")
        return staged

    names = [_validate_operation(item, event) for item in operations]
    if len(set(names)) != len(names):
        raise GenericTypedInterpreterError("typed patch repeats an operation type")
    for operation, name in zip(operations, names):
        if name == "cancel_commitment":
            _apply_cancel(staged, operation)
        elif name == "replace_commitment":
            _apply_replace(staged, operation, event)
        elif name == "activate_override":
            _apply_activate(staged, operation, event)
        elif name == "cancel_executing_action":
            _apply_cancel_action(staged, operation, event)
        elif name == "release_override":
            _apply_release(staged, operation, event)
        elif name != "acknowledge_event":
            raise GenericTypedInterpreterError("unhandled typed operation")

    if operations:
        staged["state_version"] = int(staged["state_version"]) + 1
        staged["evidence_versions"] = {
            "event_id": event["event_id"],
            "world_version": event["world_version"],
            "input_state_version": event["input_state_version"],
        }
    if canonical_json(state) != caller_before:
        raise RuntimeError("generic typed interpreter mutated caller state")
    return staged
