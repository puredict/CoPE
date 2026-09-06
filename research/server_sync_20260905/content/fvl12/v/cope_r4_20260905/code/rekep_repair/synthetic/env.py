"""Synthetic2DEnv -- a closed-loop stepping simulator with explicit control
limits.  This is the single environment every method runs through, so any
performance difference comes from the recovery policy, not from a different
dynamics model, control limit, disturbance, horizon, or seed.

State x = (p_x, p_y, theta).  Action a = (dp_x, dp_y, dtheta), clipped to
(v_max, v_max, w_max) per step.  Kinematic integration x <- x + a.
The obstacle follows its scheduled path; an optional slip drops the object.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..execution.action import clip_action
from ..execution.context import ExecutionContext
from .dynamics import SceneConfig, clearance


class Synthetic2DEnv:
    def __init__(self, cfg: SceneConfig, seed: int = 0):
        self.cfg = cfg
        self.rng = np.random.default_rng(seed)
        self.reset()

    # --- lifecycle --------------------------------------------------------
    def reset(self) -> ExecutionContext:
        self.t = 0
        self.state = np.array([self.cfg.p_init[0], self.cfg.p_init[1], self.cfg.theta_pour], float)
        self.grasped = True
        self.slipped = False
        self.drop_pos: Optional[np.ndarray] = None
        self.goal = self.cfg.p_goal.astype(float).copy()   # may relocate
        return self.observe()

    def observe(self) -> ExecutionContext:
        cfg = self.cfg
        o = cfg.obstacle.position(self.t)
        clr = clearance(self.state[:2], cfg.obstacle, self.t)
        obj_pos = self.state[:2].copy() if self.grasped else self.drop_pos.copy()
        return ExecutionContext(
            t=self.t,
            state=self.state.copy(),
            obstacle_pos=None if o is None else o.copy(),
            obstacle_radius=cfg.obstacle.radius,
            clearance=clr,
            task_goal=self.goal.copy(),
            nominal_goal=cfg.p_goal.copy(),
            target_displacement=float(np.linalg.norm(self.goal - cfg.p_goal)),
            object_pos=obj_pos,
            object_grasped=self.grasped,
            slipped=self.slipped,
            reacquire_pos=None if self.drop_pos is None else self.drop_pos.copy(),
            attachments={"object": "grasped" if self.grasped else "released"},
        )

    def predicates(self, d_react: float, target_threshold: float = 0.15):
        """The full active predicate set -- handed IDENTICALLY to every policy
        so no method sees a richer view of the world than another."""
        from ..repair.abstract_state import WorldPredicates
        ctx = self.observe()
        return WorldPredicates(
            obstacle_present=ctx.obstacle_pos is not None and ctx.clearance < d_react,
            unsafe_clearance=ctx.obstacle_pos is not None and ctx.clearance < d_react,
            object_slipped=not ctx.object_grasped,
            target_relocated=ctx.target_displacement > target_threshold,
        )

    # --- stepping ---------------------------------------------------------
    def clip_action(self, a: np.ndarray) -> np.ndarray:
        """Shared with the rollout verifier -- see execution/action.py."""
        return clip_action(a, self.cfg.v_max, self.cfg.w_max)

    def step(self, action: np.ndarray) -> ExecutionContext:
        cfg = self.cfg
        a = self.clip_action(action)
        self.state = self.state + a
        self.state[:2] = np.clip(self.state[:2], cfg.ws_lo, cfg.ws_hi)
        self.t += 1

        # scheduled target relocation
        if cfg.relocation_time is not None and self.t == cfg.relocation_time:
            self.goal = self.goal + cfg.relocation_delta

        # scheduled slip
        if cfg.slip_time is not None and self.t == cfg.slip_time and self.grasped:
            self.grasped = False
            self.slipped = True
            self.drop_pos = self.state[:2] + cfg.drop_offset

        # autonomous re-grasp when the ee returns to the dropped object
        if (not self.grasped) and self.drop_pos is not None:
            if np.linalg.norm(self.state[:2] - self.drop_pos) < 0.05:
                self.grasped = True
                self.slipped = False
                self.drop_pos = None

        return self.observe()

    @property
    def done(self) -> bool:
        return self.t >= self.cfg.horizon
