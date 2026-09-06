"""B2 -- safe stop and resume: stop while the obstacle is near, then continue
the current stage.  No ordered repair, no continuation contract, no mode
suspension (it keeps the pour tilt while stopped)."""

from __future__ import annotations

import numpy as np

from ..events.detector import EventDetector
from ..events.event import EventType
from ..execution.context import ExecutionContext
from ..execution.controller import control
from ..execution.executor import RecoveryPolicy
from .common import build_params, nominal_pour_stage, record


class SafeStopPolicy(RecoveryPolicy):
    name = "safe_stop"

    def reset(self, env) -> None:
        self.env = env
        self.cfg = env.cfg
        self.params = build_params(self.cfg)
        self.detector = EventDetector(d_safe=self.cfg.d_react)
        self.stage = nominal_pour_stage(behavior="progress")
        self._done = False

    def act(self, ctx: ExecutionContext):
        ev = self.detector.detect(ctx)
        if ev.event_type == EventType.OBSTACLE_INTRUSION:
            a = np.array([0.0, 0.0, 0.0])          # stop (keeps current tilt)
            rec = record(ctx.t, a, self.stage, "SUSPENDED", event_id=ev.event_id)
            return a, rec
        a = control("progress", ctx, self.stage, None, self.params, ctx.task_goal)
        rec = record(ctx.t, a, self.stage, "ACTIVE")
        if np.linalg.norm(ctx.position - ctx.task_goal) < self.params.tol_pos:
            self._done = True
        return a, rec

    def finished(self) -> bool:
        return self._done
