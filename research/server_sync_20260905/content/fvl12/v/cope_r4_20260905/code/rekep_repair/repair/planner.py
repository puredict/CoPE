"""Runtime repair-program synthesis by search over typed operators.

The goal is an event-conditioned ``RepairGoal`` (union of every active
predicate's requirements), NOT a generic boolean.  The planner must *prove* the
final abstract state satisfies every requirement; the concrete filters
independently re-verify the same requirements against the rolled-out state.

Search is bounded best-first (uniform cost).  Every applicable operator strictly
adds information (see ``SymbolicOp.applicable``), so each is used at most once
and the search terminates.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .abstract_state import SYMBOLIC_OPS, AbstractState, RepairGoal, SymbolicOp


@dataclass
class PlanResult:
    plans: List[Tuple[Tuple[str, ...], float]]
    explored: List[Tuple[Tuple[str, ...], Tuple[str, ...]]]
    n_expanded: int
    goal_reached: bool
    goal: Optional[RepairGoal] = None

    @property
    def best(self) -> Optional[Tuple[str, ...]]:
        return self.plans[0][0] if self.plans else None

    def final_state(self, init: AbstractState, plan=None) -> AbstractState:
        seq = plan if plan is not None else (self.best or ())
        s = init
        for name in seq:
            s = SYMBOLIC_OPS[name].effect(s)
        return s

    def abstract_trajectory(self, init: AbstractState) -> List[AbstractState]:
        traj, s = [init], init
        for name in (self.best or ()):
            s = SYMBOLIC_OPS[name].effect(s)
            traj.append(s)
        return traj


class RepairPlanner:
    def __init__(self, ops: Optional[Dict[str, SymbolicOp]] = None, max_len: int = 10):
        self.ops = ops or SYMBOLIC_OPS
        self.max_len = max_len

    def plan(self, init: AbstractState, goal: RepairGoal, k: int = 4) -> PlanResult:
        frontier: List[Tuple[float, int, AbstractState, Tuple[str, ...]]] = []
        tie = 0
        heapq.heappush(frontier, (0.0, tie, init, ()))
        explored: List[Tuple[Tuple[str, ...], Tuple[str, ...]]] = []
        found: List[Tuple[Tuple[str, ...], float]] = []
        seen_paths = set()
        n_expanded = 0

        while frontier and len(found) < k:
            cost, _, state, path = heapq.heappop(frontier)
            n_expanded += 1
            applicable = [n for n, op in self.ops.items() if op.applicable(state)]
            explored.append((state.true_flags(), tuple(applicable)))

            if goal.satisfied_by(state):
                if path not in seen_paths:
                    seen_paths.add(path)
                    found.append((path, cost))
                continue

            if len(path) >= self.max_len:
                continue

            for name in applicable:
                if name in path:                 # each operator at most once
                    continue
                op = self.ops[name]
                tie += 1
                heapq.heappush(frontier, (cost + op.cost, tie, op.effect(state),
                                          path + (name,)))

        found.sort(key=lambda pc: (pc[1], len(pc[0])))
        return PlanResult(plans=found, explored=explored, n_expanded=n_expanded,
                          goal_reached=bool(found), goal=goal)
