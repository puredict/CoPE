"""Physical leg executor --- runs the task through the FROZEN execution layer.

Replaces the symbolic mock as the benchmark's default. A "leg" is one object
transported to one basket, executed step-by-step through
`rekep_repair.execution.controller.control` inside a `BasketLegEnv` (which *is*
`Synthetic2DEnv`). Guards come from `rekep_repair.execution.guard_monitor`.

The point of the change: `RolloutVerifier` predicts what a candidate repair will
do under these exact kinematics and control limits. Against a symbolic mock it
had nothing to predict, so verification was vacuous. Here a candidate that would
collide, time out, or fail to restore is genuinely rejected before execution.

The mock is kept (`mock_executor.py`) for the fast semantic-only tests and is no
longer what the pilot runs.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from rekep_repair.execution.controller import control
from rekep_repair.execution.guard_monitor import stage_exit
from rekep_repair.policies.common import build_params
from rekep_repair.program.stage import StageState

from ..naming import canonical_id
from .basket_world import BasketLegEnv, basket_position


def _draw(key: str) -> float:
    h = hashlib.blake2b(key.encode(), digest_size=8).hexdigest()
    return int(h, 16) / float(1 << 64)


@dataclass
class LegResult:
    goal_id: str
    obj: str
    target: Optional[str]
    placed: bool = False
    reason: str = ""
    steps: int = 0
    collision: bool = False
    min_clearance: float = float("inf")
    retargeted_to: Optional[str] = None
    abandoned: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class PhysicalLegExecutor:
    """Drives legs through the frozen execution layer.

    Method-neutral: it is handed a compiled goal dict and an engine, never a
    policy. The same object serves every arm, and the per-attempt disturbance
    draw is keyed on the physical action so the arms get common random numbers.
    """

    def __init__(self, seed: int = 0, *, p_disturbance: float = 0.0,
                 max_leg_steps: int = 260, horizon: int = 300):
        self.seed = seed
        self.p_disturbance = p_disturbance
        self.max_leg_steps = max_leg_steps
        self.horizon = horizon
        self.attempts: Dict[str, int] = {}
        self.legs: List[LegResult] = []
        self.total_steps = 0
        self.env: Optional[BasketLegEnv] = None

    # ------------------------------------------------------------------
    def begin_leg(self, goal: Dict[str, Any], engine, world: Dict[str, Any]
                  ) -> BasketLegEnv:
        obj = goal["object"]
        target = goal.get("target")
        blocked = tuple(world.get("unavailable_targets", []) or ())
        self.env = BasketLegEnv(obj, target, seed=self.seed,
                                horizon=self.horizon, blocked_targets=blocked)
        engine.begin_leg(self.env)
        self.attempts[obj] = self.attempts.get(obj, 0) + 1
        return self.env

    # ------------------------------------------------------------------
    def step(self, engine) -> Dict[str, Any]:
        """One control step of the current leg, through the frozen controller."""
        env = self.env
        ctx = env.observe()
        stage = engine.program.active_stage()
        params = build_params(env.cfg, task_goal=ctx.task_goal)
        behavior = stage.metadata.get("behavior", "progress")
        a = control(behavior, ctx, stage, engine.continuation, params,
                    ctx.task_goal)
        env.step(a)
        self.total_steps += 1
        return {"clearance": float(ctx.clearance),
                "collision": bool(ctx.clearance < 0.0)}

    # ------------------------------------------------------------------
    def leg_done(self, engine) -> Tuple[bool, str]:
        env = self.env
        if env.at_goal():
            if env.target_name in env.blocked_targets:
                return True, "target unavailable at arrival"
            return True, "reached target"
        if env.t >= env.cfg.horizon:
            return True, "horizon exhausted"
        return False, ""

    # ------------------------------------------------------------------
    def finish_leg(self, goal: Dict[str, Any], reason: str, steps: int,
                   min_clearance: float, collision: bool,
                   force_failed: bool = False) -> LegResult:
        """`force_failed` is for a goal the semantic layer withdrew mid-leg: it
        must not count as placed even if the robot happens to be standing at the
        basket when the cancellation lands."""
        env = self.env
        placed = (bool(env.placement_valid()) and not collision
                  and not force_failed)
        if placed and self.p_disturbance > 0.0:
            # optional stochastic grasp/placement failure, keyed on the physical
            # action so both arms draw the same luck for the same attempt
            n = self.attempts.get(env.object_name, 1) - 1
            if _draw(f"{self.seed}|{env.object_name}|{n}") < self.p_disturbance:
                placed, reason = False, "placement disturbance"
        res = LegResult(goal_id=goal["id"], obj=env.object_name,
                        target=env.target_name, placed=placed,
                        reason=reason if not placed else "placed",
                        steps=steps, collision=collision,
                        min_clearance=min_clearance)
        self.legs.append(res)
        return res
