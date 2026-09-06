"""Internal-activation probe (B1).

A class name or a disabled flag is NOT evidence that an ablation changed the
causal path.  This probe records, per repair decision, the internal variables an
ablation is *supposed* to alter, so we can assert the intended variable actually
differs from the full method.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class RepairActivation:
    """One repair-planning decision, fully introspected."""

    t: int
    predicate_key: Tuple[str, ...]
    goal_label: str
    goal_required_true: Tuple[str, ...]
    goal_required_false: Tuple[str, ...]
    explored_states: int
    synthesized_plans: Tuple[Tuple[str, ...], ...]
    generated: Tuple[str, ...]
    rejected: Tuple[Tuple[str, str], ...]
    survived: Tuple[str, ...]
    selected: Optional[str]
    selected_score: float
    score_terms: Dict[str, Any] = field(default_factory=dict)
    handoff_pose: Optional[Tuple[float, ...]] = None
    used_fallback: bool = False


@dataclass
class EpisodeActivation:
    method: str
    activations: List[RepairActivation] = field(default_factory=list)
    restore_validations: List[bool] = field(default_factory=list)
    final_state: Optional[Tuple[float, ...]] = None
    trajectory: Optional[np.ndarray] = None

    # --- comparison helpers ------------------------------------------------
    def goals(self):
        return [(a.goal_label, a.goal_required_true) for a in self.activations]

    def plans(self):
        return [a.synthesized_plans for a in self.activations]

    def selections(self):
        return [a.selected for a in self.activations]

    def handoffs(self):
        return [a.handoff_pose for a in self.activations]

    def scores(self):
        return [a.selected_score for a in self.activations]


def instrument(policy) -> EpisodeActivation:
    """Attach recording hooks to an OnlineRepairPolicy (or subclass).

    Wraps ``_plan_and_splice`` and ``_validate_restore`` so we capture the goal,
    the search result, every candidate verdict, the selection, and the restore
    decision -- without changing behavior.
    """
    act = EpisodeActivation(method=getattr(policy, "name", type(policy).__name__))
    orig_plan = policy._plan_and_splice
    orig_restore = policy._validate_restore

    def wrapped_plan(ev, ctx):
        before = len(policy._trace)
        orig_plan(ev, ctx)
        gen = getattr(policy, "generator", None)
        lp = getattr(gen, "last_plan", None) if gen else None
        goal = getattr(gen, "last_goal", None) if gen else None
        summary = policy._trace[before] if len(policy._trace) > before else ""

        generated, rejected, scored, selected, score = (), [], [], None, float("inf")
        terms: Dict[str, Any] = {}
        for ln in summary.split("\n"):
            s = ln.strip()
            if s.startswith("generated:"):
                generated = tuple(x for x in s.split("'")[1::2])
            elif s.startswith("rejected"):
                body = s[len("rejected"):].strip()
                name, _, why = body.partition(":")
                rejected.append((name.strip(), why.strip()))
            elif s.startswith("scored"):
                body = s[len("scored"):].strip()
                name, _, rest = body.partition(":")
                scored.append(name.strip())
            elif s.startswith("SELECTED"):
                selected = s.split("SELECTED", 1)[1].split("(score=")[0].strip()
                try:
                    score = float(s.split("(score=")[1].rstrip(") "))
                except Exception:
                    pass

        cont = getattr(policy, "continuation", None)
        hp = None
        if cont is not None and cont.handoff_pose is not None:
            hp = tuple(np.round(np.asarray(cont.handoff_pose, float), 6).tolist())

        preds = policy.env.predicates(policy.cfg.d_react)
        act.activations.append(RepairActivation(
            t=ctx.t,
            predicate_key=tuple(sorted(preds.key())),
            goal_label=goal.label if goal is not None else "",
            goal_required_true=tuple(sorted(goal.required_true)) if goal else (),
            goal_required_false=tuple(sorted(goal.required_false)) if goal else (),
            explored_states=getattr(lp, "n_expanded", 0) if lp else 0,
            synthesized_plans=tuple(tuple(p) for p, _c in (lp.plans if lp else [])),
            generated=generated,
            rejected=tuple(rejected),
            survived=tuple(scored),
            selected=selected,
            selected_score=score,
            score_terms=terms,
            handoff_pose=hp,
            used_fallback=selected is None,
        ))

    def wrapped_restore(ctx):
        ok = orig_restore(ctx)
        act.restore_validations.append(bool(ok))
        return ok

    policy._plan_and_splice = wrapped_plan
    policy._validate_restore = wrapped_restore
    return act
