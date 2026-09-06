"""Recovery manager --- the adapter between the CoPE semantic layer and the
EXISTING repair execution layer.

Two-layer design (per the clarification):

    CoPE semantic layer        persistent constraint state + typed local patching
                                        |  (this module)
    repair execution layer     continuation capture -> operator synthesis ->
                               legality -> sequential rollout verification ->
                               splice -> restore -> resume

**Nothing in `rekep_repair/` is replaced or duplicated.** This module only
*maps* between representations:

    ConstraintSlot(mode=SUSPENDED)  <->  TaskProgram stage suspension
    Patch                           ->   repair goal / operator sequence
    Continuation                    <->  slot restore predicate + lineage

The repair engine remains the sole owner of execution, verification and
splicing. If no execution engine is supplied, the manager operates in
semantic-only mode (used by the CPU tests and the dry-run).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .constraint_slot import ConstraintSlot, SlotMode
from .constraint_state import ConstraintState
from .patch import OpType, Patch
from .state_store import StateStore


@dataclass
class ExecutorRequest:
    """The compiled, method-neutral request handed to the downstream executor.

    Both CoPEPatchPolicy and FSRPCPolicy produce this SAME structure; the
    executor cannot tell which policy produced it. That is the fairness
    guarantee at the interface.
    """
    active_goals: List[Dict[str, Any]]
    safety_constraints: List[Dict[str, Any]]
    horizon_steps: int
    budget: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"active_goals": self.active_goals,
                "safety_constraints": self.safety_constraints,
                "horizon_steps": self.horizon_steps,
                "budget": dict(self.budget)}

    def fingerprint(self) -> str:
        import hashlib, json
        return hashlib.blake2b(
            json.dumps(self.to_dict(), sort_keys=True, default=str).encode(),
            digest_size=8).hexdigest()


class RecoveryManager:
    """Compiles active slots into an ExecutorRequest AND drives the frozen
    repair engine for the physical recovery.

    `enter_repair_pipeline()` is the single shared entry point. Both
    `CoPEPatchPolicy` and `FSRPCPolicy` call it with the identical signature
    immediately after producing their state update, and from that call onwards
    the code path is byte-identical. This is what makes "FSR-PC uses the same
    downstream stack" a structural property rather than a promise.
    """

    def __init__(self, store: StateStore, horizon_steps: int = 900,
                 repair_engine: Optional[Any] = None):
        self.store = store
        self.horizon_steps = horizon_steps
        # a `SharedRepairEngine`. When absent the manager runs in semantic-only
        # mode, which the pipeline audit reports as INCOMPLETE rather than
        # silently accepting.
        self.repair_engine = repair_engine
        self.repair_outcomes: List[Any] = []

    # ---- the shared physical-adaptation entry point --------------------
    def enter_repair_pipeline(self, *, before, after, adaptation,
                              adaptation_kind: str, world: Dict[str, Any],
                              event_id: str, step: int) -> Optional[Any]:
        """Capture -> compile goal -> synthesise -> verify -> select -> splice
        -> execute -> revalidate -> restore -> resume.

        Policy-blind: everything it needs is the state transition and the world.
        `adaptation_kind` only chooses the PATCH vs REGENERATION trace marker.
        """
        if self.repair_engine is None:
            self.store.trace.record(
                "repair_engine_absent", event_id=event_id,
                note="semantic-only mode: no physical repair was performed")
            return None
        # Semantic intent the world predicates cannot express: which goal was
        # cancelled, which preserved, which suspended. Recorded alongside the
        # compiled repair goal so the audit can answer "why did the robot have
        # to do that?", not only "what did it do?".
        if isinstance(adaptation, Patch):
            self.store.trace.record("semantic_intent", event_id=event_id,
                                    **self.patch_to_repair_goal(adaptation))
        intents = {sid: self.slot_to_repair_intent(after.get(sid))
                   for sid in after.ids()
                   if self.slot_to_repair_intent(after.get(sid)) is not None}
        if intents:
            self.store.trace.record("slot_repair_intents", event_id=event_id,
                                    intents=intents)

        ctx = self.repair_engine.env.observe()
        out = self.repair_engine.repair(
            before=before, after=after, adaptation=adaptation,
            adaptation_kind=adaptation_kind, world=world, ctx=ctx,
            event_id=event_id, step=step)
        out = self.repair_engine.drive_repair(out)
        self.repair_outcomes.append(out)
        return out

    # ---- semantic -> executor ----------------------------------------
    def compile(self, budget: Optional[Dict[str, Any]] = None) -> ExecutorRequest:
        goals, safety = [], []
        for s in self.store.compile_active():
            item = {"id": s.id, "grounding": s.grounding,
                    "priority": s.priority.value, "source": s.source.value,
                    **{k: v for k, v in s.payload.items() if not callable(v)}}
            (safety if s.source.value == "safety_rule" else goals).append(item)
        return ExecutorRequest(active_goals=goals, safety_constraints=safety,
                               horizon_steps=self.horizon_steps,
                               budget=dict(budget or {}))

    # ---- CoPE slot lifecycle <-> repair-engine concepts ---------------
    @staticmethod
    def slot_to_repair_intent(slot: ConstraintSlot) -> Optional[str]:
        """Map a slot's lifecycle mode onto the repair layer's vocabulary.

        This is the *only* semantic coupling; the repair layer keeps its own
        typed operators (Suspend/Stabilize/Retreat/.../Resume) unchanged.
        """
        return {SlotMode.SUSPENDED: "Suspend",
                SlotMode.OVERRIDDEN: "Override",
                SlotMode.ACTIVE: None,
                SlotMode.EXPIRED: "Expire"}.get(slot.mode)

    def patch_to_repair_goal(self, patch: Patch) -> Dict[str, Any]:
        """Summarise a patch as a repair goal for the existing engine.

        Deliberately thin: the repair engine derives its own abstract goal from
        world predicates. This only carries the *semantic* intent that the
        predicates cannot express (which goal was cancelled, which preserved).
        """
        return {
            "patch_id": patch.patch_id,
            "cancelled": [o.target_id for o in patch.ops if o.op is OpType.EXPIRE],
            "suspended": [o.target_id for o in patch.ops if o.op is OpType.SUSPEND],
            "preserved": [o.target_id for o in patch.ops if o.op is OpType.INHERIT],
            "inserted": [o.new_slot_id for o in patch.ops if o.op is OpType.INSERT],
            "restored": [o.target_id for o in patch.ops if o.op is OpType.RESTORE],
        }

    # ---- guarded revalidation + restoration ---------------------------
    def guarded_restore(self, slot_id: str, world: Dict[str, Any],
                        patch_id: str = "auto-restore") -> Dict[str, Any]:
        """Revalidate THEN restore --- never restore blindly.

        Returns the decision record. Implements the memo's separation of
        Revalidate (pure check) from Restore (state-changing commitment).
        """
        from .patch import Patch as _P, PatchOp as _Op
        slot = self.store.state.get(slot_id)
        if slot is None:
            return {"slot_id": slot_id, "restored": False,
                    "reason": "unknown slot"}
        result = slot.revalidate(world)
        patch = _P(patch_id=patch_id, ops=(
            _Op(OpType.REVALIDATE, target_id=slot_id,
                reason="pre-restore grounding check"),
            _Op(OpType.RESTORE, target_id=slot_id,
                reason="restore after successful revalidation"),
        ), rationale="guarded restoration")
        ok, rep = self.store.apply_patch(patch, world)
        now = self.store.state.get(slot_id)
        return {"slot_id": slot_id,
                "revalidation": result.value,
                "restored": bool(now and now.mode is SlotMode.ACTIVE),
                "validation_ok": ok,
                "violations": rep.violations}

    # ---- nominal execution -------------------------------------------
    def execute(self, request: ExecutorRequest, executor: Any) -> Dict[str, Any]:
        """Run NOMINAL (uninterrupted) work through the shared executor.

        This is deliberately *not* the repair path. An interruption goes through
        `enter_repair_pipeline()`, which drives the frozen synthesis ->
        verification -> splice -> restore -> resume engine. Calling this method
        alone would execute the task without ever repairing it -- exactly the
        gap the v1 audit identified -- so the benchmark harness calls it only
        between interruptions, and `assert_complete()` on the pipeline markers
        is what proves the repair path was actually taken.
        """
        return executor.run(request)
