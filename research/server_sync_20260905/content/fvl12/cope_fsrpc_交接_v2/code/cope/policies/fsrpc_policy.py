"""FSRPCPolicy --- the strong full-state-regeneration baseline.

## What FSR-PC is here

**FSR-PC is NOT an established published algorithm.** The acronym does not
appear anywhere in the collaborator's CoPE/RCSP memo (v0.3, 2026-04-26) or in
any other supplied material; the expansion used throughout this project,
*Full-State Regeneration with Progress/Context*, comes from the project brief
that commissioned this baseline. It must therefore be described in every report
as an **internally defined strong baseline**, never cited as external
state-of-the-art. See `docs/FSRPC_BASELINE_SPEC.md`.

## Why it is strong, not a straw man

At an interruption FSR-PC receives **exactly the same** `AdaptationInput` as
CoPE -- same world state, robot state, completed/pending/cancelled goals, user
request, safety constraints, task history, event history, perception and compute
budget. It is deliberately **not** made forgetful or history-free.

The single intended difference:

    CoPE    edits the persistent state with typed local patches
    FSR-PC  emits a COMPLETE regenerated state

Consequences that follow from regeneration (and are what we measure), not from
withholding information:
  * every slot is re-emitted, so slot identity is re-minted rather than carried;
  * lifecycle history and lineage are not inherently continued;
  * the edit footprint equals the whole state, not the touched subset.

A conscientious regenerator can still *reconstruct* correct content from the
history it is given -- and this implementation does exactly that. It is a strong
baseline precisely because it gets everything right that regeneration allows.

FSR-PC must never call CoPE patch operations; it builds slots directly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..constraint_slot import (
    ConstraintSlot, Priority, SlotMode, SlotSource,
)
from ..patch import RegeneratedState
from ..naming import canonical_id
from ..recovery_manager import ExecutorRequest, RecoveryManager
from ..state_store import StateStore
from .adaptation_input import AdaptationInput


class FSRPCPolicy:
    """Full-State Regeneration with Progress/Context (internally defined)."""

    name = "FSR-PC"

    def __init__(self, store: StateStore, horizon_steps: int = 900,
                 repair_engine: Optional[Any] = None,
                 preserve_ids: bool = False):
        self.store = store
        self.mgr = RecoveryManager(store, horizon_steps, repair_engine)
        self.n_model_calls = 0
        self.n_slots_edited = 0
        self.n_slots_emitted = 0
        self.regenerations: List[RegeneratedState] = []
        self.last_validation = None
        self.last_repair = None
        # If True the regenerator also re-uses the previous ids. Off by default
        # because re-minting identity is the defining property of regeneration;
        # the flag exists so the ablation can be run rather than argued about.
        self.preserve_ids = preserve_ids

    # ------------------------------------------------------------------
    def regenerate(self, inp: AdaptationInput) -> RegeneratedState:
        """Rebuild the COMPLETE constraint state from the supplied context.

        Uses the full information packet: completed goals are honoured (not
        re-planned), cancellations are dropped, redirections are re-grounded to
        the new target, suspensions are emitted as suspended slots.
        """
        upd = inp.world_state.get("update", {})
        canon = canonical_id
        cancelled = {canon(g) for g in
                     set(inp.cancelled_goals) | set(upd.get("cancel", []))}
        redirect = {canon(k): v for k, v in dict(upd.get("redirect", {})).items()}
        suspend = {canon(g) for g in upd.get("suspend", [])}
        restore = {canon(g) for g in upd.get("restore", [])}
        completed = {canon(g) for g in inp.completed_goals}
        unavailable = set(inp.world_state.get("unavailable_targets", []) or [])

        slots: List[ConstraintSlot] = []
        rid = f"regen-{inp.event_id or 'e'}-{inp.event_step}"

        # Every task goal is re-emitted from scratch. The regenerator collapses
        # its own prior slots onto the canonical task vocabulary first, so that
        # repeated regenerations do not multiply records -- FSR-PC is given
        # every chance to be correct.
        prior = self.store.state
        live: Dict[str, ConstraintSlot] = {}
        for sid in prior.ids():
            s = prior.get(sid)
            if s.source is SlotSource.SAFETY_RULE:
                continue
            c = canon(sid)
            cur = live.get(c)
            if cur is None or (cur.mode is not SlotMode.ACTIVE
                               and s.mode is SlotMode.ACTIVE):
                live[c] = s

        for gid in sorted(set(live) | completed
                          | {canon(g) for g in inp.pending_goals}):
            old = live.get(gid)
            base_payload = dict(old.payload) if old else {}
            obj = base_payload.get("object", gid.replace("g_", ""))
            target = base_payload.get("target")
            new_id = gid if self.preserve_ids else f"{gid}#r{inp.event_step}"

            # a completed goal is regenerated as a satisfied, still-active slot
            if gid in completed:
                slots.append(ConstraintSlot(
                    id=new_id, grounding=f"place_{obj}_in_{target}",
                    mode=SlotMode.ACTIVE,
                    priority=(old.priority if old else Priority.SOFT),
                    source=SlotSource.INITIAL_TASK,
                    payload={**base_payload, "completed": True}))
                continue

            if gid in cancelled:
                # regeneration expresses cancellation by not emitting an active
                # goal; an expired record is emitted so the state stays auditable
                slots.append(ConstraintSlot(
                    id=new_id, grounding=f"place_{obj}_in_{target}",
                    mode=SlotMode.EXPIRED, source=SlotSource.INITIAL_TASK,
                    payload=base_payload))
                continue

            tgt = redirect.get(gid, target)
            # carry the prior lifecycle mode forward: a strong regenerator uses
            # the full context it is given rather than defaulting to ACTIVE
            mode = old.mode if old is not None else SlotMode.ACTIVE
            if gid in suspend or tgt in unavailable:
                mode = SlotMode.SUSPENDED
            if gid in restore and tgt not in unavailable:
                mode = SlotMode.ACTIVE
            slots.append(ConstraintSlot(
                id=new_id, grounding=f"place_{obj}_in_{tgt}", mode=mode,
                priority=(old.priority if old else Priority.SOFT),
                source=SlotSource.INITIAL_TASK,
                payload={**base_payload, "target": tgt}))

        # safety constraints are regenerated too
        for c in list(inp.safety_constraints) + list(upd.get("insert_safety", [])):
            cid = c["id"] if self.preserve_ids else f"{c['id']}#r{inp.event_step}"
            slots.append(ConstraintSlot(
                id=cid, grounding=c.get("grounding", c["id"]),
                mode=SlotMode.ACTIVE, priority=Priority.HARD,
                source=SlotSource.SAFETY_RULE, payload=c.get("payload", {})))

        return RegeneratedState(regen_id=rid, slots=tuple(slots),
                                event_id=inp.event_id,
                                issued_at_step=inp.event_step,
                                rationale="complete regeneration from full context")

    # ------------------------------------------------------------------
    def adapt(self, inp: AdaptationInput) -> ExecutorRequest:
        before_fp = self.store.state.fingerprint()
        before_ids = set(self.store.state.ids())
        before_state = self.store.state          # C_t, captured before install

        regen = self.regenerate(inp)
        self.n_model_calls += 1
        self.regenerations.append(regen)
        self.store.trace.record("state_regenerated", **regen.to_dict())

        ok, rep = self.store.install_regenerated(regen)
        self.last_validation = rep
        if not ok:
            self.store.trace.record("regen_rejected", regen_id=regen.regen_id,
                                    violations=rep.violations)
            return self.mgr.compile(budget=inp.compute_budget)

        # ---- hand off to the SHARED downstream stack -----------------------
        # The SAME RecoveryManager method CoPE calls, with the same signature.
        # FSR-PC differs only in how it produced the new state, never in what
        # happens to it afterwards.
        self.last_repair = self.mgr.enter_repair_pipeline(
            before=before_state, after=self.store.state, adaptation=regen,
            adaptation_kind="regeneration", world=inp.world_state,
            event_id=inp.event_id, step=inp.event_step)

        self.n_slots_emitted += len(regen.slots)
        self.n_slots_edited += len(regen.slots)      # regeneration touches all
        after_ids = set(self.store.state.ids())
        self.store.trace.record(
            "adaptation_summary", method="FSR-PC", regen_id=regen.regen_id,
            n_ops=0, n_slots_edited=len(regen.slots),
            n_slots_emitted=len(regen.slots), n_slots_total=len(after_ids),
            identity_preserved=before_ids.issubset(after_ids),
            state_fp_before=before_fp,
            state_fp_after=self.store.state.fingerprint())
        return self.mgr.compile(budget=inp.compute_budget)
