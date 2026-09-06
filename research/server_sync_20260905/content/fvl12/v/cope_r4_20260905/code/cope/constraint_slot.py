"""CoPE constraint slot.

Implements the slot schema of the CoPE / RCSP memo (Jingsu Li, v0.3, 2026-04-26,
§3.1):

    c_i = (id, omega, mode, priority, source, validity, restore, lineage, history)

The point of the schema, quoting the memo's intent: a constraint is not only a
mathematical function but a software-engineering object with identity,
lifecycle, relations and edit history. ``omega`` (the grounding) is only one
field.

Lifecycle modes (memo §3.2) separate *existence* from *participation*:
  active      -- participates in planning/control
  suspended   -- temporarily disabled, still exists, may be restored
  overridden  -- covered by another specific slot, with a relation in the graph
  expired     -- permanently invalid in this task context, still auditable
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class SlotMode(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    OVERRIDDEN = "overridden"
    EXPIRED = "expired"


class SlotSource(str, Enum):
    INITIAL_TASK = "initial_task"
    USER_PREFERENCE = "user_preference"
    SAFETY_RULE = "safety_rule"
    EVENT_PATCH = "event_patch"
    LEARNED_RULE = "learned_rule"


class Priority(str, Enum):
    HARD = "hard"          # safety; must not be traded away
    SOFT = "soft"          # preference


class RevalidationResult(str, Enum):
    """Memo §4: Revalidate returns OK / DEGRADED / FAIL and does NOT change mode."""
    OK = "OK"
    DEGRADED = "DEGRADED"
    FAIL = "FAIL"


# A grounding/validity/restore predicate over the world state.
Predicate = Callable[[Dict[str, Any]], bool]


@dataclass(frozen=True)
class Lineage:
    """Relations to other slots and patches (memo: dependency, override,
    inheritance, replacement)."""
    overrides: Tuple[str, ...] = ()        # this slot covers these
    overridden_by: Optional[str] = None    # this slot is covered by that one
    derived_from: Optional[str] = None     # replacement / re-grounding ancestor
    inherited_at: Tuple[int, ...] = ()     # patch indices that explicitly carried it
    depends_on: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {"overrides": list(self.overrides), "overridden_by": self.overridden_by,
                "derived_from": self.derived_from,
                "inherited_at": list(self.inherited_at),
                "depends_on": list(self.depends_on)}


@dataclass(frozen=True)
class SlotEdit:
    """One entry of the slot-local edit log."""
    seq: int                 # monotonically increasing per slot
    patch_id: str
    operation: str
    detail: str = ""
    mode_before: Optional[SlotMode] = None
    mode_after: Optional[SlotMode] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"seq": self.seq, "patch_id": self.patch_id,
                "operation": self.operation, "detail": self.detail,
                "mode_before": self.mode_before.value if self.mode_before else None,
                "mode_after": self.mode_after.value if self.mode_after else None}


@dataclass(frozen=True)
class ConstraintSlot:
    """A persistent, lifecycle-bearing constraint."""

    id: str
    grounding: str                                   # symbolic name of omega
    mode: SlotMode = SlotMode.ACTIVE
    priority: Priority = Priority.SOFT
    source: SlotSource = SlotSource.INITIAL_TASK
    validity: Optional[Predicate] = None             # when the grounding holds
    restore: Optional[Predicate] = None              # when a suspended slot may return
    lineage: Lineage = field(default_factory=Lineage)
    history: Tuple[SlotEdit, ...] = ()
    # task payload the downstream executor needs (goal object, target, ...)
    payload: Dict[str, Any] = field(default_factory=dict)
    priority_snapshot: Optional[Priority] = None     # taken on Suspend

    # --- queries -------------------------------------------------------
    @property
    def participates(self) -> bool:
        """Only ACTIVE slots are compiled into the downstream representation."""
        return self.mode is SlotMode.ACTIVE

    @property
    def restorable(self) -> bool:
        """EXPIRED is a soft delete: auditable but never restorable."""
        return self.mode in (SlotMode.SUSPENDED, SlotMode.OVERRIDDEN)

    def check_validity(self, world: Dict[str, Any]) -> bool:
        return True if self.validity is None else bool(self.validity(world))

    def check_restore(self, world: Dict[str, Any]) -> bool:
        return True if self.restore is None else bool(self.restore(world))

    def revalidate(self, world: Dict[str, Any]) -> RevalidationResult:
        """Pure check; never mutates. Memo §4: separate from Restore."""
        if self.mode is SlotMode.EXPIRED:
            return RevalidationResult.FAIL
        if not self.check_validity(world):
            return RevalidationResult.FAIL
        if not self.check_restore(world):
            return RevalidationResult.DEGRADED
        return RevalidationResult.OK

    # --- edits (always return a NEW slot; slots are immutable) ----------
    def with_edit(self, patch_id: str, operation: str, detail: str = "",
                  **changes) -> "ConstraintSlot":
        before = self.mode
        after = changes.get("mode", self.mode)
        edit = SlotEdit(seq=len(self.history) + 1, patch_id=patch_id,
                        operation=operation, detail=detail,
                        mode_before=before, mode_after=after)
        return replace(self, history=self.history + (edit,), **changes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "grounding": self.grounding, "mode": self.mode.value,
            "priority": self.priority.value, "source": self.source.value,
            "has_validity": self.validity is not None,
            "has_restore": self.restore is not None,
            "lineage": self.lineage.to_dict(),
            "history": [e.to_dict() for e in self.history],
            "payload": dict(self.payload),
            "priority_snapshot": (self.priority_snapshot.value
                                  if self.priority_snapshot else None),
        }
