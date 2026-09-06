"""ConstraintStateToRepairGoalCompiler --- CoPE semantics -> repair requirements.

This is the missing link the audit identified. Previously the semantic layer
compiled only to an `ExecutorRequest` (a list of active goals) and the repair
engine was never told *what the physical recovery has to achieve*. Here the
constraint-state change itself is compiled into the engine's own vocabulary:

    (S_t, S_t+, adaptation)  ->  (Event, WorldPredicates, AbstractState, RepairGoal)

Two properties matter and both are tested:

1. **The compiler reads the state DIFF, not the policy.** It is handed the
   before-state, the after-state and the adaptation record. It never asks which
   policy produced them, so CoPE and FSR-PC reach the identical requirement set
   whenever they make the same semantic change. That is what keeps requirement
   10 (FSR-PC uses the same downstream stack) honest.

2. **Requirements are attributed.** Every requirement carries the slot and the
   lifecycle transition that induced it, so the audit trace can answer "why did
   the robot have to do that?" rather than only "what did it do?".

Mapping rules (slot lifecycle transition -> repair requirement):

| transition                        | physical meaning        | requirement            |
|-----------------------------------|-------------------------|------------------------|
| ACTIVE -> OVERRIDDEN (re-grounded) | the target moved        | aligned_to_current_target, restore_valid |
| ACTIVE -> SUSPENDED (target gone)  | set the goal aside      | restore_valid (end resumable; do NOT try to clear an absent basket) |
| ACTIVE -> EXPIRED (cancelled)      | stop pursuing it        | restore_valid (must still end resumable) |
| SUSPENDED -> ACTIVE (restored)     | resume the old goal     | restore_valid + the slot's own restore predicate |
| INSERT of a HARD safety slot       | new safety envelope     | safe_clearance, not obstacle_present |
| object not grasped in the world    | slip                    | object_grasped, object_stable |

`restore_valid` appears in almost every rule on purpose: whatever the semantic
change was, the physical system must end in a state from which the interrupted
stage can legally resume. That requirement is checked against the continuation
contract by the engine's own rollout verifier, not by this compiler.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from rekep_repair.events.event import Event, EventType
from rekep_repair.repair.abstract_state import (
    AbstractState, RepairGoal, WorldPredicates, goal_from_predicates,
    state_from_predicates,
)

from ..constraint_slot import Priority, SlotMode, SlotSource
from ..constraint_state import ConstraintState
from ..naming import canonical_id
from ..patch import OpType, Patch, RegeneratedState


@dataclass(frozen=True)
class RequirementSource:
    """Why a single requirement exists. Feeds the audit trace."""
    slot_id: str
    transition: str                 # "active->suspended", "insert", ...
    requirement: str                # "safe_clearance" / "not:obstacle_present"
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"slot_id": self.slot_id, "transition": self.transition,
                "requirement": self.requirement, "reason": self.reason}


@dataclass
class RepairRequirements:
    """Everything the frozen repair engine needs, derived from CoPE semantics."""
    event: Event
    predicates: WorldPredicates
    abstract_init: AbstractState
    goal: RepairGoal
    sources: List[RequirementSource] = field(default_factory=list)
    needs_physical_repair: bool = True
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event.event_id,
            "event_type": self.event.event_type.value,
            "severity": round(float(self.event.severity), 4),
            "affected_entities": list(self.event.affected_entities),
            "predicates_active": list(self.predicates.active()),
            "abstract_init_true": list(self.abstract_init.true_flags()),
            "goal_label": self.goal.label,
            "required_true": sorted(self.goal.required_true),
            "required_false": sorted(self.goal.required_false),
            "sources": [s.to_dict() for s in self.sources],
            "needs_physical_repair": self.needs_physical_repair,
            "note": self.note,
        }

    def fingerprint(self) -> str:
        """Identical semantic change => identical requirements, whatever the arm."""
        import hashlib
        import json
        payload = {"required_true": sorted(self.goal.required_true),
                   "required_false": sorted(self.goal.required_false),
                   "predicates": sorted(self.predicates.active()),
                   "event_type": self.event.event_type.value}
        return hashlib.blake2b(json.dumps(payload, sort_keys=True).encode(),
                               digest_size=8).hexdigest()


class ConstraintStateToRepairGoalCompiler:
    """Compiles a constraint-state transition into a repair goal.

    Stateless and policy-blind by construction: `compile()` receives only
    states, an adaptation record and the world, never a policy handle.
    """

    #: transitions that oblige the physical layer to do something
    PHYSICAL_TRANSITIONS = {
        (SlotMode.ACTIVE, SlotMode.OVERRIDDEN): "retarget",
        (SlotMode.ACTIVE, SlotMode.SUSPENDED): "suspend",
        (SlotMode.ACTIVE, SlotMode.EXPIRED): "cancel",
        (SlotMode.SUSPENDED, SlotMode.ACTIVE): "restore",
        (SlotMode.OVERRIDDEN, SlotMode.ACTIVE): "restore",
        (SlotMode.SUSPENDED, SlotMode.EXPIRED): "cancel",
    }

    def __init__(self, target_move_threshold: float = 0.15):
        self.target_move_threshold = target_move_threshold

    # ------------------------------------------------------------------
    def compile(self, *, before: ConstraintState, after: ConstraintState,
                adaptation: Any, world: Dict[str, Any], ctx: Any,
                event_id: str, step: int) -> RepairRequirements:
        """`adaptation` is a `Patch` (CoPE) or a `RegeneratedState` (FSR-PC).

        Only its *effect on the state* is used, never its type, except to label
        the trace. Both arms therefore compile to the same requirements for the
        same semantic change.
        """
        transitions = self._diff(before, after)
        inserted = self._inserted_safety(before, after)

        # --- physical predicates observed in the world (shared channel) ----
        preds = self._predicates(ctx, world, transitions)
        abstract_init = state_from_predicates(preds)

        # --- baseline goal from the physical predicates (engine's own rule) --
        goal = goal_from_predicates(preds)
        sources: List[RequirementSource] = []
        for req in sorted(goal.required_true):
            sources.append(RequirementSource(
                slot_id="(world)", transition="observed_predicates",
                requirement=req, reason="derived by the engine from the "
                                        "active predicate set"))
        for req in sorted(goal.required_false):
            sources.append(RequirementSource(
                slot_id="(world)", transition="observed_predicates",
                requirement=f"not:{req}",
                reason="derived by the engine from the active predicate set"))

        # --- semantic requirements from the constraint-state diff ----------
        for slot_id, (old_mode, new_mode, slot) in sorted(transitions.items()):
            kind = self.PHYSICAL_TRANSITIONS.get((old_mode, new_mode))
            if kind is None:
                continue
            extra, why = self._requirements_for(kind, slot)
            if extra is None:
                continue
            goal = goal.union(extra)
            for req in sorted(extra.required_true):
                sources.append(RequirementSource(
                    slot_id=slot_id,
                    transition=f"{old_mode.value}->{new_mode.value}",
                    requirement=req, reason=why))
            for req in sorted(extra.required_false):
                sources.append(RequirementSource(
                    slot_id=slot_id,
                    transition=f"{old_mode.value}->{new_mode.value}",
                    requirement=f"not:{req}", reason=why))

        for slot in inserted:
            goal = goal.union(RepairGoal(
                required_true=frozenset({"safe_clearance", "restore_valid"}),
                required_false=frozenset({"obstacle_present"}),
                label="safety_inserted"))
            sources.append(RequirementSource(
                slot_id=slot.id, transition="insert",
                requirement="safe_clearance",
                reason=f"new hard safety constraint {slot.grounding!r} must hold "
                       f"before the task may resume"))

        # A repair that is asked for nothing is not a repair. If the semantic
        # change imposes no physical requirement AND the world is undisturbed,
        # say so explicitly instead of running an empty pipeline.
        needs = bool(goal.required_true or goal.required_false)
        event = self._event(preds, transitions, event_id, step)
        if not needs:
            return RepairRequirements(
                event=event, predicates=preds, abstract_init=abstract_init,
                goal=goal, sources=sources, needs_physical_repair=False,
                note="semantic change imposes no physical requirement and the "
                     "world is undisturbed; no repair program is synthesised")

        label = "+".join(sorted({s.transition for s in sources
                                 if s.transition != "observed_predicates"})) \
            or goal.label
        goal = RepairGoal(required_true=goal.required_true,
                          required_false=goal.required_false, label=label)
        return RepairRequirements(event=event, predicates=preds,
                                  abstract_init=abstract_init, goal=goal,
                                  sources=sources, needs_physical_repair=True)

    # ------------------------------------------------------------------
    def _requirements_for(self, kind: str, slot
                          ) -> Tuple[Optional[RepairGoal], str]:
        if kind == "retarget":
            return (RepairGoal(
                required_true=frozenset({"aligned_to_current_target",
                                         "restore_valid"}),
                label="retarget"),
                f"goal {canonical_id(slot.id)} was re-grounded onto a new "
                f"target; the program must adopt the new target contract "
                f"before resuming")
        if kind == "suspend":
            # The goal is being SET ASIDE, not pursued through an obstruction.
            # The physical obligation is to end resumable -- put the held object
            # back at the captured handoff and stay ready -- not to clear
            # anything. Demanding `not obstacle_present` here would ask the
            # robot to remove a basket that was taken away by a person.
            return (RepairGoal(required_true=frozenset({"restore_valid"}),
                               label="suspend"),
                    f"goal {canonical_id(slot.id)} was suspended because its "
                    f"target is unavailable; the program must end in a state "
                    f"the remaining task can resume from")
        if kind == "cancel":
            return (RepairGoal(required_true=frozenset({"restore_valid"}),
                               label="cancel"),
                    f"goal {canonical_id(slot.id)} was cancelled; the program "
                    f"must still end in a state the remaining task can resume "
                    f"from")
        if kind == "restore":
            return (RepairGoal(required_true=frozenset({"restore_valid"}),
                               label="restore"),
                    f"goal {canonical_id(slot.id)} was restored; the resume "
                    f"contract must hold before the stage may continue")
        return None, ""

    # ------------------------------------------------------------------
    @staticmethod
    def _diff(before: ConstraintState, after: ConstraintState
              ) -> Dict[str, Tuple[SlotMode, SlotMode, Any]]:
        """Lifecycle transitions, keyed on CANONICAL id.

        Canonicalisation is what makes FSR-PC's re-minted ids comparable to
        CoPE's stable ids. Without it the diff would report every FSR-PC slot as
        brand new and the baseline would be handed different requirements --
        an unfair comparison created by bookkeeping rather than by method.
        """
        def live(state: ConstraintState) -> Dict[str, Any]:
            order = {SlotMode.ACTIVE: 0, SlotMode.SUSPENDED: 1,
                     SlotMode.OVERRIDDEN: 2, SlotMode.EXPIRED: 3}
            out: Dict[str, Any] = {}
            for sid in state.ids():
                s = state.get(sid)
                c = canonical_id(sid)
                cur = out.get(c)
                if cur is None or order[s.mode] < order[cur.mode]:
                    out[c] = s
            return out

        b, a = live(before), live(after)
        transitions: Dict[str, Tuple[SlotMode, SlotMode, Any]] = {}
        for cid, new in a.items():
            old = b.get(cid)
            if old is None:
                continue
            if old.mode is not new.mode:
                transitions[cid] = (old.mode, new.mode, new)
            elif (old.payload.get("target") != new.payload.get("target")
                  and new.mode is SlotMode.ACTIVE):
                # FSR-PC expresses a redirection by emitting the same goal with
                # a different target rather than by an Override edge. Treat it
                # as the same physical transition -- otherwise the baseline
                # would silently skip the retarget requirement.
                transitions[cid] = (SlotMode.ACTIVE, SlotMode.OVERRIDDEN, new)
        return transitions

    @staticmethod
    def _inserted_safety(before: ConstraintState, after: ConstraintState) -> List[Any]:
        old = {canonical_id(s) for s in before.ids()}
        return [after.get(sid) for sid in after.ids()
                if canonical_id(sid) not in old
                and after.get(sid).source is SlotSource.SAFETY_RULE]

    # ------------------------------------------------------------------
    def _predicates(self, ctx, world: Dict[str, Any],
                    transitions: Dict[str, Any]) -> WorldPredicates:
        """The shared predicate channel.

        Physical observations come from `ctx` exactly as the frozen engine's own
        env would report them. The semantic layer may additionally *assert* that
        the target changed, because a user redirection is a target relocation
        that no sensor can observe.
        """
        obstacle = bool(getattr(ctx, "obstacle_pos", None) is not None
                        and getattr(ctx, "clearance", float("inf"))
                        < self.target_move_threshold * 2)
        unsafe = obstacle
        slipped = not bool(getattr(ctx, "object_grasped", True))
        relocated = bool(getattr(ctx, "target_displacement", 0.0)
                         > self.target_move_threshold)
        relocated = relocated or any(
            new is SlotMode.OVERRIDDEN for _, (old, new, _) in transitions.items())
        # An unavailable target is NOT an obstacle: nothing blocks the robot,
        # the destination simply is not there. Reporting absence as
        # `obstacle_present` would oblige the planner to produce
        # `WaitUntilClear`, which the rollout verifier must then reject because
        # the obstruction never leaves.
        return WorldPredicates(
            obstacle_present=obstacle,
            unsafe_clearance=unsafe,
            object_slipped=slipped,
            target_relocated=relocated)

    @staticmethod
    def _event(preds: WorldPredicates, transitions: Dict[str, Any],
               event_id: str, step: int) -> Event:
        if preds.object_slipped:
            et = EventType.OBJECT_SLIP
        elif preds.target_relocated:
            et = EventType.TARGET_RELOCATION
        elif preds.obstacle_present:
            et = EventType.OBSTACLE_INTRUSION
        else:
            et = EventType.PERSISTENT_INFEASIBILITY
        severity = min(1.0, 0.25 * len(preds.active()) + 0.25 * len(transitions))
        return Event(event_type=et, severity=severity,
                     affected_entities=tuple(sorted(transitions)),
                     confidence=1.0, t=step, event_id=event_id,
                     payload={"transitions": {k: (o.value, n.value)
                                              for k, (o, n, _) in transitions.items()}})
