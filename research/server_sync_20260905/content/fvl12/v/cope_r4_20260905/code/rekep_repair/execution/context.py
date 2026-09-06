"""ExecutionContext -- the per-step observation handed to detectors, policies,
controllers, and guards.  Domain-agnostic; the 2D synthetic env fills it in,
and an OmniGibson adapter would fill the same fields later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np


@dataclass
class ExecutionContext:
    t: int
    state: np.ndarray                       # ee: (p_x, p_y, theta)
    keypoints: Optional[np.ndarray] = None
    obstacle_pos: Optional[np.ndarray] = None
    obstacle_radius: float = 0.0
    clearance: float = float("inf")         # dist(ee, obstacle_surface)
    # --- task target (may relocate at runtime).  ALWAYS use this, never the
    # immutable SceneConfig.p_goal, for control, guards, contracts and metrics.
    task_goal: Optional[np.ndarray] = None
    nominal_goal: Optional[np.ndarray] = None   # the original, for comparison
    target_displacement: float = 0.0            # ||task_goal - nominal_goal||
    # --- object state, distinct from the end-effector
    object_pos: Optional[np.ndarray] = None
    object_grasped: bool = True
    slipped: bool = False
    # position the manipulator must go to in order to reacquire the object
    reacquire_pos: Optional[np.ndarray] = None
    attachments: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, object] = field(default_factory=dict)

    @property
    def position(self) -> np.ndarray:
        """End-effector position."""
        return self.state[:2]

    @property
    def theta(self) -> float:
        """End-effector / held-object orientation."""
        return float(self.state[2])

    # back-compat: older call sites used `target_pos` for "where to go next"
    @property
    def target_pos(self) -> Optional[np.ndarray]:
        if not self.object_grasped and self.reacquire_pos is not None:
            return self.reacquire_pos
        return self.task_goal
