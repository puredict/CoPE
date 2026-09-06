"""Model mismatch (B2): separate the planning model f-hat from execution f.

The rollout verifier plans with the NOMINAL model.  The environment executes
with a perturbed one.  Every dimension is independently configurable, and all
methods receive paired seeds so the realized disturbance sequence is identical.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class MismatchConfig:
    """Execution-side deviations from the planning model."""

    translation_gain: float = 1.0      # actual/commanded translation
    rotation_gain: float = 1.0         # actual/commanded rotation
    action_noise: float = 0.0          # sigma of additive action noise
    object_obs_noise: float = 0.0      # sigma on observed object position
    obstacle_pred_error: float = 0.0   # planner's obstacle position error
    detector_delay: int = 0            # steps before an event is reported
    guard_delay: int = 0               # steps before guards see the state
    regrasp_failure_p: float = 0.0     # probability a regrasp attempt fails
    release_drift: float = 0.0         # per-step drift of a released object
    target_pred_error: float = 0.0     # planner's target position error

    @property
    def is_nominal(self) -> bool:
        return (self.translation_gain == 1.0 and self.rotation_gain == 1.0
                and self.action_noise == 0.0 and self.object_obs_noise == 0.0
                and self.obstacle_pred_error == 0.0 and self.detector_delay == 0
                and self.guard_delay == 0 and self.regrasp_failure_p == 0.0
                and self.release_drift == 0.0 and self.target_pred_error == 0.0)


LEVELS = {
    "none": MismatchConfig(),
    "mild": MismatchConfig(
        translation_gain=0.95, rotation_gain=0.95, action_noise=0.004,
        object_obs_noise=0.01, obstacle_pred_error=0.02, detector_delay=0,
        guard_delay=0, regrasp_failure_p=0.05, release_drift=0.002,
        target_pred_error=0.01),
    "moderate": MismatchConfig(
        translation_gain=0.88, rotation_gain=0.88, action_noise=0.010,
        object_obs_noise=0.025, obstacle_pred_error=0.05, detector_delay=1,
        guard_delay=1, regrasp_failure_p=0.15, release_drift=0.005,
        target_pred_error=0.03),
    "severe": MismatchConfig(
        translation_gain=0.75, rotation_gain=0.75, action_noise=0.020,
        object_obs_noise=0.05, obstacle_pred_error=0.10, detector_delay=2,
        guard_delay=2, regrasp_failure_p=0.30, release_drift=0.010,
        target_pred_error=0.06),
}
LEVEL_ORDER = ("none", "mild", "moderate", "severe")


class MismatchedEnv:
    """Wraps Synthetic2DEnv, applying execution-side mismatch.

    The wrapped env is what the POLICY acts on; the verifier keeps using the
    nominal cfg, so planning and execution genuinely disagree.
    """

    def __init__(self, env, mm: MismatchConfig, seed: int = 0):
        self.env = env
        self.mm = mm
        self.rng = np.random.default_rng(seed + 9973)
        self._regrasp_blocked = False
        self._ctx_buf: list = []      # guard_delay: stale observations
        self._pred_buf: list = []     # detector_delay: stale predicates

    # --- delegation -------------------------------------------------------
    def __getattr__(self, item):
        return getattr(self.env, item)

    @property
    def cfg(self):
        return self.env.cfg

    def reset(self):
        self._regrasp_blocked = False
        self._ctx_buf = []
        self._pred_buf = []
        self.env.reset()
        return self.observe()

    # --- perturbed observation -------------------------------------------
    def _perturbed_now(self):
        ctx = self.env.observe()
        mm = self.mm
        if mm.object_obs_noise > 0 and ctx.reacquire_pos is not None:
            ctx.reacquire_pos = ctx.reacquire_pos + self.rng.normal(
                scale=mm.object_obs_noise, size=2)
        if mm.target_pred_error > 0 and ctx.task_goal is not None:
            ctx.task_goal = ctx.task_goal + self.rng.normal(
                scale=mm.target_pred_error, size=2)
        if mm.obstacle_pred_error > 0 and ctx.obstacle_pos is not None:
            ctx.obstacle_pos = ctx.obstacle_pos + self.rng.normal(
                scale=mm.obstacle_pred_error, size=2)
        return ctx

    def observe(self):
        """Perturbed observation, optionally DELAYED by ``guard_delay`` steps
        (guards and controllers then act on a stale view of the world)."""
        ctx = self._perturbed_now()
        d = self.mm.guard_delay
        if d <= 0:
            return ctx
        self._ctx_buf.append(ctx)
        if len(self._ctx_buf) > d:
            return self._ctx_buf.pop(0)
        return self._ctx_buf[0]

    def predicates(self, d_react: float, target_threshold: float = 0.15):
        """Predicates, optionally DELAYED by ``detector_delay`` steps, so an
        event is reported later than it actually occurs."""
        p = self.env.predicates(d_react, target_threshold)
        d = self.mm.detector_delay
        if d <= 0:
            return p
        self._pred_buf.append(p)
        if len(self._pred_buf) > d:
            return self._pred_buf.pop(0)
        return self._pred_buf[0]

    # --- perturbed execution ---------------------------------------------
    def step(self, action: np.ndarray):
        mm = self.mm
        a = np.asarray(action, float).copy()
        a[:2] *= mm.translation_gain
        a[2] *= mm.rotation_gain
        if mm.action_noise > 0:
            a = a + self.rng.normal(scale=mm.action_noise, size=3)

        was_grasped = self.env.grasped
        # stochastic regrasp failure: block the automatic pickup this step
        if (not was_grasped) and mm.regrasp_failure_p > 0:
            if self.rng.random() < mm.regrasp_failure_p:
                self._regrasp_blocked = True

        # unmodeled drift of a released object
        if (not was_grasped) and mm.release_drift > 0 and self.env.drop_pos is not None:
            self.env.drop_pos = self.env.drop_pos + self.rng.normal(
                scale=mm.release_drift, size=2)

        ctx = self.env.step(a)

        if self._regrasp_blocked and self.env.grasped and not was_grasped:
            # undo the pickup that the nominal env granted
            self.env.grasped = False
            self.env.slipped = True
            if self.env.drop_pos is None:
                self.env.drop_pos = self.env.state[:2] + np.array([0.03, 0.03])
            self._regrasp_blocked = False
        # IMPORTANT: return the PERTURBED (and possibly delayed) observation.
        # Returning the inner env's clean ctx silently bypassed every
        # observation-side mismatch dimension.
        return self.observe()


# --- per-dimension attribution (Track A) ------------------------------------
# Each source is varied ALONE, at the same four levels, so its individual
# contribution can be attributed.  Level values match the corresponding field
# of LEVELS[...] so "moderate" here means the same magnitude it has in the
# joint configuration.
SOURCE_LEVELS = {
    "translation_gain":   {"none": 1.0,  "mild": 0.95, "moderate": 0.88, "severe": 0.75},
    "rotation_gain":      {"none": 1.0,  "mild": 0.95, "moderate": 0.88, "severe": 0.75},
    "action_noise":       {"none": 0.0,  "mild": 0.004,"moderate": 0.010,"severe": 0.020},
    "object_obs_noise":   {"none": 0.0,  "mild": 0.01, "moderate": 0.025,"severe": 0.05},
    "obstacle_pred_error":{"none": 0.0,  "mild": 0.02, "moderate": 0.05, "severe": 0.10},
    "detector_delay":     {"none": 0,    "mild": 0,    "moderate": 1,    "severe": 2},
    "guard_delay":        {"none": 0,    "mild": 0,    "moderate": 1,    "severe": 2},
    "regrasp_failure_p":  {"none": 0.0,  "mild": 0.05, "moderate": 0.15, "severe": 0.30},
    "release_drift":      {"none": 0.0,  "mild": 0.002,"moderate": 0.005,"severe": 0.010},
    "target_pred_error":  {"none": 0.0,  "mild": 0.01, "moderate": 0.03, "severe": 0.06},
}
SOURCES = tuple(SOURCE_LEVELS)


def single_source(source: str, level: str) -> MismatchConfig:
    """A config with ONLY ``source`` perturbed, everything else nominal."""
    if source not in SOURCE_LEVELS:
        raise KeyError(source)
    return replace(MismatchConfig(), **{source: SOURCE_LEVELS[source][level]})
