"""RepairManager -- the online pipeline:

    event + continuation
      -> generate candidates
      -> legality filter (reject illegal)
      -> feasibility filter (reject short-horizon infeasible)
      -> score + select
      -> (or) signal safe fallback

Returns a structured RepairResult carrying every rejection reason, so the
executor can log a full runtime trace and fall back safely when nothing
survives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ..events.event import Event
from ..program.continuation import Continuation
from .abstract_state import AbstractState, RepairGoal
from .rollout_verifier import RolloutVerifier
from .candidate import RepairCandidate
from .feasibility_filter import ControlLimits, FeasibilityFilter
from .legality_filter import LegalityFilter
from .operator import RepairParams
from .scorer import Scorer, ScoreWeights
from .synthesis_generator import SynthesisGenerator


@dataclass
class RepairResult:
    event_id: str
    goal_label: str = ""
    generated: List[str] = field(default_factory=list)
    rejected: List[Tuple[str, str]] = field(default_factory=list)     # (template, reason)
    rollouts: List[Tuple[str, str]] = field(default_factory=list)
    scored: List[Tuple[str, float, dict]] = field(default_factory=list)
    selected: Optional[RepairCandidate] = None
    use_fallback: bool = False

    def summary(self) -> str:
        lines = [f"event={self.event_id}  goal={self.goal_label}"]
        lines.append(f"  generated: {self.generated}")
        for name, rep in self.rollouts:
            lines.append(f"  rollout   {name}: {rep}")
        for name, reason in self.rejected:
            lines.append(f"  rejected  {name}: {reason}")
        for name, score, terms in self.scored:
            lines.append(f"  scored    {name}: {score:.3f}  {terms}")
        if self.selected is not None:
            lines.append(f"  SELECTED  {self.selected.template_name} (score={self.selected.score:.3f})")
        elif self.use_fallback:
            lines.append("  -> SAFE FALLBACK (no surviving candidate)")
        return "\n".join(lines)


class RepairManager:
    def __init__(
        self,
        params: RepairParams = None,
        limits: ControlLimits = None,
        weights: ScoreWeights = ScoreWeights(),
        anchor_id: str = "__anchor__",
        successor_id: str = "__succ__",
        generator=None,
        cfg=None,
        horizon_budget: int = 200,
    ):
        # default: runtime operator synthesis.  Pass a CandidateGenerator to get
        # the template-instantiation baseline.
        self.generator = generator if generator is not None else SynthesisGenerator(params)
        self.legality = LegalityFilter(anchor_id, successor_id)
        self.feasibility = FeasibilityFilter(limits, params)
        self.scorer = Scorer(params, weights)
        self.verifier = (RolloutVerifier(params, cfg, horizon_budget)
                         if cfg is not None else None)

    def plan(self, event: Event, continuation: Continuation,
             abstract_init: AbstractState = None,
             goal: RepairGoal = None, ctx=None, env=None) -> RepairResult:
        res = RepairResult(event_id=event.event_id)
        res.goal_label = goal.label if goal is not None else ""
        candidates = self.generator.generate(event, continuation, abstract_init, goal)
        res.generated = [c.template_name for c in candidates]
        if not candidates:
            res.use_fallback = True
            return res

        # 1) structural legality
        legal: List[RepairCandidate] = []
        for c in candidates:
            self.legality.check(c)
            if c.legal:
                legal.append(c)
            else:
                res.rejected.append((c.template_name, f"legality/{c.legality_reason}"))

        # 2) cheap terminal reachability screen
        feasible: List[RepairCandidate] = []
        for c in legal:
            self.feasibility.check(c)
            if c.feasible:
                feasible.append(c)
            else:
                res.rejected.append((c.template_name, f"feasibility/{c.feasibility_reason}"))

        # 3) SEQUENTIAL rollout: propagate state operator-by-operator and
        #    independently re-verify every active event requirement.  A
        #    candidate with unresolved requirements is REJECTED, never merely
        #    penalized.
        verified: List[RepairCandidate] = []
        if self.verifier is not None and ctx is not None and goal is not None:
            for c in feasible:
                rep = self.verifier.verify(c, ctx, goal, continuation)
                c.rollout = rep
                res.rollouts.append((c.template_name, rep.summary()))
                if rep.ok:
                    verified.append(c)
                else:
                    res.rejected.append((c.template_name, f"rollout/{rep.reason}"))
        else:
            verified = feasible

        if not verified:
            res.use_fallback = True
            return res

        selected = self.scorer.select(verified, event)
        res.scored = [(c.template_name, c.score, c.score_terms) for c in verified]
        res.selected = selected
        return res
