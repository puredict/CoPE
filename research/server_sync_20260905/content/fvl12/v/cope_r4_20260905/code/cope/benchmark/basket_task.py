"""Multi-object basket sorting/packing benchmark.

Chosen over the ReKep pen task because that task's nominal success floor is low
and it confounds execution failure with recovery failure. Objects and actions
here are restricted to already-validated pick-and-place primitives.

Nominal task:  place milk and yogurt in basket A; place butter in basket B.

Interruption conditions I1-I4 are defined at the bottom.
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..constraint_slot import ConstraintSlot, Priority, SlotSource
from ..policies.adaptation_input import AdaptationInput

OBJECTS = ("milk", "yogurt", "butter")
# basket_C is a spare destination so that a *repeated* redirection can end
# somewhere other than the nominal target; without it I3 would be a no-op
# for final placement and the control arm would pass it for free.
BASKETS = ("basket_A", "basket_B", "basket_C")

NOMINAL_ASSIGNMENT = {"milk": "basket_A", "yogurt": "basket_A",
                      "butter": "basket_B"}

# Fixed scripted execution order. A property of the executor, not of any
# policy: both arms inherit it through the shared slot payload, so the
# interruption always lands at the same point in the task.
EXECUTION_ORDER = {"milk": 0, "yogurt": 1, "butter": 2}

SAFETY = ({"id": "c_no_collision", "grounding": "avoid_collision",
           "payload": {"kind": "safety"}},
          {"id": "c_gentle", "grounding": "handle_objects_gently",
           "payload": {"kind": "user_preference_as_safety"}})


def _seed(key: str) -> int:
    return int(hashlib.blake2b(key.encode(), digest_size=4).hexdigest(), 16)


@dataclass(frozen=True)
class BasketTaskSpec:
    seed: int
    condition: str = "nominal"      # nominal | I1 | I2 | I3 | I4
    method: str = "CoPE"
    horizon_steps: int = 900

    def key(self) -> str:
        """Pairing key -- deliberately EXCLUDES the method."""
        return f"basket_sorting|{self.condition}|{self.seed}"

    def episode_id(self) -> str:
        return f"{self.key()}|{self.method}"


def nominal_goals() -> List[ConstraintSlot]:
    return [ConstraintSlot(id=f"g_{o}", grounding=f"place_{o}_in_{b}",
                           priority=Priority.SOFT, source=SlotSource.INITIAL_TASK,
                           payload={"object": o, "target": b,
                                    "order": EXECUTION_ORDER[o]})
            for o, b in NOMINAL_ASSIGNMENT.items()]


def safety_slots() -> List[ConstraintSlot]:
    return [ConstraintSlot(id=c["id"], grounding=c["grounding"],
                           priority=Priority.HARD, source=SlotSource.SAFETY_RULE,
                           payload=c["payload"]) for c in SAFETY]


def build_initial_state() -> List[ConstraintSlot]:
    return nominal_goals() + safety_slots()


@dataclass(frozen=True)
class InterruptionCondition:
    """A user update delivered mid-episode. Identical for every method.

    `trigger_after_goal=""` means the update is delivered before any goal is
    attempted. `execution_order` lets a condition set the scripted order so the
    interruption lands where the condition intends; it is part of the shared
    initial state, so both arms get the same ordering.
    """
    name: str
    trigger_after_goal: str
    update: Dict[str, Any]
    second_update: Optional[Dict[str, Any]] = None
    second_trigger_after_goal: Optional[str] = None
    #: I5 needs a third update. Delivery timing comes from the scheduler, not
    #: from any goal completing (see `cope/benchmark/scheduler.py`).
    third_update: Optional[Dict[str, Any]] = None
    execution_order: Optional[Dict[str, int]] = None
    description: str = ""

    @property
    def n_updates(self) -> int:
        return 1 + (self.second_update is not None) + (self.third_update is not None)


def interruption(condition: str, seed: int) -> Optional[InterruptionCondition]:
    """The four conditions. Deterministic in (condition, seed) -- never in method."""
    if condition == "nominal":
        return None
    if condition == "I1":       # cancellation + redirection
        return InterruptionCondition(
            name="I1", trigger_after_goal="g_milk",
            update={"cancel": ["g_yogurt"],
                    "cancel_reason": "user no longer wants the yogurt packed",
                    "redirect": {"g_butter": "basket_A"}},
            description="milk done; cancel yogurt; move butter B->A")
    if condition == "I2":       # temporary target unavailability
        # butter is scheduled FIRST so that the unavailability actually bites:
        # the arm must set it aside, do the other work, and come back.
        return InterruptionCondition(
            name="I2", trigger_after_goal="",
            execution_order={"butter": 0, "milk": 1, "yogurt": 2},
            update={"suspend": ["g_butter"],
                    "suspend_reason": "basket_B temporarily unavailable",
                    "world": {"unavailable_targets": ["basket_B"]}},
            second_trigger_after_goal="g_milk",
            second_update={"restore": ["g_butter"],
                           "world": {"unavailable_targets": []}},
            description="suspend butter while B unavailable, restore later")
    if condition == "I3":       # repeated interruption on the SAME slot
        # Both updates land before butter (execution order 2) is attempted, so
        # the condition is winnable and the metric measures state survival
        # across two consecutive edits rather than reaction latency.
        return InterruptionCondition(
            name="I3", trigger_after_goal="g_milk",
            update={"redirect": {"g_butter": "basket_A"},
                    "user_request": "actually put the butter in basket A"},
            second_trigger_after_goal="g_yogurt",
            second_update={"redirect": {"g_butter": "basket_C"},
                           "user_request": "sorry, basket C in the end",
                           "insert_safety": [
                               {"id": "c_keep_upright",
                                "grounding": "keep_object_upright",
                                "reason": "user asked for careful handling"}]},
            description="the same goal is redirected twice in one episode")
    if condition == "I4":       # changed-world restoration
        return InterruptionCondition(
            name="I4", trigger_after_goal="",
            execution_order={"butter": 0, "milk": 1, "yogurt": 2},
            update={"suspend": ["g_butter"],
                    "suspend_reason": "basket_B removed from the table",
                    "world": {"unavailable_targets": ["basket_B"],
                              "moved_targets": ["basket_B"]}},
            second_trigger_after_goal="g_milk",
            second_update={"restore": ["g_butter"],
                           "world": {"unavailable_targets": [],
                                     "moved_targets": ["basket_B"]}},
            description="B is suspended, MOVED, then made available again; "
                        "restoration must revalidate the old grounding")
    if condition == "I5":       # nested override and restoration
        # Diagnostic condition for LIFECYCLE + LINEAGE. Butter is suspended
        # (basket_B gone), temporarily redirected to basket_C, the redirection
        # is then cancelled before it completes, basket_B is moved and returns.
        # The system must decide WHICH butter version is restorable, revalidate
        # the moved basket, and end with exactly one active butter goal.
        #
        # This is deliberately not stacked in CoPE's favour: FSR-PC receives the
        # identical full event history and can regenerate a coherent state.
        return InterruptionCondition(
            name="I5", trigger_after_goal="",
            execution_order={"butter": 0, "milk": 1, "yogurt": 2},
            update={"suspend": ["g_butter"],
                    "suspend_reason": "basket_B removed from the table",
                    "world": {"unavailable_targets": ["basket_B"],
                              "moved_targets": []},
                    "user_request": "basket B is gone -- hold the butter"},
            second_trigger_after_goal="",
            second_update={"redirect": {"g_butter": "basket_C"},
                           "user_request": "put the butter in basket C instead",
                           "world": {"unavailable_targets": ["basket_B"]}},
            third_update={"cancel_redirect": ["g_butter@basket_C"],
                          "restore": ["g_butter"],
                          "cancel_reason": "user withdrew the basket C detour",
                          "user_request": "no, basket B is back -- use it",
                          "world": {"unavailable_targets": [],
                                    "moved_targets": ["basket_B"]}},
            description="suspend -> temporary override -> cancel the override "
                        "-> target moved -> restore the ORIGINAL grounding")
    raise ValueError(f"unknown condition {condition!r}")


def make_adaptation_input(spec: BasketTaskSpec, world: Dict[str, Any],
                          completed: Tuple[str, ...], pending: Tuple[str, ...],
                          cancelled: Tuple[str, ...],
                          task_history: Tuple[Dict[str, Any], ...],
                          event_history: Tuple[Dict[str, Any], ...],
                          update: Dict[str, Any], event_id: str,
                          event_step: int) -> AdaptationInput:
    """Build the SINGLE information packet handed to whichever policy runs.

    The method is not an input to any field -- that is the fairness guarantee.
    """
    return AdaptationInput(
        world_state={**world, "update": update},
        robot_state={"holding": None, "base_pose": [0.0, 0.0, 0.0]},
        completed_goals=tuple(completed), pending_goals=tuple(pending),
        cancelled_goals=tuple(cancelled),
        user_request=update.get("user_request", "revise the packing task"),
        safety_constraints=tuple(dict(c) for c in SAFETY),
        task_history=tuple(task_history), event_history=tuple(event_history),
        perception={"visible_objects": list(OBJECTS),
                    "visible_baskets": list(BASKETS),
                    "unavailable_targets": list(
                        world.get("unavailable_targets", []) or [])},
        compute_budget={"max_planner_calls": 4, "max_seconds": 30.0,
                        "horizon_steps": spec.horizon_steps},
        event_id=event_id, event_step=event_step)


# Which audit queries each condition actually poses. A query the episode never
# raises is scored as not-applicable (None), never as an audit failure.
AUDIT_APPLICABILITY = {
    "nominal": {},
    "I1": {"Q1_which_goal_cancelled": True, "Q2_which_completed_preserved": True,
           "Q5_replacement_state": True},
    "I2": {"Q2_which_completed_preserved": True, "Q3_why_suspended": True,
           "Q4_restore_condition": True},
    "I3": {"Q2_which_completed_preserved": True, "Q5_replacement_state": True},
    "I4": {"Q2_which_completed_preserved": True, "Q3_why_suspended": True,
           "Q4_restore_condition": True},
    # I5 poses every query: a cancellation, a preserved goal, a suspension,
    # a restoration condition, and a replacement that is later withdrawn.
    "I5": {"Q1_which_goal_cancelled": True, "Q2_which_completed_preserved": True,
           "Q3_why_suspended": True, "Q4_restore_condition": True,
           "Q5_replacement_state": True},
}


def audit_applicability(condition: str):
    return dict(AUDIT_APPLICABILITY.get(condition, {}))
