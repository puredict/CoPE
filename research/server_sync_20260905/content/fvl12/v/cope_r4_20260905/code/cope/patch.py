"""Typed patch: an ordered list of operations induced by an external event.

Memo §4:  P_t = [op_1, op_2, ..., op_k]
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class OpType(str, Enum):
    # first-paper subset
    INSERT = "Insert"
    SUSPEND = "Suspend"
    OVERRIDE = "Override"
    INHERIT = "Inherit"
    EXPIRE = "Expire"
    REVALIDATE = "Revalidate"
    RESTORE = "Restore"
    # optional, included only if a benchmark needs them
    PROMOTE = "Promote"
    DEMOTE = "Demote"


FIRST_PAPER_SUBSET = (OpType.INSERT, OpType.SUSPEND, OpType.OVERRIDE,
                      OpType.INHERIT, OpType.EXPIRE, OpType.REVALIDATE,
                      OpType.RESTORE)


@dataclass(frozen=True)
class PatchOp:
    op: OpType
    target_id: Optional[str] = None          # existing slot the op acts on
    new_slot_id: Optional[str] = None        # Insert / Override replacement
    args: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"op": self.op.value, "target_id": self.target_id,
                "new_slot_id": self.new_slot_id,
                "args": {k: v for k, v in self.args.items()
                         if not callable(v)},
                "reason": self.reason}


@dataclass(frozen=True)
class Patch:
    """A typed, minimal, auditable edit to the persistent constraint state."""
    patch_id: str
    ops: Tuple[PatchOp, ...]
    event_id: str = ""
    issued_at_step: int = 0
    rationale: str = ""

    def __len__(self) -> int:
        return len(self.ops)

    @property
    def touched_ids(self) -> Tuple[str, ...]:
        out = []
        for o in self.ops:
            for i in (o.target_id, o.new_slot_id):
                if i and i not in out:
                    out.append(i)
        return tuple(out)

    def to_dict(self) -> Dict[str, Any]:
        return {"patch_id": self.patch_id, "event_id": self.event_id,
                "issued_at_step": self.issued_at_step,
                "rationale": self.rationale,
                "n_ops": len(self.ops),
                "ops": [o.to_dict() for o in self.ops],
                "touched_ids": list(self.touched_ids)}


@dataclass(frozen=True)
class RegeneratedState:
    """FSR-PC's output: a COMPLETE new constraint state, not an edit.

    Kept in this module so both adaptation outputs are visible side by side and
    the structural difference is explicit.
    """
    regen_id: str
    slots: Tuple[Any, ...]                   # Tuple[ConstraintSlot, ...]
    event_id: str = ""
    issued_at_step: int = 0
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        # `slots` carries the full snapshot so the audit layer can diff
        # consecutive regenerations. Without it FSR-PC would be unable to answer
        # even the queries a state snapshot genuinely supports, and the audit
        # comparison would be circular.
        return {"regen_id": self.regen_id, "event_id": self.event_id,
                "issued_at_step": self.issued_at_step,
                "rationale": self.rationale,
                "n_slots_emitted": len(self.slots),
                "slot_ids": [s.id for s in self.slots],
                "slots": [{"id": s.id, "mode": s.mode.value,
                           "grounding": s.grounding,
                           "priority": s.priority.value,
                           "source": s.source.value,
                           "payload": {k: v for k, v in s.payload.items()
                                       if not callable(v)}}
                          for s in self.slots]}
