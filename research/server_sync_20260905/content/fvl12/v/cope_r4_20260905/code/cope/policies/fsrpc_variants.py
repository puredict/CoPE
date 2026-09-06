"""Diagnostic FSR-PC variants.

The v2 pilot showed CoPE's measured differences split into a *definitional*
group (identity, edit distance -- true by construction) and one *empirical*
group (audit coverage). These variants decompose the audit advantage so we can
say which ingredient actually produces it:

    FSR-PC                full regeneration, re-minted ids, no provenance
    FSR-PC_stable_ids     full regeneration, ids mapped back when unambiguous
    FSR-PC_provenance     full regeneration + explicit reason / source_event /
                          predecessor / replacement relation / restoration
                          condition

If `FSR-PC_provenance` closes the audit gap, the advantage comes from recording
provenance, not from local editing, and the paper must say so. If it does not,
the advantage is attributable to persistent local editing itself.

**Neither variant is weakened.** Both still regenerate the COMPLETE state, both
receive the identical `AdaptationInput`, the identical compute budget, and the
identical downstream repair stack. Neither may call CoPE patch application:
`assert_no_patch_application()` is asserted by a test.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional

from ..constraint_slot import ConstraintSlot, Lineage, SlotEdit, SlotMode
from ..naming import canonical_id
from ..patch import RegeneratedState
from .adaptation_input import AdaptationInput
from .fsrpc_policy import FSRPCPolicy


class FSRPCStableIdsPolicy(FSRPCPolicy):
    """Full regeneration that reuses prior ids where the mapping is unambiguous.

    Isolates *identity re-minting* from regeneration. The state is still rebuilt
    in full every time -- `slots_regenerated` stays at the full state size, and
    no patch operator is ever applied.
    """

    name = "FSR-PC_stable_ids"

    def __init__(self, store, horizon_steps: int = 900, repair_engine=None):
        super().__init__(store, horizon_steps, repair_engine, preserve_ids=True)

    def regenerate(self, inp: AdaptationInput) -> RegeneratedState:
        regen = super().regenerate(inp)
        # `preserve_ids=True` already emits canonical ids; this guards the
        # "unambiguous" qualifier: if two regenerated slots would collapse onto
        # one prior id, keep them distinct rather than silently merging.
        seen: Dict[str, int] = {}
        slots: List[ConstraintSlot] = []
        for s in regen.slots:
            c = canonical_id(s.id)
            seen[c] = seen.get(c, 0) + 1
            slots.append(s if seen[c] == 1
                         else replace(s, id=f"{c}#amb{seen[c]}"))
        return RegeneratedState(
            regen_id=regen.regen_id, slots=tuple(slots),
            event_id=regen.event_id, issued_at_step=regen.issued_at_step,
            rationale="complete regeneration with stable id mapping")


class FSRPCProvenancePolicy(FSRPCPolicy):
    """Full regeneration that also emits explicit provenance per slot.

    Isolates *provenance recording* from local editing. Still a complete
    regeneration: every slot is re-emitted, ids are re-minted exactly as in
    plain FSR-PC, and no patch operator is applied. The difference is that each
    emitted slot carries why it looks the way it does.
    """

    name = "FSR-PC_provenance"

    def regenerate(self, inp: AdaptationInput) -> RegeneratedState:
        regen = super().regenerate(inp)
        upd = inp.world_state.get("update", {}) or {}
        cancelled = {canonical_id(g) for g in
                     set(inp.cancelled_goals) | set(upd.get("cancel", []))}
        redirect = {canonical_id(k): v
                    for k, v in (upd.get("redirect", {}) or {}).items()}
        suspend = {canonical_id(g) for g in upd.get("suspend", [])}
        restore = {canonical_id(g) for g in upd.get("restore", [])}
        completed = {canonical_id(g) for g in inp.completed_goals}
        prior = {canonical_id(i): i for i in self.store.state.ids()}

        slots: List[ConstraintSlot] = []
        for s in regen.slots:
            c = canonical_id(s.id)
            if c in cancelled:
                reason = upd.get("cancel_reason", "goal cancelled by the user")
                relation = "expired"
            elif c in redirect:
                reason = f"user redirected {c} to {redirect[c]}"
                relation = "replaces"
            elif c in suspend:
                reason = upd.get("suspend_reason", "target unavailable")
                relation = "suspended"
            elif c in restore:
                reason = "target available again; grounding revalidated"
                relation = "restored"
            elif c in completed:
                reason = "completed progress carried forward"
                relation = "inherited"
            else:
                reason = "unchanged by this event; re-emitted by regeneration"
                relation = "unchanged"

            prov = {
                "reason": reason,
                "source_event": inp.event_id,
                "predecessor_slot": prior.get(c),
                "replacement_relation": relation,
                "restoration_condition": (
                    f"target {s.payload.get('target')} available and revalidated"
                    if s.mode is SlotMode.SUSPENDED or c in restore else None),
            }
            # provenance is carried in the payload and mirrored into a single
            # history entry, so the audit layer can read it without any
            # CoPE-specific operator name
            hist = (SlotEdit(seq=1, patch_id=regen.regen_id,
                             operation="Regenerate", detail=reason,
                             mode_before=None, mode_after=s.mode),)
            slots.append(replace(
                s, payload={**s.payload, "provenance": prov},
                lineage=Lineage(derived_from=prov["predecessor_slot"]),
                history=hist))

        return RegeneratedState(
            regen_id=regen.regen_id, slots=tuple(slots),
            event_id=regen.event_id, issued_at_step=regen.issued_at_step,
            rationale="complete regeneration with explicit provenance")


def assert_no_patch_application(policy_cls) -> None:
    """A variant that applied a patch would no longer be a regeneration baseline."""
    import inspect
    src = inspect.getsource(policy_cls)
    for banned in ("apply_patch", "PatchOp(", "generate_patch"):
        if banned in src:
            raise AssertionError(
                f"{policy_cls.__name__} uses CoPE patch application ({banned})")
