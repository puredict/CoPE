"""Structural legality: WellFormed (acyclic + connected), HasRestore,
AttachmentConsistent.  Rejects candidates that could never be spliced into a
valid task program (Sec. 5.5).
"""

from __future__ import annotations

from typing import List

from ..program.graph import TaskGraph
from .candidate import RepairCandidate


class LegalityFilter:
    def __init__(self, anchor_id: str = "__anchor__", successor_id: str = "__succ__"):
        self.anchor_id = anchor_id
        self.successor_id = successor_id

    def check(self, cand: RepairCandidate) -> RepairCandidate:
        ok_graph, why_graph = self._wellformed(cand)
        ok_restore = cand.provides_restore() or cand.is_terminal()
        ok_attach, why_attach = self._attachment_consistent(cand)

        if not ok_graph:
            cand.legal, cand.legality_reason = False, f"not-wellformed: {why_graph}"
        elif not ok_restore:
            cand.legal, cand.legality_reason = False, "no-restore-edge"
        elif not ok_attach:
            cand.legal, cand.legality_reason = False, f"attachment: {why_attach}"
        else:
            cand.legal, cand.legality_reason = True, "ok"
        return cand

    def filter(self, cands: List[RepairCandidate]) -> List[RepairCandidate]:
        return [c for c in (self.check(c) for c in cands) if c.legal]

    # --- WellFormed -------------------------------------------------------
    def _wellformed(self, cand: RepairCandidate):
        nodes = [self.anchor_id] + cand.stage_ids + [self.successor_id]
        g = TaskGraph(nodes=list(nodes), edges=set())
        ids = cand.stage_ids
        g.edges.add((self.anchor_id, ids[0]))
        if cand.internal_edges is not None:
            # adversarial / explicit edges among stage nodes
            for e in cand.internal_edges:
                g.edges.add(e)
        else:
            for a, b in zip(ids, ids[1:]):
                g.edges.add((a, b))
        g.edges.add((ids[-1], self.successor_id))
        if not g.is_acyclic():
            return False, "cyclic"
        if not g.is_connected_chain_from(self.anchor_id):
            return False, "disconnected"
        return True, "ok"

    # --- AttachmentConsistent --------------------------------------------
    def _attachment_consistent(self, cand: RepairCandidate):
        held = cand.continuation.attachment_state.get("object", "grasped") == "grasped"
        for s in cand.stages:
            if s.metadata.get("requires_grasp") and not held:
                return False, f"{s.stage_id} requires grasp but object not held"
            if s.metadata.get("establishes_grasp"):
                held = True
        return True, "ok"
