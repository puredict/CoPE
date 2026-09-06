"""Verifier-discriminative diagnostic scenario.

## Why this exists

The v2 LIBERO pilot generated 162 candidate repair programs, rollout-verified
all 162, and rejected **zero**. The verifier ran, but the pilot never showed it
changing a decision, so it contributed no evidence.

This scenario is built so that runtime synthesis produces several *plausible*
candidates of which some are physically bad:

    candidate 0   short operator ordering, but the path collides / makes
                  unsafe contact
    candidate 1   collision-free, but ends too far from the captured
                  continuation handoff -> restore contract cannot hold
    candidate 2   collision-free and restore-valid  -> selected

The candidates are produced by the **actual** `SynthesisGenerator` planner, not
hard-coded. The scenario only shapes the *world* (an obstruction near the
handoff corridor and a tight clearance margin) so the verifier's existing checks
have something to discriminate.

Checkpoint isolation is unchanged: every candidate starts from the same saved
state, which the engine already asserts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from rekep_repair.synthetic.dynamics import Obstacle

from .basket_world import BASKET_POS, BasketLegEnv, basket_position


@dataclass
class VerifierProbeSpec:
    """World shaping for the diagnostic. Deterministic in `seed`."""
    seed: int = 0
    obj: str = "butter"
    target: str = "basket_B"
    #: obstruction radius; larger => more candidates collide
    obstacle_radius: float = 0.16
    #: how far along the path to the basket the obstruction sits
    obstacle_frac: float = 0.55
    #: steps to run before the interruption is injected
    steps_before_event: int = 8

    def key(self) -> str:
        return f"verifier_probe|{self.obj}|{self.target}|{self.seed}"


def build_probe_env(spec: VerifierProbeSpec) -> BasketLegEnv:
    """A leg env with an obstruction placed in the return corridor.

    The obstruction is a genuine `Obstacle` in the frozen `SceneConfig`, so the
    frozen controllers, guards and the frozen `RolloutVerifier` all see it
    through their normal channels -- nothing about the verifier is special-cased.
    """
    env = BasketLegEnv(spec.obj, spec.target, seed=spec.seed)
    start = np.asarray(env.cfg.p_init, float)
    goal = basket_position(spec.target)
    centre = start + spec.obstacle_frac * (goal - start)
    env.cfg.obstacle = Obstacle(p_start=centre.copy(), p_end=centre.copy(),
                                radius=spec.obstacle_radius,
                                t_enter=0, t_exit=10 ** 6)
    # tighten the reaction margin so the obstruction is inside the planner's
    # awareness and the goal actually requires clearing it
    env.cfg.d_react = max(env.cfg.d_react, spec.obstacle_radius + 0.12)
    env.cfg.d_safe = max(env.cfg.d_safe, spec.obstacle_radius * 0.75)
    return env


def summarize_rejections(outcome) -> Dict[str, Any]:
    """Normalise the engine's rejection records into the reporting vocabulary."""
    buckets = {"collision_or_unsafe_contact": [], "invalid_handoff": [],
               "infeasible": [], "illegal": [], "other": []}
    for name, reason in (outcome.rejections or []):
        r = str(reason).lower()
        if "collision" in r or "unsafe" in r or "clearance" in r:
            buckets["collision_or_unsafe_contact"].append(name)
        elif "handoff" in r or "restore" in r:
            buckets["invalid_handoff"].append(name)
        elif "feasib" in r:
            buckets["infeasible"].append(name)
        elif "legal" in r:
            buckets["illegal"].append(name)
        else:
            buckets["other"].append(name)
    return {
        "n_candidates": outcome.n_candidates,
        "n_rejected": outcome.n_rejected,
        "n_accepted": max(0, (outcome.n_candidates or 0)
                          - (outcome.n_rejected or 0)),
        "selected": outcome.selected,
        "rejected_by_reason": {k: v for k, v in buckets.items() if v},
        "verifier_discriminated": bool(outcome.n_rejected)
                                  and outcome.selected is not None,
        "rollout_verification_enabled": getattr(
            outcome, "rollout_verification_enabled", True),
    }


def rejection_lines(outcome) -> List[str]:
    """The exact lines the protocol asks to see in the trace."""
    lines: List[str] = []
    for name, reason in (outcome.rejections or []):
        r = str(reason).lower()
        tag = ("collision_or_unsafe_contact"
               if ("collision" in r or "unsafe" in r or "clearance" in r)
               else "invalid_handoff" if ("handoff" in r or "restore" in r)
               else "infeasible" if "feasib" in r
               else "illegal" if "legal" in r else "other")
        lines.append(f"CANDIDATE_REJECTED {name} reason={tag}")
    if outcome.selected:
        lines.append(f"CANDIDATE_SELECTED {outcome.selected}")
    return lines


def run_probe(spec: Optional[VerifierProbeSpec] = None, *,
              disable_rollout_verification: bool = False) -> Dict[str, Any]:
    """Run the probe once and report what the verifier actually did.

    Reports the outcome as observed. It does not assert a particular
    reject/reject/accept split, because on the CPU synthetic world the
    synthesised candidates share an operator multiset and the verifier rejects
    them uniformly. The three-way split is established on LIBERO -- the v2
    preflight recorded exactly it (candidate 0 unsafe contact, candidate 1
    handoff 0.142 m, candidate 2 accepted).
    """
    from ..audit_trace import AuditTrace
    from ..constraint_slot import ConstraintSlot, SlotMode
    from ..constraint_state import ConstraintState
    from ..repair_bridge import SharedRepairEngine
    from rekep_repair.execution.controller import control
    from rekep_repair.policies.common import build_params

    spec = spec or VerifierProbeSpec()
    env = build_probe_env(spec)
    engine = SharedRepairEngine(env, AuditTrace())
    engine.disable_rollout_verification = disable_rollout_verification
    params = build_params(env.cfg)
    for _ in range(spec.steps_before_event):
        ctx = env.observe()
        env.step(control("progress", ctx, engine.program.active_stage(), None,
                         params, ctx.task_goal))

    before = ConstraintState().put_many([
        ConstraintSlot(id="g_butter", grounding="place_butter_in_basket_B",
                       payload={"object": "butter", "target": "basket_B"})])
    env.retarget("basket_A")
    after = ConstraintState().put_many([
        ConstraintSlot(id="g_butter", grounding="place_butter_in_basket_B",
                       mode=SlotMode.OVERRIDDEN,
                       payload={"object": "butter", "target": "basket_B"}),
        ConstraintSlot(id="g_butter@basket_A",
                       grounding="place_butter_in_basket_A",
                       payload={"object": "butter", "target": "basket_A"})])
    out = engine.repair(before=before, after=after, adaptation=None,
                        adaptation_kind="patch", world={},
                        ctx=env.observe(), event_id="verifier-probe",
                        step=spec.steps_before_event)
    summary = summarize_rejections(out)
    summary["lines"] = rejection_lines(out)
    summary["safe_fallback"] = bool(out.safe_fallback)
    summary["probe"] = spec.key()
    return summary


def compare_verifier_arms(spec: Optional[VerifierProbeSpec] = None
                          ) -> Dict[str, Any]:
    """CoPE_full vs CoPE_no_rollout_verification on the same probe.

    This is the mechanism test: if the two arms reach the same decision, the
    verifier changed nothing and must be reported as non-discriminative.
    """
    spec = spec or VerifierProbeSpec()
    full = run_probe(spec, disable_rollout_verification=False)
    abl = run_probe(spec, disable_rollout_verification=True)
    return {"CoPE_full": full, "CoPE_no_rollout_verification": abl,
            "verifier_changed_the_decision":
                full.get("selected") != abl.get("selected")
                or full.get("safe_fallback") != abl.get("safe_fallback"),
            "n_rejected_full": full.get("n_rejected"),
            "n_rejected_ablated": abl.get("n_rejected")}
