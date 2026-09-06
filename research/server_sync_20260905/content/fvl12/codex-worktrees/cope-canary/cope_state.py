from __future__ import annotations

import copy
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal


SlotMode = Literal["active", "suspended", "overridden", "expired"]
PatchType = Literal[
    "Insert",
    "Suspend",
    "Override",
    "Promote",
    "Demote",
    "Inherit",
    "Expire",
    "Revalidate",
    "Restore",
]
RevalidationStatus = Literal["OK", "DEGRADED", "FAIL"]


@dataclass(frozen=True)
class ConstraintSlot:
    id: str
    grounding: dict[str, Any] = field(default_factory=dict)
    mode: SlotMode = "active"
    priority: int = 0
    source: str = "unspecified"
    validity: dict[str, Any] = field(default_factory=dict)
    restore: dict[str, Any] = field(default_factory=dict)
    lineage: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class PatchOperation:
    op: PatchType
    slot_id: str | None = None
    slot: ConstraintSlot | None = None
    target_id: str | None = None
    priority: int | None = None
    revalidation: RevalidationStatus | None = None
    reason: str = ""
    source: str = "cope"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConstraintState:
    slots: dict[str, ConstraintSlot] = field(default_factory=dict)
    graph: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    revision: int = 0


class PatchApplicationError(ValueError):
    pass


def insert(slot: ConstraintSlot, *, reason: str = "", source: str = "cope") -> PatchOperation:
    return PatchOperation("Insert", slot_id=slot.id, slot=slot, reason=reason, source=source)


def suspend(slot_id: str, *, reason: str = "", source: str = "cope") -> PatchOperation:
    return PatchOperation("Suspend", slot_id=slot_id, reason=reason, source=source)


def override(slot_id: str, target_id: str, *, reason: str = "", source: str = "cope") -> PatchOperation:
    return PatchOperation("Override", slot_id=slot_id, target_id=target_id, reason=reason, source=source)


def promote(slot_id: str, priority: int, *, reason: str = "", source: str = "cope") -> PatchOperation:
    return PatchOperation("Promote", slot_id=slot_id, priority=priority, reason=reason, source=source)


def demote(slot_id: str, priority: int, *, reason: str = "", source: str = "cope") -> PatchOperation:
    return PatchOperation("Demote", slot_id=slot_id, priority=priority, reason=reason, source=source)


def inherit(slot_id: str, *, reason: str = "", source: str = "cope") -> PatchOperation:
    return PatchOperation("Inherit", slot_id=slot_id, reason=reason, source=source)


def expire(slot_id: str, *, reason: str = "", source: str = "cope") -> PatchOperation:
    return PatchOperation("Expire", slot_id=slot_id, reason=reason, source=source)


def revalidate(
    slot_id: str,
    status: RevalidationStatus,
    *,
    reason: str = "",
    source: str = "detector",
    metadata: dict[str, Any] | None = None,
) -> PatchOperation:
    return PatchOperation(
        "Revalidate",
        slot_id=slot_id,
        revalidation=status,
        reason=reason,
        source=source,
        metadata=dict(metadata or {}),
    )


def restore(slot_id: str, *, reason: str = "", source: str = "cope") -> PatchOperation:
    return PatchOperation("Restore", slot_id=slot_id, reason=reason, source=source)


def slot_key(text: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return key or "unknown"


def to_json_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return to_json_dict(asdict(value))
    if isinstance(value, dict):
        return {str(k): to_json_dict(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_dict(v) for v in value]
    return value


def _copy_slot(slot: ConstraintSlot) -> ConstraintSlot:
    return ConstraintSlot(
        id=slot.id,
        grounding=copy.deepcopy(slot.grounding),
        mode=slot.mode,
        priority=int(slot.priority),
        source=slot.source,
        validity=copy.deepcopy(slot.validity),
        restore=copy.deepcopy(slot.restore),
        lineage=copy.deepcopy(slot.lineage),
        history=copy.deepcopy(slot.history),
    )


def _event(operation: PatchOperation, revision: int) -> dict[str, Any]:
    return {
        "revision": int(revision),
        "op": operation.op,
        "slot_id": operation.slot_id,
        "target_id": operation.target_id,
        "priority": operation.priority,
        "revalidation": operation.revalidation,
        "reason": operation.reason,
        "source": operation.source,
        "metadata": copy.deepcopy(operation.metadata),
    }


def _require_slot(slots: dict[str, ConstraintSlot], slot_id: str | None, op: str) -> ConstraintSlot:
    if not slot_id:
        raise PatchApplicationError(f"{op} requires slot_id")
    if slot_id not in slots:
        raise PatchApplicationError(f"{op} references missing slot {slot_id!r}")
    return slots[slot_id]


def _with_history(slot: ConstraintSlot, event: dict[str, Any], **changes: Any) -> ConstraintSlot:
    history = copy.deepcopy(slot.history)
    history.append(copy.deepcopy(event))
    return replace(slot, history=history, **changes)


def _latest_revalidation(slot: ConstraintSlot) -> str | None:
    for event in reversed(slot.history):
        if event.get("op") == "Revalidate":
            return event.get("revalidation")
    return None


def apply_patch(state: ConstraintState, operations: list[PatchOperation]) -> ConstraintState:
    slots = {slot_id: _copy_slot(slot) for slot_id, slot in state.slots.items()}
    graph = copy.deepcopy(state.graph)
    history = copy.deepcopy(state.history)
    revision = int(state.revision)

    for operation in operations:
        revision += 1
        event = _event(operation, revision)
        op = operation.op

        if op == "Insert":
            if operation.slot is None:
                raise PatchApplicationError("Insert requires slot")
            slot = _copy_slot(operation.slot)
            if not slot.id:
                raise PatchApplicationError("Insert requires non-empty slot id")
            if slot.id in slots:
                raise PatchApplicationError(f"Insert would replace existing slot {slot.id!r}")
            event["slot_id"] = slot.id
            slots[slot.id] = _with_history(slot, event)

        elif op == "Suspend":
            slot = _require_slot(slots, operation.slot_id, op)
            if slot.mode == "expired":
                raise PatchApplicationError(f"cannot suspend expired slot {slot.id!r}")
            slots[slot.id] = _with_history(slot, event, mode="suspended")

        elif op == "Override":
            slot = _require_slot(slots, operation.slot_id, op)
            target = _require_slot(slots, operation.target_id, op)
            if slot.mode == "expired" or target.mode == "expired":
                raise PatchApplicationError("Override cannot reference expired slots")
            edge = {
                "type": "override",
                "from": target.id,
                "to": slot.id,
                "revision": revision,
                "reason": operation.reason,
            }
            graph.append(edge)
            lineage = copy.deepcopy(slot.lineage)
            lineage.append(edge)
            slots[slot.id] = _with_history(slot, event, mode="overridden", lineage=lineage)

        elif op == "Promote":
            slot = _require_slot(slots, operation.slot_id, op)
            if operation.priority is None:
                raise PatchApplicationError("Promote requires priority")
            if int(operation.priority) <= int(slot.priority):
                raise PatchApplicationError("Promote requires a strictly higher priority")
            slots[slot.id] = _with_history(slot, event, priority=int(operation.priority))

        elif op == "Demote":
            slot = _require_slot(slots, operation.slot_id, op)
            if operation.priority is None:
                raise PatchApplicationError("Demote requires priority")
            if int(operation.priority) >= int(slot.priority):
                raise PatchApplicationError("Demote requires a strictly lower priority")
            slots[slot.id] = _with_history(slot, event, priority=int(operation.priority))

        elif op == "Inherit":
            slot = _require_slot(slots, operation.slot_id, op)
            if slot.mode == "expired":
                raise PatchApplicationError(f"cannot inherit expired slot {slot.id!r}")
            slots[slot.id] = _with_history(slot, event)

        elif op == "Expire":
            slot = _require_slot(slots, operation.slot_id, op)
            slots[slot.id] = _with_history(slot, event, mode="expired")

        elif op == "Revalidate":
            slot = _require_slot(slots, operation.slot_id, op)
            if operation.revalidation not in {"OK", "DEGRADED", "FAIL"}:
                raise PatchApplicationError("Revalidate requires status OK, DEGRADED, or FAIL")
            slots[slot.id] = _with_history(slot, event)

        elif op == "Restore":
            slot = _require_slot(slots, operation.slot_id, op)
            if slot.mode == "expired":
                raise PatchApplicationError(f"cannot restore expired slot {slot.id!r}")
            if slot.mode not in {"suspended", "overridden"}:
                raise PatchApplicationError(f"Restore requires suspended or overridden slot, got {slot.mode!r}")
            latest = _latest_revalidation(slot)
            if latest not in {"OK", "DEGRADED"}:
                raise PatchApplicationError(f"Restore requires prior OK/DEGRADED Revalidate, got {latest!r}")
            graph.append(
                {
                    "type": "restore",
                    "from": slot.id,
                    "to": slot.id,
                    "revision": revision,
                    "revalidation": latest,
                    "reason": operation.reason,
                }
            )
            slots[slot.id] = _with_history(slot, event, mode="active")

        else:
            raise PatchApplicationError(f"unknown patch operation {op!r}")

        history.append(copy.deepcopy(event))

    next_state = ConstraintState(slots=slots, graph=graph, history=history, revision=revision)
    errors = validate_state_invariants(next_state)
    if errors:
        raise PatchApplicationError("; ".join(errors))
    return next_state


def validate_state_invariants(state: ConstraintState) -> list[str]:
    errors: list[str] = []
    if state.revision != len(state.history):
        errors.append(f"revision {state.revision} does not match history length {len(state.history)}")
    expected_revisions = list(range(1, len(state.history) + 1))
    actual_revisions = [int(event.get("revision", -1)) for event in state.history]
    if actual_revisions != expected_revisions:
        errors.append("global history revisions are not monotonic from 1")
    for slot_id, slot in state.slots.items():
        if slot.id != slot_id:
            errors.append(f"slot key {slot_id!r} does not match id {slot.id!r}")
        for event in slot.history:
            event_slot = event.get("slot_id")
            if event_slot not in {slot_id, None}:
                errors.append(f"slot {slot_id!r} has foreign history event for {event_slot!r}")
    for edge in state.graph:
        for endpoint in ("from", "to"):
            slot_id = edge.get(endpoint)
            if slot_id is not None and slot_id not in state.slots:
                errors.append(f"graph edge references missing {endpoint} slot {slot_id!r}")
    return errors


def plan_guarded_recovery(
    state: ConstraintState,
    revalidation_by_slot: dict[str, RevalidationStatus],
    *,
    degraded_priority_delta: int = 1,
) -> list[PatchOperation]:
    operations: list[PatchOperation] = []
    for slot_id in sorted(revalidation_by_slot):
        slot = state.slots.get(slot_id)
        if slot is None or slot.mode not in {"suspended", "overridden"}:
            continue
        status = revalidation_by_slot[slot_id]
        operations.append(revalidate(slot_id, status, reason="guarded_recovery_check"))
        if status == "OK":
            operations.append(restore(slot_id, reason="restore_after_ok_revalidation"))
        elif status == "DEGRADED":
            operations.append(restore(slot_id, reason="restore_after_degraded_revalidation"))
            operations.append(
                demote(
                    slot_id,
                    int(slot.priority) - int(degraded_priority_delta),
                    reason="degraded_revalidation_demotes_slot",
                )
            )
        elif status == "FAIL":
            operations.append(expire(slot_id, reason="expire_after_failed_revalidation"))
        else:
            raise PatchApplicationError(f"unknown revalidation status {status!r}")
    return operations


def initial_libero_pick_place_state(
    *,
    task_description: str,
    affected_object: str,
    target_joint: str,
    goal: str = "plate",
) -> ConstraintState:
    obj = slot_key(affected_object)
    goal_key = slot_key(goal)
    slots = {
        "task_goal:pick_place": ConstraintSlot(
            id="task_goal:pick_place",
            grounding={"type": "task_description", "text": task_description},
            priority=100,
            source="initial_task",
            validity={"predicate": "task_not_completed"},
            restore={"predicate": "task_goal_still_requested"},
        ),
        f"target_pose:{obj}": ConstraintSlot(
            id=f"target_pose:{obj}",
            grounding={"type": "sim_free_joint_pose", "joint": target_joint},
            priority=80,
            source="initial_perception",
            validity={"predicate": "target_pose_matches_current_world"},
            restore={"predicate": "target_pose_revalidated"},
        ),
        f"grasp_validity:{obj}": ConstraintSlot(
            id=f"grasp_validity:{obj}",
            grounding={"type": "grasp_state", "object": affected_object},
            priority=70,
            source="initial_task",
            validity={"predicate": "grasp_still_valid_for_target_pose"},
            restore={"predicate": "object_recontacted_or_regrasped"},
        ),
        f"goal_pose:{goal_key}": ConstraintSlot(
            id=f"goal_pose:{goal_key}",
            grounding={"type": "goal_region", "name": goal},
            priority=80,
            source="initial_task",
            validity={"predicate": "goal_region_still_valid"},
            restore={"predicate": "goal_region_revalidated"},
        ),
    }
    return ConstraintState(slots=slots)


def make_object_displacement_patch(
    *,
    affected_object: str,
    target_joint: str,
    before_qpos: list[float],
    after_qpos: list[float],
    goal: str = "plate",
    detector_source: str = "sim_gt_oracle",
) -> list[PatchOperation]:
    obj = slot_key(affected_object)
    goal_key = slot_key(goal)
    old_pose_id = f"target_pose:{obj}"
    new_pose_id = f"target_pose_current:{obj}"
    grasp_id = f"grasp_validity:{obj}"
    new_pose_slot = ConstraintSlot(
        id=new_pose_id,
        grounding={
            "type": "sim_free_joint_pose",
            "joint": target_joint,
            "qpos": list(after_qpos),
        },
        mode="active",
        priority=80,
        source="event_induced_patch",
        validity={"predicate": "current_pose_matches_fresh_observation"},
        restore={"predicate": "not_applicable_new_grounding"},
        lineage=[
            {
                "type": "replacement",
                "replaces": old_pose_id,
                "before_qpos": list(before_qpos),
                "after_qpos": list(after_qpos),
            }
        ],
    )
    return [
        revalidate(
            old_pose_id,
            "FAIL",
            source=detector_source,
            reason="object_displacement_invalidates_old_target_pose",
            metadata={"before_qpos": list(before_qpos), "after_qpos": list(after_qpos)},
        ),
        expire(old_pose_id, reason="old_target_pose_no_longer_valid", source="cope_patch"),
        insert(new_pose_slot, reason="insert_current_target_pose", source="cope_patch"),
        suspend(grasp_id, reason="object_displacement_invalidates_grasp_state", source="cope_patch"),
        inherit("task_goal:pick_place", reason="task_goal_survives_object_displacement", source="cope_patch"),
        inherit(f"goal_pose:{goal_key}", reason="goal_region_unaffected_by_target_displacement", source="cope_patch"),
    ]


def summarize_constraint_state(state: ConstraintState) -> dict[str, Any]:
    summary = {
        "active": [],
        "suspended": [],
        "overridden": [],
        "expired": [],
    }
    for slot_id in sorted(state.slots):
        slot = state.slots[slot_id]
        summary[slot.mode].append(
            {
                "id": slot.id,
                "priority": slot.priority,
                "source": slot.source,
                "grounding": copy.deepcopy(slot.grounding),
            }
        )
    return summary


def build_policy_prompt_from_constraint_state(
    *,
    original_task: str,
    state: ConstraintState,
    affected_object: str,
) -> tuple[str, dict[str, Any]]:
    obj = slot_key(affected_object)
    current_pose_id = f"target_pose_current:{obj}"
    old_pose_id = f"target_pose:{obj}"
    grasp_id = f"grasp_validity:{obj}"

    current_pose = state.slots.get(current_pose_id)
    old_pose = state.slots.get(old_pose_id)
    grasp = state.slots.get(grasp_id)

    if current_pose is None or current_pose.mode != "active":
        prompt = f"complete the original task: {original_task}"
        decision = "no_active_current_pose_slot"
    elif grasp is not None and grasp.mode == "suspended":
        prompt = f"relocalize the {affected_object} at its current position, regrasp if needed, then complete the original task: {original_task}"
        decision = "relocalize_regrasp_then_continue"
    else:
        prompt = f"relocalize the {affected_object} at its current position, then complete the original task: {original_task}"
        decision = "relocalize_then_continue"

    metadata = {
        "adapter": "cope_constraint_state_prompt_v0",
        "decision": decision,
        "affected_object": affected_object,
        "active_current_pose_slot": current_pose_id if current_pose is not None and current_pose.mode == "active" else None,
        "expired_old_pose_slot": old_pose_id if old_pose is not None and old_pose.mode == "expired" else None,
        "suspended_grasp_slot": grasp_id if grasp is not None and grasp.mode == "suspended" else None,
        "slot_summary": summarize_constraint_state(state),
    }
    return prompt, metadata
