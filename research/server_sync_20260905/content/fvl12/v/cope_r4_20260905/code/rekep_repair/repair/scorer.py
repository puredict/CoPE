"""State-dependent candidate scoring.

Scoring runs AFTER sequential rollout, so it uses measured/predicted quantities
rather than structural length alone:

    J = w_res * event_residual        (hard-rejected upstream; kept for ranking)
      + w_safe * safety_shortfall(predicted min clearance, severity)
      + w_dur  * predicted duration
      + w_hand * predicted handoff error
      + w_att  * attachment risk
      + alpha  * edit cost (#stages)
      + w_sw   * switching cost

Event severity and current clearance modulate the safety term, so a severe,
close-range intrusion prefers plans that open more margin, while a mild, distant
one prefers shorter plans.  Structural length no longer dominates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..events.event import Event
from .candidate import RepairCandidate
from .operator import RepairParams


@dataclass(frozen=True)
class ScoreWeights:
    w_residual: float = 100.0     # unresolved requirement (also hard-rejected)
    w_safety: float = 8.0         # safety shortfall vs desired margin
    w_duration: float = 0.05      # predicted steps
    w_handoff: float = 2.0        # predicted handoff error
    w_attach: float = 5.0         # ends without the object held
    alpha: float = 0.3            # edit cost (#stages)
    w_switch: float = 0.1         # mode switches
    # legacy knobs kept so older call sites still construct
    beta: float = 5.0
    gamma: float = 1.0
    eta: float = 0.05
    event_penalty: float = 10.0


class Scorer:
    def __init__(self, params: RepairParams, weights: ScoreWeights = ScoreWeights()):
        self.params = params
        self.w = weights

    def score(self, cand: RepairCandidate, event: Event) -> RepairCandidate:
        w, p = self.w, self.params
        rep = cand.rollout
        sev = float(getattr(event, "severity", 0.0) or 0.0)

        if rep is None:
            # no rollout available: fall back to structure only
            cand.score = w.alpha * len(cand.stages)
            cand.score_terms = {"edit": len(cand.stages), "note": "no-rollout"}
            return cand

        # desired standoff grows with severity: a severe intrusion wants margin
        desired = p.d_react * (0.6 + 0.6 * sev)
        shortfall = max(0.0, desired - rep.predicted_min_clearance)

        residual = w.w_residual * len(rep.event_residual)
        safety = w.w_safety * shortfall
        duration = w.w_duration * rep.predicted_duration
        handoff = w.w_handoff * min(rep.predicted_handoff_error, 10.0)
        attach = w.w_attach * (0.0 if rep.predicted_attachment == "grasped" else 1.0)
        edit = w.alpha * len(cand.stages)
        switch = w.w_switch * max(0, len(cand.stages) - 1)

        total = residual + safety + duration + handoff + attach + edit + switch
        cand.score = float(total)
        cand.score_terms = {
            "residual": round(residual, 3),
            "safety": round(safety, 3),
            "duration": round(duration, 3),
            "handoff": round(handoff, 3),
            "attach": round(attach, 3),
            "edit": round(edit, 3),
            "switch": round(switch, 3),
            "min_clr": round(rep.predicted_min_clearance, 3),
            "steps": rep.predicted_duration,
            "severity": round(sev, 3),
        }
        return cand

    def select(self, cands: List[RepairCandidate], event: Event) -> Optional[RepairCandidate]:
        if not cands:
            return None
        for c in cands:
            self.score(c, event)
        return min(cands, key=lambda c: (c.score, len(c.stages)))
