"""Stage specification -- the atomic node of a ReKep-R task program.

A ``StageSpec`` bundles everything Eq. (1) needs for one stage of the outer
summation: sub-goal constraints, path constraints, a transition guard, a
semantic mode, and the execution metadata that later becomes the continuation.

We keep constraints as callables returning a scalar with the ReKep convention
``f(x) <= 0  <=>  satisfied``.  This matches the paper (main.tex) and lets the
same object be scored, penalized, or checked as a hard constraint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Tuple

import numpy as np

from .contracts import Contract, ALWAYS


class StageState(str, Enum):
    """Runtime lifecycle state of a stage node.

    The interrupted nominal stage moves ACTIVE -> SUSPENDED at interruption and
    must NOT become COMPLETED until its resumed instance finishes.  Repair
    operator stages run as REPAIR_ACTIVE; the resumed copy of the interrupted
    stage runs as RESUMED (only enterable once the restore contract holds).
    """

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REPAIR_ACTIVE = "REPAIR_ACTIVE"
    RESUMED = "RESUMED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Mode(str, Enum):
    """Semantic mode of a stage.  The nominal modes come from the task; the
    repair modes come from the typed repair library (Sec. 5.4)."""

    # nominal task modes
    TRANSPORT = "TRANSPORT"
    POUR = "POUR"
    ALIGN = "ALIGN"
    GRASP = "GRASP"
    PLACE = "PLACE"
    # repair modes
    SUSPEND = "SUSPEND"
    STABILIZE = "STABILIZE"
    AVOID = "AVOID"
    RETREAT = "RETREAT"
    WAIT = "WAIT"
    REGRASP = "REGRASP"
    REALIGN = "REALIGN"
    RESTORE = "RESTORE"
    SAFE_STOP = "SAFE_STOP"


# A constraint: state (and optional keypoints) -> scalar, satisfied when <= 0.
Constraint = Callable[[np.ndarray, Optional[np.ndarray]], float]
# A guard: returns True when the stage may terminate / transition.
Guard = Callable[[np.ndarray, Optional[np.ndarray]], bool]


@dataclass(frozen=True)
class StageSpec:
    """One stage ``s_i = (C_sub, C_path, rho_i, m_i, psi_i)``."""

    stage_id: str
    mode: Mode
    kind: str = "nominal"          # "nominal" | "repair" | "resumed"
    subgoal_constraints: Tuple[Constraint, ...] = ()
    path_constraints: Tuple[Constraint, ...] = ()
    entry_guard: Contract = ALWAYS
    exit_guard: Optional[Guard] = None
    max_steps: int = 200
    # Optional fixed target in state space used by the synthetic solver as the
    # stage's nominal attractor (the set A / B in the conflict analysis).
    target: Optional[np.ndarray] = None
    target_weight: Optional[np.ndarray] = None
    metadata: dict = field(default_factory=dict)

    # --- constraint evaluation helpers -----------------------------------
    def subgoal_violation(self, x: np.ndarray, k: Optional[np.ndarray] = None) -> float:
        """Total positive violation of sub-goal constraints (0 if satisfied)."""
        return _total_violation(self.subgoal_constraints, x, k)

    def path_violation(self, x: np.ndarray, k: Optional[np.ndarray] = None) -> float:
        """Total positive violation of path constraints (0 if satisfied)."""
        return _total_violation(self.path_constraints, x, k)

    def exit_satisfied(self, x: np.ndarray, k: Optional[np.ndarray] = None) -> bool:
        if self.exit_guard is None:
            # Default guard: sub-goals satisfied.
            return self.subgoal_violation(x, k) <= 1e-9
        return bool(self.exit_guard(x, k))


def _total_violation(constraints, x, k) -> float:
    total = 0.0
    for f in constraints:
        v = float(f(x, k))
        if v > 0.0:
            total += v
    return total
