"""EventDetector -- turns an ExecutionContext into an Event.

Ground-truth deterministic detection by default.  A ``noise_model`` may be
attached for the robustness study (delay, false pos/neg, keypoint jitter);
Oracle detection uses ``noise_model=None``.
"""

from __future__ import annotations

from typing import Callable, Optional

from ..execution.context import ExecutionContext
from . import predicates as P
from .event import Event, EventType, NO_EVENT


class EventDetector:
    def __init__(
        self,
        d_safe: float,
        target_threshold: float = 0.15,
        noise_model: Optional["NoiseModel"] = None,
    ):
        self.d_safe = d_safe
        self.target_threshold = target_threshold
        self.noise_model = noise_model
        self._counter = 0

    def detect(self, ctx: ExecutionContext) -> Event:
        ev = self._detect_ground_truth(ctx)
        if self.noise_model is not None:
            ev = self.noise_model.corrupt(ev, ctx)
        return ev

    def _detect_ground_truth(self, ctx: ExecutionContext) -> Event:
        # priority: slip > intrusion > relocation
        if P.object_slipped(ctx):
            return self._mk(EventType.OBJECT_SLIP, 1.0, ("object",), ctx)
        if P.obstacle_intrusion(ctx, self.d_safe):
            sev = P.intrusion_severity(ctx, self.d_safe)
            return self._mk(EventType.OBSTACLE_INTRUSION, sev, ("obstacle",), ctx)
        if P.target_relocated(ctx, self.target_threshold):
            return self._mk(EventType.TARGET_RELOCATION, 1.0, ("target",), ctx)
        return NO_EVENT

    def _mk(self, et: EventType, sev: float, entities, ctx: ExecutionContext) -> Event:
        self._counter += 1
        return Event(
            event_type=et,
            severity=float(sev),
            affected_entities=tuple(entities),
            confidence=1.0,
            t=ctx.t,
            event_id=f"E{self._counter:04d}@t{ctx.t}",
        )


class NoiseModel:
    """Hook for the robustness study: delay, false positive/negative."""

    def __init__(
        self,
        delay: int = 0,
        p_false_neg: float = 0.0,
        p_false_pos: float = 0.0,
        rng=None,
    ):
        import numpy as np

        self.delay = delay
        self.p_false_neg = p_false_neg
        self.p_false_pos = p_false_pos
        self.rng = rng or np.random.default_rng(0)
        self._queue: list = []          # [(report_time, event)]

    def corrupt(self, ev: Event, ctx: ExecutionContext) -> Event:
        # false negative / false positive on the *sensed* event
        if ev.is_active and self.rng.random() < self.p_false_neg:
            ev = NO_EVENT
        elif not ev.is_active and self.rng.random() < self.p_false_pos:
            ev = Event(EventType.OBSTACLE_INTRUSION, 0.5, ("phantom",), 0.5, ctx.t,
                       f"FP@t{ctx.t}")

        if self.delay <= 0:
            return ev

        # detection delay: hold a fresh event and report it `delay` steps later
        if ev.is_active:
            self._queue.append((ctx.t + self.delay, ev))
        due = [e for (tt, e) in self._queue if tt <= ctx.t]
        self._queue = [(tt, e) for (tt, e) in self._queue if tt > ctx.t]
        return due[0] if due else NO_EVENT
