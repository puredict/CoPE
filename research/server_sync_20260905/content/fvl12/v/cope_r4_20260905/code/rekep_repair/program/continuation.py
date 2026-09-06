"""Continuation capture -- the recovery checkpoint kappa_t.

This is the distinguishing concept of ReKep-R (Sec. 3.1).  When an event
interrupts the *active* stage (not a completed one), we snapshot the execution
contract so that after the repair program runs we can resume the interrupted
computation from a valid state rather than restarting the stage.

kappa_t = (i, x_t, e_t, q_t, A_t, g_i, C_i, chi_t)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np

from .contracts import Contract
from .stage import Mode


@dataclass(frozen=True)
class Continuation:
    """Snapshot taken at interruption time."""

    interrupted_stage_id: str
    stage_mode: Mode
    state: np.ndarray                     # x_t  (full synthetic state)
    ee_pose: np.ndarray                   # e_t  (pose subset of x_t, or SE(3) log)
    joint_state: Optional[np.ndarray] = None      # q_t
    attachment_state: Dict[str, str] = field(default_factory=dict)  # A_t
    nominal_target: Optional[np.ndarray] = None   # attractor of interrupted stage
    resume_contract: Optional[Contract] = None    # Pre(s_i^resumed)
    handoff_pose: Optional[np.ndarray] = None      # e_handoff for realignment
    progress_marker: float = 0.0          # chi_t in [0, 1]
    timestamp: int = 0
    event_id: str = ""                    # provenance link to the triggering event

    def metadata_event_id(self) -> str:
        return self.event_id

    def handoff_error(self, x: np.ndarray, weight: Optional[np.ndarray] = None) -> float:
        """E_handoff = ||Log(e_target^{-1} e_restore)||_W.

        In the synthetic domain poses live in a flat vector space, so the
        SE(3) log reduces to a weighted Euclidean distance to ``handoff_pose``.
        """
        if self.handoff_pose is None:
            return 0.0
        e = np.asarray(x, dtype=float)[: self.handoff_pose.shape[0]]
        diff = e - self.handoff_pose
        if weight is not None:
            return float(np.sqrt(np.sum(np.asarray(weight) * diff ** 2)))
        return float(np.linalg.norm(diff))

    def restorable_from(self, x: np.ndarray, k: Optional[np.ndarray] = None) -> bool:
        """Whether state ``x`` satisfies the resume contract Pre(s_i^resumed)."""
        if self.resume_contract is None:
            return True
        return self.resume_contract.holds(x, k)
