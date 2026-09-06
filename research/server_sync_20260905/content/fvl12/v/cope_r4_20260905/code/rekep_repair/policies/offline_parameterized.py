"""P0-B: a genuinely STRONG precompiled baseline.

A precompiled recovery branch here is a **symbolic, parameterized program**.  At
runtime this policy has every capability online synthesis has:

* the same active predicate set (``env.predicates``);
* the same concrete state / runtime parameter binding (handoff pose, reacquire
  target, current task goal);
* the same controllers and guards;
* the same sequential rollout verifier (so it can reject an infeasible branch);
* the same state-dependent scoring quantities;
* multiple already-compiled orderings per predicate combination to choose from;
* continuation capture, graph splice, restore-contract validation and resume.

The ONLY prohibited capability is constructing an operator sequence that was not
compiled before execution.  The scientific distinction is therefore exactly:

    offline: choose among precompiled operator sequences
    online : search over operators and synthesize a new sequence

Consequently, when the exact combination IS precompiled, this baseline should
match online success (and select faster, since it does no search).  If it does
not, that is a baseline/controller bug, not an online advantage.
"""

from __future__ import annotations

import itertools
import time
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

from ..events.event import Event
from ..program.continuation import Continuation
from ..repair.abstract_state import (
    AbstractState,
    RepairGoal,
    goal_from_predicates,
    state_from_predicates,
)
from ..repair.candidate import RepairCandidate
from ..repair.operator import OPERATORS, RepairParams
from ..repair.planner import RepairPlanner
from .offline_recovery import PREDICATES, _preds_from_key
from .online_repair import OnlineRepairPolicy


def all_combinations(max_size: int = 3) -> List[FrozenSet[str]]:
    out: List[FrozenSet[str]] = []
    for r in range(1, max_size + 1):
        for combo in itertools.combinations(PREDICATES, r):
            out.append(frozenset(combo))
    return out


class PrecompiledLibrary:
    """Offline-compiled symbolic branches: predicate-combination -> ordered
    operator-name sequences.  Compiled ONCE, before execution."""

    def __init__(self, combinations: Sequence[FrozenSet[str]], branches_per_combo: int = 3):
        self.combinations = [frozenset(c) for c in combinations]
        self.branches_per_combo = branches_per_combo
        self.table: Dict[FrozenSet[str], List[Tuple[str, ...]]] = {}
        self.compile_expansions = 0
        self.compile_seconds = 0.0

    def compile(self) -> "PrecompiledLibrary":
        planner = RepairPlanner()
        t0 = time.perf_counter()
        for key in self.combinations:
            p = _preds_from_key(key)
            res = planner.plan(state_from_predicates(p), goal_from_predicates(p),
                               k=self.branches_per_combo)
            self.compile_expansions += res.n_expanded
            if res.plans:
                # store MULTIPLE valid structural orderings for this combination
                self.table[key] = [ops for ops, _c in res.plans]
        self.compile_seconds = time.perf_counter() - t0
        return self

    @property
    def branch_count(self) -> int:
        return sum(len(v) for v in self.table.values())

    @property
    def combination_count(self) -> int:
        return len(self.table)

    def graph_size(self, ) -> int:
        return sum(len(seq) for seqs in self.table.values() for seq in seqs)

    def lookup(self, key: FrozenSet[str]) -> List[Tuple[str, ...]]:
        return self.table.get(key, [])


class _LibraryGenerator:
    """Candidate generator that BINDS precompiled sequences to runtime
    parameters.  It never searches: if the combination was not compiled, it
    returns nothing (-> safe fallback)."""

    kind = "precompiled-parameterized"

    def __init__(self, params: RepairParams, library: PrecompiledLibrary,
                 key: FrozenSet[str]):
        self.params = params
        self.library = library
        self.key = key
        self.last_plan = None
        self.n_lookup = 0

    def generate(self, event: Event, continuation: Continuation,
                 abstract_init: Optional[AbstractState] = None,
                 goal: Optional[RepairGoal] = None) -> List[RepairCandidate]:
        seqs = self.library.lookup(self.key)
        self.n_lookup = len(seqs)
        out: List[RepairCandidate] = []
        for ops in seqs:
            stages = [OPERATORS[n].instantiate(i, event, continuation, self.params)
                      for i, n in enumerate(ops)]
            out.append(RepairCandidate("|".join(ops), stages, continuation))
        return out


class OfflineParameterizedPolicy(OnlineRepairPolicy):
    """Precompiled branches + full runtime parameter binding, verification and
    selection.  Inherits the entire online runtime (continuation capture,
    splice, restore gate, resume); only the generator differs."""

    name = "offline_parameterized"

    def __init__(self, combinations: Optional[Sequence[FrozenSet[str]]] = None,
                 branches_per_combo: int = 3):
        self._combos = ([frozenset(c) for c in combinations]
                        if combinations is not None else all_combinations(3))
        self._branches_per_combo = branches_per_combo

    def reset(self, env) -> None:
        super().reset(env)
        # compile ONCE, before execution
        self.library = PrecompiledLibrary(self._combos,
                                          self._branches_per_combo).compile()
        self._current_key: FrozenSet[str] = frozenset()

    def _make_generator(self, params):
        return _LibraryGenerator(params, self.library, self._current_key)

    def _plan_and_splice(self, ev, ctx) -> None:
        # bind the runtime predicate combination before the generator is built
        self._current_key = self.env.predicates(self.cfg.d_react).key()
        super()._plan_and_splice(ev, ctx)

    # --- reporting --------------------------------------------------------
    @property
    def branch_count(self) -> int:
        return self.library.branch_count

    @property
    def graph_size(self) -> int:
        return self.library.graph_size()

    @property
    def compile_ops(self) -> int:
        return self.library.compile_expansions


class OfflineExactPolicy(OfflineParameterizedPolicy):
    """Regime 1: the exact combination(s) ARE precompiled (full combination
    coverage up to size 3)."""
    name = "offline_exact"

    def __init__(self):
        super().__init__(all_combinations(3))


class OfflineAtomicOnlyPolicy(OfflineParameterizedPolicy):
    """Regime 2: only atomic / single-event branches were precompiled."""
    name = "offline_atomic"

    def __init__(self):
        super().__init__([frozenset({p}) for p in PREDICATES])


class OfflineBudgetPolicy(OfflineParameterizedPolicy):
    """Regime 3: fixed branch-memory budget over combinations."""
    name = "offline_budget"

    def __init__(self, budget: int = 2, branches_per_combo: int = 3):
        combos = sorted(all_combinations(3), key=lambda c: (len(c), sorted(c)))
        super().__init__(combos[:budget], branches_per_combo)
        self.budget = budget
