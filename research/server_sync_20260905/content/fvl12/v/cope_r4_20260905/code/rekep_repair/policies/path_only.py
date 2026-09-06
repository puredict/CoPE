"""B1 -- ReKep + path-only constraint augmentation.

On the event, an avoidance term is added to the *active* stage, but the pouring
mode is never suspended: the stage skeleton is unchanged and the pour
orientation objective stays active.  It dodges but cannot hold the container
upright -> it spills (the Theorem-1 conflict, realized online).
"""

from __future__ import annotations

import numpy as np

from ..execution.context import ExecutionContext
from ..execution.controller import control
from ..execution.executor import RecoveryPolicy
from .common import build_params, nominal_pour_stage, record


class PathOnlyPolicy(RecoveryPolicy):
    name = "path_only"

    def reset(self, env) -> None:
        self.env = env
        self.cfg = env.cfg
        self.params = build_params(self.cfg)
        self.stage = nominal_pour_stage(behavior="progress")   # 'progress' includes repulsion
        self._done = False

    def act(self, ctx: ExecutionContext):
        # avoidance is always available via 'progress' repulsion, but the pour
        # orientation term is never deactivated.
        a = control("progress", ctx, self.stage, None, self.params, ctx.task_goal)
        rec = record(ctx.t, a, self.stage, "ACTIVE")
        if np.linalg.norm(ctx.position - ctx.task_goal) < self.params.tol_pos:
            self._done = True
        return a, rec

    def finished(self) -> bool:
        return self._done
