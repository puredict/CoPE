"""FROZEN environment-adapter interface (deliverable 8).

Everything the repair layer needs from a world lives behind this interface, so
the same online-synthesis machinery can drive the 2D synthetic domain or a
ReKep/OmniGibson scene without changes to `repair/`, `program/`, or `policies/`.

Contract stability: treat this as FROZEN.  Add methods only by extending the
base class with a default implementation; do not change existing signatures.

Deliberately NOT in the interface: trajectory optimization.  The ReKep adapter
must delegate to ReKep's own subgoal/path/IK solvers, so the paper can isolate
    same ReKep constraint + trajectory solvers  +  online repair layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import numpy as np

from .execution.context import ExecutionContext
from .repair.abstract_state import WorldPredicates
from .repair.candidate import RepairCandidate
from .repair.rollout_verifier import RolloutReport


class RepairEnvironmentAdapter(ABC):
    """Simulator-independent surface used by the online repair layer."""

    # --- observation ------------------------------------------------------
    @abstractmethod
    def observe_context(self) -> ExecutionContext:
        """Current execution context (ee state, clearance, object, goal)."""

    @abstractmethod
    def active_predicates(self) -> WorldPredicates:
        """The full active predicate set.  MUST be the same object handed to
        every policy, so no method sees a richer world view than another."""

    @abstractmethod
    def current_task_goal(self) -> np.ndarray:
        """The CURRENT task goal (may relocate at runtime).  Never the
        immutable configured goal."""

    @abstractmethod
    def attachment_state(self) -> Dict[str, str]:
        """e.g. {"object": "grasped" | "released"}."""

    # --- prediction / verification ---------------------------------------
    @abstractmethod
    def simulate_candidate(
        self,
        candidate: RepairCandidate,
        ctx: ExecutionContext,
        goal: Any,
        continuation: Any,
    ) -> RolloutReport:
        """Sequentially roll a candidate out and report predicted collision,
        guard failures, duration, handoff error, attachment and requirement
        residual.  Must not mutate the live world."""

    # --- actuation --------------------------------------------------------
    @abstractmethod
    def execute_action(self, action: np.ndarray) -> ExecutionContext:
        """Apply one control step and return the resulting context."""

    # --- optional -----------------------------------------------------
    def reset(self) -> ExecutionContext:
        return self.observe_context()

    @property
    def horizon(self) -> int:
        return 200


class SyntheticAdapter(RepairEnvironmentAdapter):
    """Adapter over ``Synthetic2DEnv`` (CPU).  Reference implementation."""

    def __init__(self, env, d_react: Optional[float] = None):
        self.env = env
        self.cfg = env.cfg
        self.d_react = d_react if d_react is not None else env.cfg.d_react
        from .policies.common import build_params
        from .repair.rollout_verifier import RolloutVerifier
        self._verifier = RolloutVerifier(build_params(env.cfg), env.cfg,
                                         horizon_budget=env.cfg.horizon)

    def observe_context(self) -> ExecutionContext:
        return self.env.observe()

    def active_predicates(self) -> WorldPredicates:
        return self.env.predicates(self.d_react)

    def current_task_goal(self) -> np.ndarray:
        return self.env.goal.copy()

    def attachment_state(self) -> Dict[str, str]:
        return {"object": "grasped" if self.env.grasped else "released"}

    def simulate_candidate(self, candidate, ctx, goal, continuation) -> RolloutReport:
        return self._verifier.verify(candidate, ctx, goal, continuation)

    def execute_action(self, action: np.ndarray) -> ExecutionContext:
        return self.env.step(action)

    def reset(self) -> ExecutionContext:
        return self.env.reset()

    @property
    def horizon(self) -> int:
        return self.cfg.horizon


# The real GPU adapter lives in rekep_adapter.py (deferred imports so it stays
# importable on the CPU machine).  Re-exported here for a single import site.
def _load_rekep_adapter():
    from .rekep_adapter import ReKepOmniGibsonAdapter as _A
    return _A


def __getattr__(name):
    if name == "ReKepOmniGibsonAdapter":
        return _load_rekep_adapter()
    raise AttributeError(name)
