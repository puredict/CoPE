"""Symbolic operator model + first-class event requirements.

Two corrections drive this design:

* **Physical separation of end-effector and object.**  A released object cannot
  be reoriented by the gripper, so ``Stabilize`` requires ``object_grasped``.
  ``WaitUntilClear`` only demands gripper-based stabilization when the object is
  actually held; a released, stationary object needs none.
* **Event-conditioned goals.**  The planner goal is NOT a generic
  ``restore_valid and not obstacle_present``.  It is a ``RepairGoal`` derived
  from the *full active predicate set*, so an obstacle, a slip, a relocation, or
  any combination each impose their own requirements, and a compound state
  imposes the union.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Dict, FrozenSet, List, Tuple


@dataclass(frozen=True)
class AbstractState:
    # --- execution mode
    nominal_suspended: bool = False
    # --- end-effector facts
    ee_at_handoff: bool = False
    orientation_restored: bool = False
    safe_clearance: bool = True
    # --- object facts (distinct from the end-effector!)
    object_grasped: bool = True
    object_stable: bool = False        # only meaningful while grasped
    # --- world facts
    obstacle_present: bool = False
    # --- target facts
    target_changed: bool = False
    new_target_known: bool = False
    aligned_to_current_target: bool = False
    # --- restoration
    restore_valid: bool = False

    def true_flags(self) -> Tuple[str, ...]:
        return tuple(k for k, v in self.__dict__.items() if v)

    def with_(self, **kw) -> "AbstractState":
        return replace(self, **kw)


@dataclass(frozen=True)
class RepairGoal:
    """Event-conditioned goal: every requirement must hold in the final state."""

    required_true: FrozenSet[str] = frozenset()
    required_false: FrozenSet[str] = frozenset()
    label: str = ""

    def satisfied_by(self, s: AbstractState) -> bool:
        d = s.__dict__
        return (all(d.get(k) for k in self.required_true)
                and all(not d.get(k) for k in self.required_false))

    def residual(self, s: AbstractState) -> Tuple[str, ...]:
        """Which requirements are still unmet (used as a hard reject reason)."""
        d = s.__dict__
        miss = [k for k in sorted(self.required_true) if not d.get(k)]
        miss += [f"not:{k}" for k in sorted(self.required_false) if d.get(k)]
        return tuple(miss)

    def union(self, other: "RepairGoal") -> "RepairGoal":
        return RepairGoal(
            required_true=self.required_true | other.required_true,
            required_false=self.required_false | other.required_false,
            label=f"{self.label}+{other.label}".strip("+"),
        )


@dataclass(frozen=True)
class SymbolicOp:
    name: str
    precondition: Callable[[AbstractState], bool]
    effect: Callable[[AbstractState], AbstractState]
    cost: float = 1.0

    def applicable(self, s: AbstractState) -> bool:
        # must hold AND make progress (prevents no-op cycles; guarantees
        # termination since every applicable op adds information)
        return self.precondition(s) and self.effect(s) != s


def _wait_ok(s: AbstractState) -> bool:
    """WaitUntilClear precondition.

    Requires suspension, an obstacle to wait out, and a safe standoff (only
    Retreat opens clearance).  Gripper-based stabilization is required ONLY when
    the object is actually held; a released object resting on the surface needs
    no gripper stabilization.
    """
    if not (s.nominal_suspended and s.obstacle_present and s.safe_clearance):
        return False
    return s.object_stable if s.object_grasped else True


SYMBOLIC_OPS: Dict[str, SymbolicOp] = {
    "Suspend": SymbolicOp(
        "Suspend",
        lambda s: not s.nominal_suspended,
        lambda s: s.with_(nominal_suspended=True),
        cost=1.0,
    ),
    # Stabilize acts on the HELD object via the gripper -> requires a grasp.
    "Stabilize": SymbolicOp(
        "Stabilize",
        lambda s: s.nominal_suspended and s.object_grasped and not s.object_stable,
        lambda s: s.with_(object_stable=True),
        cost=1.5,
    ),
    # The only operator that increases clearance.
    "Retreat": SymbolicOp(
        "Retreat",
        lambda s: s.nominal_suspended and s.obstacle_present and not s.safe_clearance,
        lambda s: s.with_(safe_clearance=True),
        cost=2.0,
    ),
    "WaitUntilClear": SymbolicOp(
        "WaitUntilClear",
        _wait_ok,
        lambda s: s.with_(obstacle_present=False),
        cost=2.0,
    ),
    # Re-acquiring yields a grasp but the object is NOT yet stabilized.
    "ReacquireTarget": SymbolicOp(
        "ReacquireTarget",
        lambda s: (s.nominal_suspended and (not s.object_grasped)
                   and s.new_target_known and s.safe_clearance),
        lambda s: s.with_(object_grasped=True, object_stable=False),
        cost=3.0,
    ),
    # Adopt the relocated target as the task's current goal contract.
    "UpdateTargetContract": SymbolicOp(
        "UpdateTargetContract",
        lambda s: (s.nominal_suspended and s.target_changed
                   and s.new_target_known and not s.aligned_to_current_target),
        lambda s: s.with_(aligned_to_current_target=True),
        cost=1.0,
    ),
    # Return the (held, stabilized) object to the continuation handoff.
    "Realign": SymbolicOp(
        "Realign",
        lambda s: (s.nominal_suspended and s.object_grasped and s.object_stable
                   and s.safe_clearance and not s.obstacle_present
                   and not (s.ee_at_handoff and s.orientation_restored)),
        lambda s: s.with_(ee_at_handoff=True, orientation_restored=True),
        cost=2.0,
    ),
    "Resume": SymbolicOp(
        "Resume",
        lambda s: (s.ee_at_handoff and s.orientation_restored and s.object_grasped
                   and (s.aligned_to_current_target if s.target_changed else True)
                   and not s.restore_valid),
        lambda s: s.with_(restore_valid=True),
        cost=1.0,
    ),
}


# --- predicate set -> abstract state + goal ---------------------------------
@dataclass(frozen=True)
class WorldPredicates:
    """The full active predicate set, shared identically by ALL policies.

    This is the symmetric information channel: online synthesis and every
    offline baseline receive exactly these predicates, so no method sees a
    richer view of the world than another.
    """

    obstacle_present: bool = False
    unsafe_clearance: bool = False
    object_slipped: bool = False
    target_relocated: bool = False

    def active(self) -> Tuple[str, ...]:
        return tuple(k for k, v in self.__dict__.items() if v)

    def key(self) -> FrozenSet[str]:
        """Canonical key of the predicate combination (for branch lookup)."""
        return frozenset(k for k in ("obstacle_present", "object_slipped",
                                     "target_relocated") if getattr(self, k))


def state_from_predicates(p: WorldPredicates) -> AbstractState:
    return AbstractState(
        nominal_suspended=False,
        ee_at_handoff=False,
        orientation_restored=False,
        safe_clearance=not p.unsafe_clearance,
        object_grasped=not p.object_slipped,
        object_stable=False,
        obstacle_present=p.obstacle_present,
        target_changed=p.target_relocated,
        new_target_known=True,
        aligned_to_current_target=False,
        restore_valid=False,
    )


def goal_from_predicates(p: WorldPredicates) -> RepairGoal:
    """Union of every active predicate's requirements, plus restoration."""
    goal = RepairGoal(required_true=frozenset({"restore_valid"}), label="restore")
    if p.obstacle_present or p.unsafe_clearance:
        goal = goal.union(RepairGoal(
            required_true=frozenset({"safe_clearance"}),
            required_false=frozenset({"obstacle_present"}),
            label="obstacle"))
    if p.object_slipped:
        goal = goal.union(RepairGoal(
            required_true=frozenset({"object_grasped", "object_stable"}),
            label="slip"))
    if p.target_relocated:
        goal = goal.union(RepairGoal(
            required_true=frozenset({"aligned_to_current_target"}),
            label="relocation"))
    return goal


# --- back-compat shim used by older call sites ------------------------------
def initial_state(*, obstacle_present: bool, safe_clearance: bool,
                  object_grasped: bool) -> AbstractState:
    return state_from_predicates(WorldPredicates(
        obstacle_present=obstacle_present,
        unsafe_clearance=not safe_clearance,
        object_slipped=not object_grasped,
    ))
