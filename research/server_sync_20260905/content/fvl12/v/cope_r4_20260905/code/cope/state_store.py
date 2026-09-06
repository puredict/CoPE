"""State store: maintains S_t (constraint state), G_t (relations) and H_t (history).

Memo §"State store: maintains S_t, G_t, and H_t".
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .audit_trace import AuditTrace
from .constraint_state import ConstraintState
from .constraint_slot import ConstraintSlot, SlotMode
from .patch import Patch, RegeneratedState
from .patch_operators import apply_patch
from .patch_validator import (
    ValidationReport, is_regenerated_state_valid, validate_patch, validate_state,
)


@dataclass
class StateStore:
    state: ConstraintState = field(default_factory=ConstraintState)
    trace: AuditTrace = field(default_factory=AuditTrace)
    history: List[Dict[str, Any]] = field(default_factory=list)

    # --- CoPE path: local typed patch ----------------------------------
    def apply_patch(self, patch: Patch, world: Dict[str, Any]
                    ) -> Tuple[bool, ValidationReport]:
        before = self.state
        pre = validate_patch(before, patch)
        self.trace.record("patch_validate", patch_id=patch.patch_id,
                          ok=pre.ok, violations=pre.violations)
        if not pre.ok:
            return False, pre
        after, records = apply_patch(before, patch, world)
        for op, rec in zip(patch.ops, records):
            self.trace.record("op", patch_id=patch.patch_id, **rec)
        post = validate_state(before, after)
        self.trace.record("state_validate", patch_id=patch.patch_id,
                          ok=post.ok, violations=post.violations)
        if not post.ok:
            return False, post
        self.state = after
        self.history.append({"kind": "patch", "patch_id": patch.patch_id,
                             "n_ops": len(patch.ops),
                             "before_fp": before.fingerprint(),
                             "after_fp": after.fingerprint(),
                             "n_slots_before": len(before.slots),
                             "n_slots_after": len(after.slots),
                             "touched": list(patch.touched_ids)})
        return True, post

    # --- FSR-PC path: complete regenerated state ------------------------
    def install_regenerated(self, regen: RegeneratedState
                            ) -> Tuple[bool, ValidationReport]:
        before = self.state
        after = ConstraintState(slots={s.id: s for s in regen.slots},
                                version=before.version + 1)
        rep = is_regenerated_state_valid(before, after)
        self.trace.record("regen_validate", regen_id=regen.regen_id,
                          ok=rep.ok, violations=rep.violations,
                          n_slots_emitted=len(regen.slots))
        if not rep.ok:
            return False, rep
        self.state = after
        self.history.append({"kind": "regenerate", "regen_id": regen.regen_id,
                             "n_ops": 0,
                             "n_slots_emitted": len(regen.slots),
                             "before_fp": before.fingerprint(),
                             "after_fp": after.fingerprint(),
                             "n_slots_before": len(before.slots),
                             "n_slots_after": len(after.slots),
                             "touched": [s.id for s in regen.slots]})
        return True, rep

    # --- shared -------------------------------------------------------
    def seed(self, slots: List[ConstraintSlot]) -> None:
        self.state = self.state.put_many(slots)
        self.trace.record("seed", slot_ids=[s.id for s in slots])

    def compile_active(self) -> List[ConstraintSlot]:
        """The ONLY interface the downstream executor sees.

        Identical for both policies -- this is what keeps the comparison fair.
        """
        return sorted(self.state.active(), key=lambda s: s.id)

    def history_monotonic(self) -> bool:
        for s in self.state.slots.values():
            seqs = [e.seq for e in s.history]
            if seqs != sorted(seqs) or len(set(seqs)) != len(seqs):
                return False
        return True
