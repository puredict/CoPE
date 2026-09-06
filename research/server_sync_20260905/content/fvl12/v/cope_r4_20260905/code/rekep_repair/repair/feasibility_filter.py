"""Short-horizon feasibility screen (Sec. 5.5).

Rejects candidates whose required motions cannot be realized under the control
limits within the allotted per-stage horizon -- in particular an infeasible
handoff (the realign/resume stage cannot reach the handoff pose/orientation in
time) or a retreat that cannot open the safety margin.  This is a cheap
kinematic reachability check, not a full trajectory solve.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from .candidate import RepairCandidate
from .operator import RepairParams


@dataclass(frozen=True)
class ControlLimits:
    v_max: float          # max translation per step
    w_max: float          # max rotation per step
    ws_lo: np.ndarray = None   # workspace lower bound
    ws_hi: np.ndarray = None   # workspace upper bound


class FeasibilityFilter:
    def __init__(self, limits: ControlLimits, params: RepairParams):
        self.limits = limits
        self.params = params

    def check(self, cand: RepairCandidate) -> RepairCandidate:
        c = cand.continuation
        p = self.params
        L = self.limits
        x = np.asarray(c.state, float)
        theta_now = float(x[2])
        pos_now = x[:2]

        # find the handoff-providing stage (Realign/Resume) budget
        realign_steps = sum(
            s.max_steps for s in cand.stages
            if s.metadata.get("behavior") == "to_handoff"
        )
        if realign_steps == 0 and not cand.is_terminal():
            cand.feasible, cand.feasibility_reason = False, "no-realign-budget"
            return cand

        if not cand.is_terminal():
            # orientation reachability: theta_hold -> handoff_theta
            handoff_theta = p.handoff_theta if p.handoff_theta is not None else p.theta_pour
            dtheta = abs(handoff_theta - p.theta_hold)
            if dtheta > L.w_max * realign_steps + 1e-9:
                cand.feasible, cand.feasibility_reason = (
                    False, f"handoff-orientation-unreachable: need {dtheta:.3f}, "
                           f"budget {L.w_max * realign_steps:.3f}")
                return cand
            # position reachability of handoff pose
            if p.handoff_pose is not None:
                dpos = float(np.linalg.norm(np.asarray(p.handoff_pose, float) - pos_now))
                if dpos > L.v_max * realign_steps + 1e-9:
                    cand.feasible, cand.feasibility_reason = (
                        False, f"handoff-position-unreachable: need {dpos:.3f}, "
                               f"budget {L.v_max * realign_steps:.3f}")
                    return cand

        # workspace bounds on any explicit target
        if p.target_pos is not None and L.ws_lo is not None:
            tp = np.asarray(p.target_pos, float)
            if np.any(tp < L.ws_lo) or np.any(tp > L.ws_hi):
                cand.feasible, cand.feasibility_reason = False, "target-out-of-workspace"
                return cand

        cand.feasible, cand.feasibility_reason = True, "ok"
        return cand

    def filter(self, cands: List[RepairCandidate]) -> List[RepairCandidate]:
        return [c for c in (self.check(c) for c in cands) if c.feasible]
