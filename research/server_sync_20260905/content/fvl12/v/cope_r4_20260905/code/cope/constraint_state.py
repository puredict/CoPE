"""The persistent constraint state S_t plus the relation graph G_t.

Memo: "task execution is represented as a persistent, editable constraint
state". Slots are never deleted -- Expire is a soft delete that preserves the
audit record.
"""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .constraint_slot import ConstraintSlot, SlotMode


@dataclass(frozen=True)
class ConstraintState:
    slots: Dict[str, ConstraintSlot] = field(default_factory=dict)
    version: int = 0

    # --- queries -------------------------------------------------------
    def get(self, sid: str) -> Optional[ConstraintSlot]:
        return self.slots.get(sid)

    def active(self) -> List[ConstraintSlot]:
        return [s for s in self.slots.values() if s.participates]

    def by_mode(self, mode: SlotMode) -> List[ConstraintSlot]:
        return [s for s in self.slots.values() if s.mode is mode]

    def ids(self) -> List[str]:
        return sorted(self.slots)

    def find_canonical(self, canon: str) -> Optional[ConstraintSlot]:
        """Resolve a canonical task id (e.g. `g_butter`) to the live slot.

        Prefers ACTIVE, then SUSPENDED, then OVERRIDDEN, then EXPIRED, so that a
        later edit addresses the slot that is currently carrying the task, not a
        superseded record. Available to BOTH policies (see `cope/naming.py`).
        """
        from .naming import canonical_id
        order = {SlotMode.ACTIVE: 0, SlotMode.SUSPENDED: 1,
                 SlotMode.OVERRIDDEN: 2, SlotMode.EXPIRED: 3}
        cands = [s for s in self.slots.values()
                 if canonical_id(s.id) == canonical_id(canon)]
        if not cands:
            return None
        return sorted(cands, key=lambda s: (order[s.mode], s.id))[0]

    # --- functional updates (state is immutable) -----------------------
    def put(self, slot: ConstraintSlot) -> "ConstraintState":
        d = dict(self.slots); d[slot.id] = slot
        return ConstraintState(slots=d, version=self.version + 1)

    def put_many(self, slots: Iterable[ConstraintSlot]) -> "ConstraintState":
        d = dict(self.slots)
        for s in slots:
            d[s.id] = s
        return ConstraintState(slots=d, version=self.version + 1)

    # --- graph relations ----------------------------------------------
    def override_edges(self) -> List[Tuple[str, str]]:
        out = []
        for s in self.slots.values():
            if s.lineage.overridden_by:
                out.append((s.lineage.overridden_by, s.id))
        return sorted(out)

    def graph_consistent(self) -> bool:
        """Every override edge must be symmetric and acyclic."""
        for s in self.slots.values():
            nb = s.lineage.overridden_by
            if nb is not None:
                cov = self.slots.get(nb)
                if cov is None or s.id not in cov.lineage.overrides:
                    return False
                if nb == s.id:
                    return False
        # acyclicity of the override relation
        seen, stack = set(), []
        def walk(node, path):
            if node in path:
                return False
            path = path | {node}
            cur = self.slots.get(node)
            if cur is None:
                return True
            return all(walk(o, path) for o in cur.lineage.overrides)
        return all(walk(sid, frozenset()) for sid in self.slots)

    def to_dict(self) -> Dict[str, Any]:
        return {"version": self.version,
                "n_slots": len(self.slots),
                "n_active": len(self.active()),
                "slots": {k: v.to_dict() for k, v in sorted(self.slots.items())},
                "override_edges": self.override_edges()}

    def fingerprint(self) -> str:
        """Stable hash of the participating configuration (for churn metrics)."""
        import hashlib, json
        payload = [(s.id, s.mode.value, s.priority.value, s.grounding,
                    json.dumps(s.payload, sort_keys=True, default=str))
                   for s in sorted(self.slots.values(), key=lambda x: x.id)]
        return hashlib.blake2b(json.dumps(payload).encode(),
                               digest_size=8).hexdigest()
