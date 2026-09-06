"""Verification variants for the model-mismatch study (B2).

* ``NoVerifier``            -- accept every symbolically legal plan.
* ``NominalVerifier``       -- the current sequential rollout (nominal model).
* ``ConservativeVerifier``  -- rollout with uncertainty margins on clearance,
                               handoff tolerance, action budget and guard timing.
* ``RecedingHorizonVerifier`` -- nominal rollout, plus runtime re-verification
                               whenever predicted and observed state diverge.

A candidate ACCEPTED by the verifier that then fails physically is a
**false accept** -- the headline verification metric.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .rollout_verifier import RolloutReport, RolloutVerifier


class NoVerifier:
    """Accepts everything (no concrete feasibility check at all)."""
    name = "none"

    def __init__(self, *a, **kw):
        pass

    def verify(self, cand, ctx, goal, continuation) -> RolloutReport:
        rep = RolloutReport()
        rep.ok, rep.reason = True, "unverified"
        rep.predicted_min_clearance = float("inf")
        rep.predicted_handoff_error = 0.0
        rep.predicted_duration = sum(s.max_steps for s in cand.stages)
        rep.restore_ok = True
        return rep


class NominalVerifier(RolloutVerifier):
    """The existing sequential rollout under the nominal planning model."""
    name = "nominal"


class ConservativeVerifier(RolloutVerifier):
    """Rollout with explicit uncertainty margins.

    ``clearance_margin`` inflates the effective obstacle; ``budget_factor``
    shrinks the usable per-stage horizon; ``handoff_margin`` tightens the
    accepted handoff error.  These convert model error into rejected plans
    rather than false accepts.
    """
    name = "conservative"

    def __init__(self, params, cfg, horizon_budget,
                 clearance_margin: float = 0.06,
                 budget_factor: float = 0.8,
                 handoff_margin: float = 0.03):
        super().__init__(params, cfg, horizon_budget)
        self.clearance_margin = clearance_margin
        self.budget_factor = budget_factor
        self.handoff_margin = handoff_margin

    def verify(self, cand, ctx, goal, continuation) -> RolloutReport:
        rep = super().verify(cand, ctx, goal, continuation)
        if not rep.ok:
            return rep
        # reject plans whose predicted margin is inside the uncertainty band
        if np.isfinite(rep.predicted_min_clearance) and \
                rep.predicted_min_clearance < self.clearance_margin:
            rep.ok = False
            rep.reason = (f"conservative: predicted clearance "
                          f"{rep.predicted_min_clearance:.3f} < margin "
                          f"{self.clearance_margin:.3f}")
            return rep
        if rep.predicted_duration > self.budget_factor * self.horizon_budget:
            rep.ok = False
            rep.reason = "conservative: duration exceeds discounted budget"
            return rep
        if rep.predicted_handoff_error > self.params.tol_pos - self.handoff_margin:
            rep.ok = False
            rep.reason = "conservative: handoff error inside uncertainty band"
        return rep


class RecedingHorizonVerifier(NominalVerifier):
    """Nominal verification, but the POLICY re-verifies during execution.

    The verifier itself is nominal; the receding behaviour is implemented by
    ``RecedingOnlineRepairPolicy``, which re-plans when the observed state
    diverges from the prediction beyond a threshold.
    """
    name = "receding"


VERIFIERS = {
    "none": NoVerifier,
    "nominal": NominalVerifier,
    "conservative": ConservativeVerifier,
    "receding": RecedingHorizonVerifier,
}
