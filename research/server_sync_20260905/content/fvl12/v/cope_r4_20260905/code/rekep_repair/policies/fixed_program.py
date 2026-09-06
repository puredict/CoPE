"""B0 -- original fixed ReKep program: no event handling, no reaction."""

from __future__ import annotations

import numpy as np

from ..execution.context import ExecutionContext
from ..execution.controller import control
from ..execution.executor import RecoveryPolicy
from .common import build_params, nominal_pour_stage, record


class FixedProgramPolicy(RecoveryPolicy):
    name = "fixed_program"

    def reset(self, env) -> None:
        self.env = env
        self.cfg = env.cfg
        self.params = build_params(self.cfg)
        self.stage = nominal_pour_stage(behavior="progress_noavoid")
        self._done = False

    def act(self, ctx: ExecutionContext):
        a = control("progress_noavoid", ctx, self.stage, None, self.params, ctx.task_goal)
        rec = record(ctx.t, a, self.stage, "ACTIVE")
        if np.linalg.norm(ctx.position - ctx.task_goal) < self.params.tol_pos:
            self._done = True
        return a, rec

    def finished(self) -> bool:
        return self._done
