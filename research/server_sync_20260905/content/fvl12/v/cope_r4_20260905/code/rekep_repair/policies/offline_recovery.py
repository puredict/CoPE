"""Offline precompiled recovery baselines.

All offline policies receive the **same active predicate set** as online
synthesis (``env.predicates(...)``), so there is no information asymmetry: the
difference is purely *when* the recovery structure is created and *how many*
combinations were paid for in advance.

A branch is keyed by a **predicate combination** (a frozenset), not by a single
event class.  Branch bodies are compiled offline by running the same operator
planner at compile time -- so an anticipated combination gets exactly the
program online synthesis would build, and the only variable is coverage.

Variants
--------
* ``OfflineSingleEventCoveragePolicy`` -- one branch per *single* predicate
  (3 branches).  Renamed from the earlier misleading "FullCoverage": it is NOT
  full coverage over combinations.
* ``OfflineComprehensivePolicy``       -- every combination up to size K
  (K=3 -> 7 branches).  Used to measure the coverage/branch-count trade-off.
* ``OfflineEnumeratedPolicy``          -- an explicit list of combinations.
* ``OfflineBudgetedPolicy``            -- a fixed branch budget; picks the
  cheapest (smallest) combinations first.
"""

from __future__ import annotations

import itertools
from typing import Dict, FrozenSet, List, Optional, Sequence, Set

import numpy as np

from ..execution.context import ExecutionContext
from ..execution.controller import control
from ..execution.executor import RecoveryPolicy
from ..execution.guard_monitor import stage_exit
from ..program.stage import StageSpec
from ..repair.abstract_state import (
    WorldPredicates,
    goal_from_predicates,
    state_from_predicates,
)
from ..repair.operator import OPERATORS
from ..repair.planner import RepairPlanner
from .common import build_params, nominal_pour_stage, record

PREDICATES = ("obstacle_present", "object_slipped", "target_relocated")


def _preds_from_key(key: FrozenSet[str]) -> WorldPredicates:
    return WorldPredicates(
        obstacle_present="obstacle_present" in key,
        unsafe_clearance="obstacle_present" in key,
        object_slipped="object_slipped" in key,
        target_relocated="target_relocated" in key,
    )


def all_combinations(max_size: int = 3) -> List[FrozenSet[str]]:
    out: List[FrozenSet[str]] = []
    for r in range(1, max_size + 1):
        for combo in itertools.combinations(PREDICATES, r):
            out.append(frozenset(combo))
    return out


class OfflinePrecompiledPolicy(RecoveryPolicy):
    """Runtime = select a precompiled branch by predicate combination.
    No graph rewriting, no continuation capture, no restore validation."""

    name = "offline_precompiled"

    def __init__(self, combinations: Optional[Sequence[FrozenSet[str]]] = None):
        self.combinations = [frozenset(c) for c in (combinations or [])]
        self.compile_ops = 0          # operator-expansions paid offline

    # --- offline compilation ---------------------------------------------
    def _compile(self) -> Dict[FrozenSet[str], List[StageSpec]]:
        planner = RepairPlanner()
        branches: Dict[FrozenSet[str], List[StageSpec]] = {}
        self.compile_ops = 0
        for key in self.combinations:
            p = _preds_from_key(key)
            res = planner.plan(state_from_predicates(p), goal_from_predicates(p), k=1)
            self.compile_ops += res.n_expanded
            if not res.best:
                continue
            branches[key] = [
                OPERATORS[n].instantiate(i, None, None, self.params)
                for i, n in enumerate(res.best)
                if n != "Resume"          # offline has no restore contract
            ]
        return branches

    def reset(self, env) -> None:
        self.env = env
        self.cfg = env.cfg
        self.params = build_params(self.cfg)
        self.nominal = nominal_pour_stage(behavior="progress")
        self.branches = self._compile()
        self.state = "NOMINAL"
        self.branch: List[StageSpec] = []
        self.bidx = self.bsteps = 0
        self.handoff = self.target = None
        self.failed_safe = False
        self._done = False
        self._stop_steps = 0
        self._active_event = "offline"
        self._selected_key = None
        # Latch handled combinations.  Without this a persistent predicate
        # (e.g. a relocated target stays relocated) would re-trigger its branch
        # forever.  Latching is the charitable implementation, so the
        # comparison is not decided by a fixable bookkeeping detail.
        self._handled: Set[FrozenSet[str]] = set()

    @property
    def branch_count(self) -> int:
        return len(self.branches)

    @property
    def graph_size(self) -> int:
        return sum(len(b) for b in self.branches.values())

    # --- runtime ----------------------------------------------------------
    def act(self, ctx: ExecutionContext):
        if self.state == "SAFE_STOP":
            self._stop_steps += 1
            self.failed_safe = True
            if self._stop_steps >= 5:
                self._done = True
            return np.zeros(3), record(ctx.t, np.zeros(3), self.nominal, "FAILED")

        # SAME predicate channel as online synthesis
        preds = self.env.predicates(self.cfg.d_react)
        key = preds.key()

        if self.state == "NOMINAL":
            if key and key not in self._handled:
                if key in self.branches:
                    self.state = "IN_BRANCH"
                    self.branch = self.branches[key]
                    self._selected_key = key
                    self.bidx = self.bsteps = 0
                    self.handoff = ctx.position.copy()
                    self.target = (ctx.reacquire_pos.copy()
                                   if ctx.reacquire_pos is not None else None)
                    self._active_event = f"offline:{sorted(key)}"
                    return self.act(ctx)
                self.state = "SAFE_STOP"          # combination not precompiled
                return self.act(ctx)
            a = control("progress", ctx, self.nominal, None, self.params, ctx.task_goal)
            rec = record(ctx.t, a, self.nominal, "ACTIVE")
            if np.linalg.norm(ctx.position - ctx.task_goal) < self.params.tol_pos:
                self._done = True
            return a, rec

        # IN_BRANCH
        stage = self.branch[self.bidx]
        if stage.metadata.get("behavior") == "to_handoff":
            stage.metadata["handoff_pose"] = self.handoff
        if stage.metadata.get("behavior") == "to_target" and self.target is not None:
            stage.metadata["target_pos"] = self.target
        a = control(stage.metadata["behavior"], ctx, stage, None, self.params, ctx.task_goal)
        rec = record(ctx.t, a, stage, "REPAIR_ACTIVE", event_id=self._active_event,
                     template="offline_branch")
        self.bsteps += 1
        if stage_exit(stage, self.env.observe(), self.bsteps, None, self.params, ctx.task_goal) \
           or self.bsteps > self.cfg.horizon:
            self.bidx += 1
            self.bsteps = 0
            if self.bidx >= len(self.branch):
                self.state = "NOMINAL"            # hand back, no restore contract
                if self._selected_key is not None:
                    self._handled.add(self._selected_key)
        return a, rec

    def finished(self) -> bool:
        return self._done


class OfflineSingleEventCoveragePolicy(OfflinePrecompiledPolicy):
    """One branch per SINGLE predicate.  NOT full coverage over combinations."""
    name = "offline_single"

    def __init__(self):
        super().__init__([frozenset({p}) for p in PREDICATES])


class OfflineComprehensivePolicy(OfflinePrecompiledPolicy):
    """Every combination up to size K -- maximal coverage, maximal branch count."""
    name = "offline_comprehensive"

    def __init__(self, max_size: int = 3):
        super().__init__(all_combinations(max_size))


class OfflineEnumeratedPolicy(OfflinePrecompiledPolicy):
    name = "offline_enumerated"


class OfflineBudgetedPolicy(OfflinePrecompiledPolicy):
    """Fixed branch budget: buys the smallest combinations first."""
    name = "offline_budget"

    def __init__(self, budget: int = 1, max_size: int = 3):
        combos = sorted(all_combinations(max_size), key=lambda c: (len(c), sorted(c)))
        super().__init__(combos[:budget])
        self.budget = budget


# Back-compat alias (deprecated name -- it was never full coverage).
OfflineFullCoveragePolicy = OfflineSingleEventCoveragePolicy
