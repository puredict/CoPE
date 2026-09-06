"""Deterministic, lineage-load-bearing long-horizon task generator."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import random
from typing import Any, Dict, List, Tuple

from .models import (
    LineageEvent,
    LineageScenario,
    ScenarioSpec,
    WorkflowSlot,
    WorkflowState,
)


CRITICAL_LOGICAL_ID = "order-critical"
ROOT_SLOT_ID = "order-critical/root"


def _lineage_root(slot_id: str) -> Dict[str, Any]:
    return {"parent_id": None, "root_id": slot_id, "depth": 0, "child_ids": []}


def _initial_history(slot_id: str, mode: str) -> Tuple[Dict[str, Any], ...]:
    return ({
        "seq": 1,
        "event_id": "task-initialization",
        "operation": "Create",
        "mode_before": None,
        "mode_after": mode,
        "detail": f"registered persistent slot {slot_id}",
    },)


def _plan(primary_target: str, receipt_variant: int) -> List[Dict[str, str]]:
    # Variant 0 is the true root continuation and matches the existing LIBERO
    # basket task. Other variants are feasible but task-incorrect detours.
    receipts = (
        ("basket_A", "basket_A"),
        ("basket_C", "basket_A"),
        ("basket_A", "basket_C"),
        ("basket_B", "basket_C"),
    )
    milk_target, yogurt_target = receipts[receipt_variant % len(receipts)]
    return [
        {"object": "butter", "target": primary_target, "role": "primary_order"},
        {"object": "milk", "target": milk_target, "role": "receipt_token"},
        {"object": "yogurt", "target": yogurt_target, "role": "closure_token"},
    ]


def _workflow_payload(
    *, order_id: str, primary_target: str, receipt_variant: int, nonce: str
) -> Dict[str, Any]:
    return {
        "order_id": order_id,
        "object": "butter",
        "target": primary_target,
        "plan": _plan(primary_target, receipt_variant),
        "continuation_key": f"receipt-v{receipt_variant}",
        "audit_nonce": nonce,
    }


def _archive_slot(index: int, rng: random.Random) -> WorkflowSlot:
    object_name = ("milk", "yogurt", "butter")[index % 3]
    target = ("basket_A", "basket_B", "basket_C")[(index * 5 + 1) % 3]
    sid = f"archive/order-{index:04d}"
    nonce = hashlib.sha256(f"{rng.random()}:{index}".encode()).hexdigest()[:20]
    created = _initial_history(sid, "active")[0]
    completed = {
        "seq": 2,
        "event_id": f"historical-completion-{index:04d}",
        "operation": "Complete",
        "mode_before": "active",
        "mode_after": "completed",
        "detail": "order physically completed; record remains referenceable",
    }
    return WorkflowSlot(
        slot_id=sid,
        logical_id=f"historical-order-{index:04d}",
        kind="order_archive",
        mode="completed",
        priority="soft",
        grounding=f"place_{object_name}_in_{target}",
        payload={
            "order_number": index,
            "object": object_name,
            "target": target,
            "customer_tier": ("standard", "cold-chain", "fragile")[index % 3],
            "receipt_code": f"R-{rng.randrange(10**8):08d}",
            "audit_nonce": nonce,
            "completion_checkpoint": {
                "station": f"station-{index % 7}",
                "batch": f"batch-{index // 7:03d}",
                "verified": True,
            },
        },
        lineage=_lineage_root(sid),
        history=(created, completed),
    )


def _safety_slot(slot_id: str, grounding: str) -> WorkflowSlot:
    return WorkflowSlot(
        slot_id=slot_id,
        logical_id=slot_id,
        kind="safety",
        mode="active",
        priority="hard",
        grounding=grounding,
        payload={"must_preserve": True, "scope": "entire_shift"},
        lineage=_lineage_root(slot_id),
        history=_initial_history(slot_id, "active"),
    )


def build_scenario(spec: ScenarioSpec) -> LineageScenario:
    if spec.initial_slots < 6:
        raise ValueError("initial_slots must be at least 6")
    if spec.lineage_depth < 2:
        raise ValueError("lineage_depth must be at least 2")
    rng = random.Random(spec.seed)
    nonce = hashlib.sha256(f"critical:{spec.seed}".encode()).hexdigest()[:20]
    root = WorkflowSlot(
        slot_id=ROOT_SLOT_ID,
        logical_id=CRITICAL_LOGICAL_ID,
        kind="workflow",
        mode="active",
        priority="soft",
        grounding="place_butter_in_basket_B_then_execute_root_receipt",
        payload=_workflow_payload(
            order_id=f"critical-{spec.seed:04d}",
            primary_target="basket_B",
            receipt_variant=0,
            nonce=nonce,
        ),
        lineage=_lineage_root(ROOT_SLOT_ID),
        history=_initial_history(ROOT_SLOT_ID, "active"),
    )
    safety = [
        _safety_slot("safety/no-collision", "avoid_robot_object_collision"),
        _safety_slot("safety/gentle", "keep_contact_force_below_limit"),
        _safety_slot("safety/no-repeat", "never_repeat_a_completed_action"),
    ]
    archives = [
        _archive_slot(index, rng)
        for index in range(spec.initial_slots - 1 - len(safety))
    ]
    state = WorkflowState(
        revision=0,
        slots={slot.slot_id: slot for slot in [root, *safety, *archives]},
    )

    events: List[LineageEvent] = []
    ordinal = 1
    events.append(LineageEvent(
        event_id=f"seed-{spec.seed:04d}/e{ordinal:02d}",
        ordinal=ordinal,
        kind="suspend_current",
        current_slot_id=ROOT_SLOT_ID,
        user_request="The original station is temporarily unavailable. Suspend this order without deleting it.",
        reason="temporary station outage",
    ))
    ordinal += 1
    events.append(LineageEvent(
        event_id=f"seed-{spec.seed:04d}/e{ordinal:02d}",
        ordinal=ordinal,
        kind="restore_current",
        current_slot_id=ROOT_SLOT_ID,
        user_request="The original station is available again. Revalidate and resume the suspended order.",
        reason="original station revalidated",
    ))
    ordinal += 1

    current_id = ROOT_SLOT_ID
    # The deepest detour deliberately has the same butter->basket_B surface
    # goal as the root, but a different milk/yogurt continuation. A compiler
    # that discards lineage can therefore look correct until the later actions.
    target_pattern = ("basket_C", "basket_A", "basket_C", "basket_B")
    for depth in range(1, spec.lineage_depth + 1):
        child_id = f"order-critical/detour-{depth:02d}"
        primary_target = target_pattern[(depth - 1) % len(target_pattern)]
        if depth == spec.lineage_depth:
            primary_target = "basket_B"
        child_payload = _workflow_payload(
            order_id=f"critical-{spec.seed:04d}",
            primary_target=primary_target,
            receipt_variant=(depth % 3) + 1,
            nonce=hashlib.sha256(
                f"detour:{spec.seed}:{depth}".encode()
            ).hexdigest()[:20],
        )
        new_slot = {
            "slot_id": child_id,
            "logical_id": CRITICAL_LOGICAL_ID,
            "grounding": (
                f"place_butter_in_{primary_target}_then_execute_"
                f"receipt_v{(depth % 3) + 1}"
            ),
            "priority": "soft",
            "payload": child_payload,
        }
        events.append(LineageEvent(
            event_id=f"seed-{spec.seed:04d}/e{ordinal:02d}",
            ordinal=ordinal,
            kind="override_current",
            current_slot_id=current_id,
            user_request=(
                f"Temporarily replace the current version with detour {depth}. "
                f"Use {primary_target} and its explicitly registered continuation."
            ),
            reason=f"temporary detour level {depth}",
            new_slot=new_slot,
        ))
        current_id = child_id
        ordinal += 1

    events.append(LineageEvent(
        event_id=f"seed-{spec.seed:04d}/e{ordinal:02d}",
        ordinal=ordinal,
        kind="suspend_current",
        current_slot_id=current_id,
        user_request="Pause the currently active deepest detour, but retain its exact restore path.",
        reason="brief hold on deepest detour",
    ))
    ordinal += 1
    events.append(LineageEvent(
        event_id=f"seed-{spec.seed:04d}/e{ordinal:02d}",
        ordinal=ordinal,
        kind="restore_current",
        current_slot_id=current_id,
        user_request="Resume the just-suspended deepest detour after revalidation.",
        reason="deepest detour revalidated",
    ))
    ordinal += 1
    events.append(LineageEvent(
        event_id=f"seed-{spec.seed:04d}/e{ordinal:02d}",
        ordinal=ordinal,
        kind="restore_root",
        current_slot_id=current_id,
        user_request=(
            "Withdraw every temporary detour in this order's lineage and restore "
            "the original root workflow, including its exact downstream receipt "
            "and closure continuation. Do not infer the continuation from the "
            "surface butter destination."
        ),
        reason="all temporary detours withdrawn; original order reinstated",
    ))

    expected_plan = tuple(dict(item) for item in root.payload["plan"])
    contract = {
        "task_name": "persistent_multi_order_fulfillment",
        "critical_logical_id": CRITICAL_LOGICAL_ID,
        "root_slot_id": ROOT_SLOT_ID,
        "success_definition": {
            "required_final_plan": list(expected_plan),
            "all_model_updates_valid": True,
            "exact_object_assignment": True,
            "no_expired_detour_executed": True,
            "no_completed_action_repeated": True,
        },
        "lineage_rule": (
            "restore_root follows parent_id edges to depth zero; the root payload "
            "is authoritative even when a detour has the same primary target"
        ),
        "objects": ["butter", "milk", "yogurt"],
        "targets": ["basket_A", "basket_B", "basket_C"],
    }
    return LineageScenario(
        spec=spec,
        initial_state=state,
        events=tuple(events),
        critical_logical_id=CRITICAL_LOGICAL_ID,
        expected_plan=expected_plan,
        task_contract=contract,
    )


def oracle_patch(state: WorkflowState, event: LineageEvent) -> Dict[str, Any]:
    if event.kind == "suspend_current":
        ops = [{"op": "suspend", "slot_id": event.current_slot_id}]
    elif event.kind == "restore_current":
        ops = [{"op": "restore", "slot_id": event.current_slot_id}]
    elif event.kind == "override_current":
        ops = [{
            "op": "override",
            "slot_id": event.current_slot_id,
            "new_slot": dict(event.new_slot or {}),
        }]
    elif event.kind == "restore_root":
        ops = [{"op": "restore_root", "from_slot_id": event.current_slot_id}]
    else:
        raise ValueError(f"unknown event kind {event.kind!r}")
    return {
        "schema_version": "cope-lineage-patch-v1",
        "event_id": event.event_id,
        "base_revision": state.revision,
        "ops": ops,
    }
