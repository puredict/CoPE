"""Online repair policies parameterized by verification variant (B2)."""

from __future__ import annotations

import numpy as np

from ..repair.repair_manager import RepairManager
from ..repair.verifier_variants import VERIFIERS
from .online_repair import OnlineRepairPolicy


class VerifiedRepairPolicy(OnlineRepairPolicy):
    """Online synthesis with a selectable verifier."""

    variant = "nominal"

    def __init__(self, variant: str = None):
        if variant is not None:
            self.variant = variant
        self.name = f"online[{self.variant}]"
        # verification bookkeeping for the confusion matrix
        self.accepted_any = False
        self.n_replans = 0

    def _build_manager(self, **kw):
        mgr = RepairManager(**kw)
        V = VERIFIERS[self.variant]
        if self.variant == "none":
            mgr.verifier = V()
        else:
            mgr.verifier = V(kw["params"], kw["cfg"], kw["horizon_budget"])
        return mgr

    def _plan_and_splice(self, ev, ctx) -> None:
        super()._plan_and_splice(ev, ctx)
        if not self.failed_safe and self.continuation is not None:
            self.accepted_any = True


class RecedingRepairPolicy(VerifiedRepairPolicy):
    """Re-verify / re-plan when the observed state diverges from prediction.

    Divergence is measured against the pose predicted for the current repair
    stage; exceeding ``tol`` clears the latch for the active predicate
    combination so the next tick re-plans from the true state.
    """

    variant = "receding"

    def __init__(self, tol_frac: float = 0.25, max_replans: int = 3):
        super().__init__("receding")
        self.name = "online[receding]"
        # Threshold is a FRACTION OF PER-STEP MOTION and divergence is
        # ACCUMULATED.  A fixed absolute one-step threshold larger than v_max
        # can never fire, which is why the first version never triggered.
        self.tol_frac = tol_frac
        self.max_replans = max_replans

    def reset(self, env) -> None:
        super().reset(env)
        self._pred_pose = None
        self._cum_div = 0.0
        self.n_replans = 0

    def act(self, ctx):
        tol = self.tol_frac * self.cfg.v_max
        if (self._pred_pose is not None and self.program.in_repair
                and self.n_replans < self.max_replans):
            self._cum_div += float(np.linalg.norm(ctx.position - self._pred_pose))
            if self._cum_div > max(tol, 3.0 * tol):
                self.n_replans += 1
                self._cum_div = 0.0
                self._handled.clear()          # allow re-planning this combo
                self._pred_pose = None
        a, rec = super().act(ctx)
        # one-step-ahead prediction under the NOMINAL model
        from ..execution.action import clip_action
        self._pred_pose = ctx.position + clip_action(
            a, self.cfg.v_max, self.cfg.w_max)[:2]
        return a, rec


def make(variant: str):
    if variant == "receding":
        return RecedingRepairPolicy()
    return VerifiedRepairPolicy(variant)


VERIFIER_POLICIES = {
    "online[none]": lambda: VerifiedRepairPolicy("none"),
    "online[nominal]": lambda: VerifiedRepairPolicy("nominal"),
    "online[conservative]": lambda: VerifiedRepairPolicy("conservative"),
    "online[receding]": RecedingRepairPolicy,
}
