"""Invariant checks for a patch, run BEFORE it is applied (and after).

Four invariant families, per the task specification:
  identity     -- slot ids are stable; nothing is silently deleted or renamed
  lifecycle    -- only legal mode transitions; expired is terminal
  graph        -- override edges symmetric and acyclic
  restoration  -- Restore is preceded by Revalidate; expired never restored
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from .constraint_slot import SlotMode
from .constraint_state import ConstraintState
from .patch import OpType, Patch

# legal transitions; EXPIRED is terminal
LEGAL = {
    SlotMode.ACTIVE:     {SlotMode.ACTIVE, SlotMode.SUSPENDED,
                          SlotMode.OVERRIDDEN, SlotMode.EXPIRED},
    SlotMode.SUSPENDED:  {SlotMode.SUSPENDED, SlotMode.ACTIVE, SlotMode.EXPIRED},
    SlotMode.OVERRIDDEN: {SlotMode.OVERRIDDEN, SlotMode.ACTIVE, SlotMode.EXPIRED},
    SlotMode.EXPIRED:    {SlotMode.EXPIRED},
}


@dataclass
class ValidationReport:
    ok: bool = True
    identity_ok: bool = True
    lifecycle_ok: bool = True
    graph_ok: bool = True
    restoration_ok: bool = True
    violations: List[str] = field(default_factory=list)

    def fail(self, family: str, msg: str) -> None:
        setattr(self, f"{family}_ok", False)
        self.ok = False
        self.violations.append(f"{family}: {msg}")

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def validate_patch(state: ConstraintState, patch: Patch) -> ValidationReport:
    """Pre-application static checks."""
    r = ValidationReport()
    revalidated: set = set()
    for op in patch.ops:
        tid = op.target_id
        if op.op is OpType.INSERT:
            sid = op.new_slot_id or tid
            if sid in state.slots:
                r.fail("identity", f"Insert would clobber existing id {sid!r}")
            continue
        if tid is None or tid not in state.slots:
            r.fail("identity", f"{op.op.value} targets unknown id {tid!r}")
            continue
        cur = state.slots[tid]
        if op.op is OpType.REVALIDATE:
            revalidated.add(tid)
        if op.op is OpType.RESTORE:
            if cur.mode is SlotMode.EXPIRED:
                r.fail("restoration", f"Restore of expired slot {tid!r}")
            if tid not in revalidated:
                r.fail("restoration",
                       f"Restore({tid!r}) not preceded by Revalidate({tid!r})")
            if not cur.restorable:
                r.fail("lifecycle",
                       f"Restore({tid!r}) from non-restorable mode {cur.mode.value}")
        want = {OpType.SUSPEND: SlotMode.SUSPENDED,
                OpType.OVERRIDE: SlotMode.OVERRIDDEN,
                OpType.EXPIRE: SlotMode.EXPIRED,
                OpType.RESTORE: SlotMode.ACTIVE}.get(op.op)
        if want is not None and want not in LEGAL[cur.mode]:
            r.fail("lifecycle",
                   f"illegal transition {cur.mode.value} -> {want.value} for {tid!r}")
        if op.op is OpType.INHERIT and cur.mode is not SlotMode.ACTIVE:
            r.fail("lifecycle", f"Inherit({tid!r}) but mode is {cur.mode.value}")
    return r


def validate_state(before: ConstraintState, after: ConstraintState
                   ) -> ValidationReport:
    """Post-application checks on the resulting state."""
    r = ValidationReport()
    for sid in before.ids():
        if sid not in after.slots:
            r.fail("identity", f"slot {sid!r} disappeared (deletion is forbidden)")
    for sid, s in after.slots.items():
        old = before.get(sid)
        if old is not None and s.mode is not old.mode:
            if s.mode not in LEGAL[old.mode]:
                r.fail("lifecycle",
                       f"{sid}: {old.mode.value} -> {s.mode.value} is illegal")
        if old is not None and len(s.history) < len(old.history):
            r.fail("identity", f"{sid}: history is not monotonic")
    if not after.graph_consistent():
        r.fail("graph", "override edges are asymmetric or cyclic")
    return r


def is_regenerated_state_valid(before: ConstraintState, after: ConstraintState
                               ) -> ValidationReport:
    """Validation applied to FSR-PC output.

    FSR-PC emits a COMPLETE state, so identity preservation is *not* required by
    construction -- it is exactly what we measure. We therefore check only the
    invariants a regenerated state must still satisfy to be executable.
    """
    r = ValidationReport()
    if not after.graph_consistent():
        r.fail("graph", "override edges are asymmetric or cyclic")
    for sid, s in after.slots.items():
        if s.mode is SlotMode.OVERRIDDEN and not s.lineage.overridden_by:
            r.fail("graph", f"{sid} is overridden but has no covering slot")
    return r
