"""TaskProgram -- executable stage skeleton with an enforced runtime state
machine and continuation-carrying online repair.

Runtime semantics for an interruption during active stage s_i:

    s_i^ACTIVE -> s_i^SUSPENDED -> u_1 -> ... -> u_m -> s_i^RESUMED(kappa) -> s_{i+1}

Invariants enforced here (not by convention):

* The interrupted stage becomes SUSPENDED, never COMPLETED, when repair begins.
* The nominal successor s_{i+1} stays PENDING and unreachable until (1) every
  repair stage COMPLETED, (2) the restore contract validated, and (3) the
  RESUMED instance COMPLETED.
* The RESUMED node cannot be entered until ``mark_restore_validated`` succeeds;
  otherwise the program routes to a bounded safe fallback (FAILED).

The ReKep solver never sees any of this: it always asks for ``active_stage()``.
That isolation lets the paper attribute gains to program repair, not to a
different trajectory optimizer.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

import numpy as np

from .continuation import Continuation
from .graph import TaskGraph
from .stage import Mode, StageSpec, StageState


class RestorationBlocked(RuntimeError):
    """Raised when entry into the RESUMED node is attempted before the restore
    contract has been validated."""


class TaskProgram:
    def __init__(self, stages: List[StageSpec]):
        self._stages: Dict[str, StageSpec] = {s.stage_id: s for s in stages}
        self._order: List[str] = [s.stage_id for s in stages]
        self.graph = TaskGraph.chain(self._order)
        self.state: Dict[str, StageState] = {sid: StageState.PENDING for sid in self._order}
        self.active_index: int = 0
        self.finished: bool = False
        self.failed: bool = False
        # repair bookkeeping
        self.in_repair: bool = False
        self._interrupted_id: Optional[str] = None
        self._resumed_id: Optional[str] = None
        self._restore_validated: bool = False
        self._repair_counter: int = 0
        # provenance: node_id -> record
        self.provenance: Dict[str, dict] = {}
        if self._order:
            self.state[self._order[0]] = StageState.ACTIVE

    # --- accessors --------------------------------------------------------
    def stages(self) -> List[StageSpec]:
        return [self._stages[sid] for sid in self._order]

    def spec(self, node_id: str) -> StageSpec:
        return self._stages[node_id]

    def active_stage(self) -> StageSpec:
        return self._stages[self._order[self.active_index]]

    def active_id(self) -> str:
        return self._order[self.active_index]

    def active_state(self) -> StageState:
        return self.state[self.active_id()]

    def num_stages(self) -> int:
        return len(self._order)

    def is_repair_node(self, node_id: str) -> bool:
        return self._stages[node_id].kind == "repair"

    def is_resumed_node(self, node_id: str) -> bool:
        return self._stages[node_id].kind == "resumed"

    # --- interruption -----------------------------------------------------
    def interrupt_active_stage(self, continuation: Continuation) -> Continuation:
        """Mark the active nominal stage SUSPENDED and enter repair mode.

        Does NOT complete the stage.  Returns the continuation for the caller
        to carry through the repair.
        """
        aid = self.active_id()
        st = self.state[aid]

        # A RESUMED node is nominal work on the interrupted stage, so it may be
        # re-interrupted: the previous repair is closed out (its continuation
        # was already restored) and a fresh repair context opens.
        if st == StageState.RESUMED:
            if self._interrupted_id is not None and self._interrupted_id != aid:
                self.state[self._interrupted_id] = StageState.COMPLETED
            self._end_repair()
        elif self.in_repair:
            raise RuntimeError("already in repair; cannot re-interrupt")
        elif st != StageState.ACTIVE:
            raise RuntimeError(
                f"can only interrupt an ACTIVE or RESUMED stage, got {st}")

        self.state[aid] = StageState.SUSPENDED
        self.in_repair = True
        self._interrupted_id = aid
        self._restore_validated = False
        return continuation

    def splice_repair_before_successor(
        self,
        repair_stages: List[StageSpec],
        continuation: Continuation,
    ) -> None:
        """Insert ``repair_stages`` then a RESUMED copy of the interrupted stage
        between the suspended stage and its nominal successor.

        Precondition: ``interrupt_active_stage`` was called (state SUSPENDED).
        The active pointer moves to the first repair stage (REPAIR_ACTIVE).
        """
        if not self.in_repair or self._interrupted_id is None:
            raise RuntimeError("must interrupt_active_stage before splicing")
        anchor_id = self._interrupted_id
        anchor = self._stages[anchor_id]

        # P0-1: namespace every runtime node by anchor + event + a monotonic
        # repair-instance tag so repeated repairs never collide (which would
        # corrupt _order and make the graph cyclic).
        self._repair_counter += 1
        tag = f"r{self._repair_counter}"
        prefix = f"{anchor_id}::{continuation.event_id or 'E?'}::{tag}::"

        renamed: List[StageSpec] = [
            replace(s, stage_id=prefix + s.stage_id, kind="repair") for s in repair_stages
        ]
        resumed_id = f"{anchor_id}#resume::{tag}"
        resumed = replace(anchor, stage_id=resumed_id, kind="resumed")
        self._resumed_id = resumed_id

        new_ids = [s.stage_id for s in renamed] + [resumed_id]

        # invariants: no duplicate ids, none pre-existing
        assert len(new_ids) == len(set(new_ids)), f"duplicate repair ids: {new_ids}"
        for nid in new_ids:
            assert nid not in self._stages, f"repair id already exists: {nid}"

        for s in renamed:
            self._stages[s.stage_id] = s
            self.state[s.stage_id] = StageState.PENDING
            self.provenance[s.stage_id] = {
                "kind": "repair",
                "mode": s.mode.value,
                "operator": s.metadata.get("operator"),
                "triggered_by_event": continuation.metadata_event_id(),
                "interrupted_stage": anchor_id,
                "timestamp": continuation.timestamp,
            }
        self._stages[resumed_id] = resumed
        self.state[resumed_id] = StageState.PENDING
        self.provenance[resumed_id] = {
            "kind": "resumed",
            "of": anchor_id,
            "triggered_by_event": continuation.metadata_event_id(),
            "timestamp": continuation.timestamp,
        }

        # rewrite order + graph identically
        pos = self.active_index
        self._order[pos + 1 : pos + 1] = new_ids
        self.graph = self.graph.splice_after(anchor_id, new_ids)
        assert len(self._order) == len(set(self._order)), "duplicate ids in _order"
        assert self.graph.is_acyclic(), "splice produced a cyclic graph"

        # activate first repair stage
        self.active_index = pos + 1
        first = self.active_id()
        self.state[first] = StageState.REPAIR_ACTIVE

    # --- restore + resume -------------------------------------------------
    def restore_validated(self) -> bool:
        return self._restore_validated

    def mark_restore_validated(self, state_vec: np.ndarray, keypoints=None) -> bool:
        """Validate the continuation's resume contract against ``state_vec``.

        Returns True and unlocks entry into the RESUMED node iff the contract
        (Pre(s_i^resumed)) holds.  Idempotent.
        """
        cont = self._pending_continuation
        ok = cont.restorable_from(state_vec, keypoints) if cont is not None else True
        self._restore_validated = bool(ok)
        return self._restore_validated

    def resume_interrupted_stage(self) -> None:
        """Logical resumption bookkeeping once the RESUMED node becomes active."""
        if self._interrupted_id is not None:
            # keep SUSPENDED until the resumed instance completes; record intent
            self.provenance.setdefault(self._resumed_id, {}).update({"resumed": True})

    # --- advancement with gating -----------------------------------------
    def advance(self) -> bool:
        """Advance to the next node, enforcing the restoration gate.

        Returns False if the program finished.  Raises RestorationBlocked if
        the next node is the RESUMED instance and restore has not validated.

        P0-2: the transition is ATOMIC -- all legality checks run *before* any
        state is mutated, so a blocked transition leaves the program unchanged.
        """
        cur = self.active_id()

        # 1) check the transition legality BEFORE mutating anything
        has_next = self.active_index + 1 < len(self._order)
        if has_next:
            nxt = self._order[self.active_index + 1]
            if self.is_resumed_node(nxt) and not self._restore_validated:
                raise RestorationBlocked(
                    f"cannot enter RESUMED node {nxt}: restore contract not validated"
                )

        # 2) commit: complete the current node
        if self.is_resumed_node(cur):
            self.state[cur] = StageState.COMPLETED
            if self._interrupted_id is not None:
                self.state[self._interrupted_id] = StageState.COMPLETED
            self._end_repair()
        else:
            self.state[cur] = StageState.COMPLETED

        if not has_next:
            self.finished = True
            return False

        # 3) enter the next node
        self.active_index += 1
        if self.is_resumed_node(nxt):
            self.state[nxt] = StageState.RESUMED
            self.resume_interrupted_stage()
        elif self.is_repair_node(nxt):
            self.state[nxt] = StageState.REPAIR_ACTIVE
        else:
            self.state[nxt] = StageState.ACTIVE
        return True

    def next_id(self) -> Optional[str]:
        if self.active_index + 1 >= len(self._order):
            return None
        return self._order[self.active_index + 1]

    def about_to_enter_resumed(self) -> bool:
        nid = self.next_id()
        return nid is not None and self.is_resumed_node(nid)

    # --- fallback ---------------------------------------------------------
    def activate_safe_fallback(self, reason: str = "") -> None:
        """Route to a bounded safe failure: mark current + resumed FAILED."""
        cur = self.active_id()
        self.state[cur] = StageState.FAILED
        if self._resumed_id is not None:
            self.state[self._resumed_id] = StageState.FAILED
        if self._interrupted_id is not None:
            self.state[self._interrupted_id] = StageState.FAILED
        self.failed = True
        self.finished = True
        self.provenance.setdefault("__fallback__", {}).update({"reason": reason})

    # --- internal ---------------------------------------------------------
    _pending_continuation: Optional[Continuation] = None

    def set_pending_continuation(self, cont: Continuation) -> None:
        self._pending_continuation = cont

    def _end_repair(self) -> None:
        self.in_repair = False
        self._interrupted_id = None
        self._resumed_id = None
        self._restore_validated = False
        self._pending_continuation = None

    def is_wellformed(self) -> bool:
        return self.graph.is_acyclic()

    def order_graph_consistent(self) -> bool:
        """No duplicate ids in the linear order and the graph is acyclic and
        covers exactly the ordered nodes."""
        if len(self._order) != len(set(self._order)):
            return False
        if not self.graph.is_acyclic():
            return False
        return set(self._order) == set(self.graph.nodes)
