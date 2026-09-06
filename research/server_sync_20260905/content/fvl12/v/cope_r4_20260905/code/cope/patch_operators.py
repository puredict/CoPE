"""Typed patch operators and their side effects (memo §4).

Each operator's side effects follow the memo table exactly:

  Insert(c)               create slot (usually active); add node; append history
  Suspend(id)             mode=suspended; preserve priority snapshot + restore path
  Override(id_old,id_new) old -> overridden; add override edge
  Inherit(id)             leave active; RECORD the inheritance explicitly
  Expire(id)              mode=expired; prevent restore; keep trace
  Revalidate(id, check)   NO mode change; returns OK / DEGRADED / FAIL
  Restore(id)             mode=active IFF restore predicate AND validation pass
  Promote/Demote(id, p)   priority only; identity unchanged
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

from .constraint_slot import (
    ConstraintSlot, Lineage, Priority, RevalidationResult, SlotMode, SlotSource,
)
from .constraint_state import ConstraintState
from .patch import OpType, Patch, PatchOp


class PatchApplicationError(RuntimeError):
    """Raised when an operation cannot be applied to the current state."""


def _require(state: ConstraintState, sid: Optional[str]) -> ConstraintSlot:
    if sid is None or sid not in state.slots:
        raise PatchApplicationError(f"unknown target slot id {sid!r}")
    return state.slots[sid]


def apply_op(state: ConstraintState, op: PatchOp, patch_id: str,
             world: Dict[str, Any]) -> Tuple[ConstraintState, Dict[str, Any]]:
    """Apply one operation. Returns (new_state, record)."""
    rec: Dict[str, Any] = {"op": op.op.value, "target_id": op.target_id,
                           "reason": op.reason, "applied": True}

    # ---- Insert ------------------------------------------------------
    if op.op is OpType.INSERT:
        sid = op.new_slot_id or op.target_id
        if sid is None:
            raise PatchApplicationError("Insert requires a slot id")
        if sid in state.slots:
            raise PatchApplicationError(f"Insert: slot {sid!r} already exists")
        slot = ConstraintSlot(
            id=sid,
            grounding=op.args.get("grounding", sid),
            mode=SlotMode.ACTIVE,
            priority=op.args.get("priority", Priority.SOFT),
            source=op.args.get("source", SlotSource.EVENT_PATCH),
            validity=op.args.get("validity"),
            restore=op.args.get("restore"),
            payload=dict(op.args.get("payload", {})),
        ).with_edit(patch_id, "Insert", op.reason, mode=SlotMode.ACTIVE)
        return state.put(slot), {**rec, "new_slot_id": sid}

    # ---- Suspend -----------------------------------------------------
    if op.op is OpType.SUSPEND:
        s = _require(state, op.target_id)
        if s.mode is SlotMode.EXPIRED:
            raise PatchApplicationError(f"Suspend: {s.id} is expired")
        new = s.with_edit(patch_id, "Suspend", op.reason,
                          mode=SlotMode.SUSPENDED,
                          priority_snapshot=s.priority,
                          restore=op.args.get("restore", s.restore))
        return state.put(new), rec

    # ---- Override ----------------------------------------------------
    if op.op is OpType.OVERRIDE:
        old = _require(state, op.target_id)
        new_id = op.new_slot_id
        if new_id is None:
            raise PatchApplicationError("Override requires new_slot_id")
        st = state
        if new_id not in st.slots:                    # create the covering slot
            cover = ConstraintSlot(
                id=new_id, grounding=op.args.get("grounding", new_id),
                mode=SlotMode.ACTIVE,
                priority=op.args.get("priority", Priority.HARD),
                source=op.args.get("source", SlotSource.EVENT_PATCH),
                validity=op.args.get("validity"), restore=op.args.get("restore"),
                payload=dict(op.args.get("payload", {})),
            ).with_edit(patch_id, "Insert(cover)", op.reason, mode=SlotMode.ACTIVE)
            st = st.put(cover)
        cover = st.slots[new_id]
        cover = replace(cover, lineage=replace(
            cover.lineage, overrides=tuple(sorted(set(cover.lineage.overrides)
                                                  | {old.id}))))
        # Overriding a SUSPENDED slot must not lose the priority snapshot or the
        # restore predicate captured at suspension time -- otherwise a later
        # Restore would revive it with the wrong priority and no guard (I5).
        old_new = old.with_edit(
            patch_id, "Override", op.reason, mode=SlotMode.OVERRIDDEN,
            priority_snapshot=(old.priority_snapshot
                               if old.mode is SlotMode.SUSPENDED
                               else old.priority),
            lineage=replace(old.lineage, overridden_by=new_id))
        return st.put_many([cover, old_new]), {**rec, "new_slot_id": new_id}

    # ---- Inherit -----------------------------------------------------
    if op.op is OpType.INHERIT:
        s = _require(state, op.target_id)
        if s.mode is not SlotMode.ACTIVE:
            raise PatchApplicationError(
                f"Inherit: {s.id} is {s.mode.value}, not active")
        idx = int(op.args.get("patch_index", 0))
        new = s.with_edit(patch_id, "Inherit", op.reason,
                          lineage=replace(s.lineage,
                                          inherited_at=s.lineage.inherited_at + (idx,)))
        return state.put(new), rec

    # ---- Expire ------------------------------------------------------
    if op.op is OpType.EXPIRE:
        s = _require(state, op.target_id)
        new = s.with_edit(patch_id, "Expire", op.reason, mode=SlotMode.EXPIRED)
        return state.put(new), rec

    # ---- Revalidate (pure check; NO mode change) ----------------------
    if op.op is OpType.REVALIDATE:
        s = _require(state, op.target_id)
        result = s.revalidate(world)
        new = s.with_edit(patch_id, "Revalidate",
                          f"{op.reason} -> {result.value}", mode=s.mode)
        return state.put(new), {**rec, "result": result.value,
                                "mode_unchanged": True}

    # ---- Restore (state-changing commitment) --------------------------
    if op.op is OpType.RESTORE:
        s = _require(state, op.target_id)
        if s.mode is SlotMode.EXPIRED:
            return state, {**rec, "applied": False,
                           "refused": "expired slots are never restorable"}
        if not s.restorable:
            return state, {**rec, "applied": False,
                           "refused": f"mode {s.mode.value} is not restorable"}
        result = s.revalidate(world)
        if result is not RevalidationResult.OK:
            new = s.with_edit(patch_id, "Restore(refused)",
                              f"revalidation={result.value}", mode=s.mode)
            return state.put(new), {**rec, "applied": False,
                                    "refused": f"revalidation={result.value}",
                                    "result": result.value}
        st = state
        if s.lineage.overridden_by:                   # drop the override edge
            cov = st.slots.get(s.lineage.overridden_by)
            if cov is not None:
                st = st.put(replace(cov, lineage=replace(
                    cov.lineage,
                    overrides=tuple(x for x in cov.lineage.overrides
                                    if x != s.id))))
        new = s.with_edit(patch_id, "Restore", op.reason, mode=SlotMode.ACTIVE,
                          priority=s.priority_snapshot or s.priority,
                          lineage=replace(s.lineage, overridden_by=None))
        return st.put(new), {**rec, "result": result.value}

    # ---- Promote / Demote (optional) ----------------------------------
    if op.op in (OpType.PROMOTE, OpType.DEMOTE):
        s = _require(state, op.target_id)
        p = op.args.get("priority",
                        Priority.HARD if op.op is OpType.PROMOTE else Priority.SOFT)
        new = s.with_edit(patch_id, op.op.value, op.reason, priority=p)
        return state.put(new), {**rec, "priority": p.value}

    raise PatchApplicationError(f"unhandled operation {op.op!r}")


def apply_patch(state: ConstraintState, patch: Patch,
                world: Dict[str, Any]) -> Tuple[ConstraintState, List[Dict[str, Any]]]:
    """Apply a whole patch deterministically, in order."""
    st = state
    records: List[Dict[str, Any]] = []
    for op in patch.ops:
        st, rec = apply_op(st, op, patch.patch_id, world)
        records.append(rec)
    return st, records
