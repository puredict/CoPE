"""CoPEPatchPolicy --- persistent constraint state edited by minimal typed patches.

At an interruption:
  1. read the EXISTING persistent constraint state (nothing is thrown away);
  2. generate a minimal typed patch;
  3. validate identity / lifecycle / graph / restoration invariants;
  4. apply the patch deterministically;
  5. compile the ACTIVE slots into the downstream executor representation;
  6. execute (same executor as FSR-PC);
  7. guarded revalidation and restoration.

The patch generator here is a deterministic symbolic rule set, not an LLM: the
scientific question is whether *persistent local editing* beats *full
regeneration*, so both arms use the same deterministic planner and neither gets
a language-model advantage.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..constraint_slot import (
    ConstraintSlot, Priority, SlotMode, SlotSource,
)
from ..patch import OpType, Patch, PatchOp
from ..recovery_manager import ExecutorRequest, RecoveryManager
from ..naming import canonical_id
from ..state_store import StateStore
from .adaptation_input import AdaptationInput


class CoPEPatchPolicy:
    name = "CoPE"

    def __init__(self, store: StateStore, horizon_steps: int = 900,
                 repair_engine: Optional[Any] = None):
        self.store = store
        self.mgr = RecoveryManager(store, horizon_steps, repair_engine)
        self.n_model_calls = 0
        self.n_slots_edited = 0
        self.n_slots_emitted = 0        # CoPE emits patches, not whole states
        self.patches: List[Patch] = []
        self.last_validation = None
        self.last_repair = None

    # ------------------------------------------------------------------
    def generate_patch(self, inp: AdaptationInput) -> Patch:
        """Emit the MINIMAL typed patch that realises the user's update.

        Only slots the update actually concerns are touched. Completed goals are
        explicitly Inherited (carried forward and recorded), never re-planned.
        """
        upd = inp.world_state.get("update", {})
        ops: List[PatchOp] = []
        pid = f"patch-{inp.event_id or 'e'}-{inp.event_step}"

        find = self.store.state.find_canonical

        # 1. explicitly preserve completed progress (auditable inheritance)
        for gid in inp.completed_goals:
            s = find(gid)
            if s is not None and s.mode is SlotMode.ACTIVE:
                ops.append(PatchOp(OpType.INHERIT, target_id=s.id,
                                   args={"patch_index": inp.event_step},
                                   reason="completed goal preserved across interruption"))

        # 2. cancellations -> Expire (soft delete; auditable, never restorable)
        for gid in upd.get("cancel", []):
            s = find(gid)
            if s is not None and s.mode is not SlotMode.EXPIRED:
                ops.append(PatchOp(OpType.EXPIRE, target_id=s.id,
                                   reason=upd.get("cancel_reason",
                                                  "user cancelled this goal")))

        # 3. redirections -> Override the old goal with a re-grounded slot
        for gid, new_target in upd.get("redirect", {}).items():
            old = find(gid)
            if old is None or old.mode is SlotMode.EXPIRED:
                continue
            obj = old.payload.get("object", canonical_id(old.id))
            new_id = f"{canonical_id(old.id)}@{new_target}"
            if new_id == old.id:
                continue                      # already grounded on that target
            ops.append(PatchOp(
                OpType.OVERRIDE, target_id=old.id, new_slot_id=new_id,
                args={"grounding": f"place_{obj}_in_{new_target}",
                      "priority": old.priority, "source": SlotSource.EVENT_PATCH,
                      "payload": {**old.payload, "target": new_target,
                                  # keep the pre-detour grounding so a later
                                  # withdrawal can revert to it (I5)
                                  "original_target": old.payload.get(
                                      "original_target",
                                      old.payload.get("target"))}},
                reason=f"user redirected {canonical_id(old.id)} to {new_target}"))

        # 4. temporary unavailability -> Suspend with an explicit restore predicate
        for gid in upd.get("suspend", []):
            old = find(gid)
            if old is None or old.mode is not SlotMode.ACTIVE:
                continue
            tgt = old.payload.get("target")
            ops.append(PatchOp(
                OpType.SUSPEND, target_id=old.id,
                args={"restore": _target_available(tgt)},
                reason=upd.get("suspend_reason",
                               f"target {tgt} temporarily unavailable")))

        # 4b. a withdrawn temporary redirection (I5): Expire the covering slot
        #     so the ORIGINAL grounding becomes the restorable one again. The
        #     original is left OVERRIDDEN here; the Restore below revives it
        #     after revalidation, which is what makes lineage load-bearing.
        for cover_id in upd.get("cancel_redirect", []):
            cover = self.store.state.get(cover_id) or find(cover_id)
            if cover is None or cover.mode is SlotMode.EXPIRED:
                continue
            ops.append(PatchOp(
                OpType.EXPIRE, target_id=cover.id,
                reason=upd.get("cancel_reason",
                               "user withdrew the temporary redirection")))

        # 5. new safety constraints -> Insert
        for c in upd.get("insert_safety", []):
            ops.append(PatchOp(
                OpType.INSERT, new_slot_id=c["id"],
                args={"grounding": c.get("grounding", c["id"]),
                      "priority": Priority.HARD,
                      "source": SlotSource.SAFETY_RULE,
                      "payload": c.get("payload", {})},
                reason=c.get("reason", "event-induced safety constraint")))

        # 6. guarded restoration -> Revalidate THEN Restore (never blind)
        expiring = {c for c in upd.get("cancel_redirect", [])}
        for gid in upd.get("restore", []):
            s = find(gid)
            # If the covering slot is being expired in this same patch, the
            # restorable version is the ORIGINAL, not the cover that `find`
            # prefers while it is still active.
            if s is not None and s.id in expiring:
                origin = next((self.store.state.get(o)
                               for o in s.lineage.overrides
                               if self.store.state.get(o) is not None), None)
                s = origin or s
            if s is None:
                continue
            ops.append(PatchOp(OpType.REVALIDATE, target_id=s.id,
                               reason="check grounding still valid before restore"))
            ops.append(PatchOp(OpType.RESTORE, target_id=s.id,
                               reason="restore after successful revalidation"))

        return Patch(patch_id=pid, ops=tuple(ops), event_id=inp.event_id,
                     issued_at_step=inp.event_step,
                     rationale="minimal typed edit of the persistent state")

    # ------------------------------------------------------------------
    def adapt(self, inp: AdaptationInput) -> ExecutorRequest:
        before_fp = self.store.state.fingerprint()
        before_ids = set(self.store.state.ids())
        before_state = self.store.state          # C_t, captured before Apply

        patch = self.generate_patch(inp)
        self.n_model_calls += 1          # one deterministic patch-generation call
        self.patches.append(patch)
        self.store.trace.record("patch_generated", **patch.to_dict())

        ok, rep = self.store.apply_patch(patch, inp.world_state)
        self.last_validation = rep
        if not ok:
            self.store.trace.record("patch_rejected", patch_id=patch.patch_id,
                                    violations=rep.violations)
            # invariant violation -> do NOT mutate; fall back to current state
            return self.mgr.compile(budget=inp.compute_budget)

        # progress preservation is recorded explicitly for the audit queries
        for gid in inp.completed_goals:
            self.store.trace.record("progress_preserved", slot_id=gid,
                                    method="CoPE")

        # ---- hand off to the SHARED downstream stack -----------------------
        # From here the code path is identical to FSR-PC's: continuation
        # capture, repair-goal compilation, runtime synthesis, sequential
        # rollout verification, hard rejection, splice, restore, resume.
        self.last_repair = self.mgr.enter_repair_pipeline(
            before=before_state, after=self.store.state, adaptation=patch,
            adaptation_kind="patch", world=inp.world_state,
            event_id=inp.event_id, step=inp.event_step)

        self.n_slots_edited += len(patch.touched_ids)
        after_ids = set(self.store.state.ids())
        self.store.trace.record(
            "adaptation_summary", method="CoPE", patch_id=patch.patch_id,
            n_ops=len(patch.ops), n_slots_edited=len(patch.touched_ids),
            n_slots_emitted=0, n_slots_total=len(after_ids),
            identity_preserved=before_ids.issubset(after_ids),
            state_fp_before=before_fp,
            state_fp_after=self.store.state.fingerprint())
        return self.mgr.compile(budget=inp.compute_budget)

    # ------------------------------------------------------------------
    def guarded_restore(self, slot_id: str, world: Dict[str, Any]) -> Dict[str, Any]:
        return self.mgr.guarded_restore(slot_id, world)


def _target_available(target: Optional[str]):
    """Restore predicate: the suspended goal's target must be available again."""
    def pred(world: Dict[str, Any]) -> bool:
        unavailable = set(world.get("unavailable_targets", []) or [])
        return target is not None and target not in unavailable
    return pred
