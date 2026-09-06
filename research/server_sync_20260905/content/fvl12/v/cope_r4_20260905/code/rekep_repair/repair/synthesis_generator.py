"""Synthesis-based candidate generator.

Builds the abstract state from the current context, SEARCHES for operator
sequences that reach the goal (planner.py), and instantiates the resulting
plans into concrete RepairCandidates.  This is runtime program *synthesis* --
no complete event-specific sequence is stored.

Contrast with ``CandidateGenerator`` (template instantiation), kept as a
baseline.
"""

from __future__ import annotations

from typing import List, Optional

from ..events.event import Event
from ..program.continuation import Continuation
from .abstract_state import AbstractState, RepairGoal, initial_state
from .candidate import RepairCandidate
from .operator import OPERATORS, RepairParams
from .planner import PlanResult, RepairPlanner


class SynthesisGenerator:
    kind = "operator-synthesis"

    def __init__(self, params: RepairParams, k: int = 4):
        self.params = params
        self.planner = RepairPlanner()
        self.k = k
        self.last_plan: Optional[PlanResult] = None
        self.last_init: Optional[AbstractState] = None

    def generate(self, event: Event, continuation: Continuation,
                 abstract_init: Optional[AbstractState] = None,
                 goal: Optional[RepairGoal] = None) -> List[RepairCandidate]:
        if abstract_init is None:
            abstract_init = initial_state(
                obstacle_present=False, safe_clearance=True,
                object_grasped=continuation.attachment_state.get("object", "grasped") == "grasped",
            )
        if goal is None:
            goal = RepairGoal(required_true=frozenset({"restore_valid"}), label="restore")
        self.last_init = abstract_init
        self.last_goal = goal
        result = self.planner.plan(abstract_init, goal, k=self.k)
        self.last_plan = result

        candidates: List[RepairCandidate] = []
        for ops, _cost in result.plans:
            stages = [
                OPERATORS[name].instantiate(idx, event, continuation, self.params)
                for idx, name in enumerate(ops)
            ]
            candidates.append(
                RepairCandidate(template_name="+".join(ops), stages=stages,
                                continuation=continuation)
            )
        return candidates
