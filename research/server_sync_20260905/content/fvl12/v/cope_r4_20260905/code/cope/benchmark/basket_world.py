"""Geometric substrate for the basket task.

The audit's deeper point: a symbolic mock executor gives the repair engine
nothing to verify against. `RolloutVerifier` simulates candidates under the same
kinematics and control limits as the environment, so the benchmark needs a real
environment. This module gives the basket task one, by *reusing* the frozen
`Synthetic2DEnv` rather than writing a second simulator.

Mapping:

    a "leg"          transport one object to one basket
    leg env          Synthetic2DEnv with p_goal = the basket position
    redirection      env.goal moves  -> target_relocated predicate
    basket removed   an Obstacle sits over the basket -> obstacle_present,
                     unsafe_clearance
    slip             the frozen env's own scheduled-slip mechanism

Because the leg env IS the frozen env, every controller, guard, predicate,
clip, and the rollout verifier's world model all apply unmodified. Nothing in
`rekep_repair/` is copied or re-implemented here.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from rekep_repair.synthetic.dynamics import Obstacle, SceneConfig
from rekep_repair.synthetic.env import Synthetic2DEnv

#: Basket positions in the workspace. Fixed, shared by every arm.
BASKET_POS: Dict[str, np.ndarray] = {
    "basket_A": np.array([1.00, 0.00]),
    "basket_B": np.array([1.00, 0.55]),
    "basket_C": np.array([0.55, -0.60]),
}

#: Where each object starts. Also fixed and shared.
OBJECT_POS: Dict[str, np.ndarray] = {
    "milk": np.array([0.00, 0.00]),
    "yogurt": np.array([0.00, 0.20]),
    "butter": np.array([0.00, -0.20]),
}

#: An obstacle far outside the workspace: "no obstruction", without special-casing.
_ABSENT = Obstacle(p_start=np.array([9.0, 9.0]), p_end=np.array([9.0, 9.0]),
                   radius=0.01, t_enter=0, t_exit=0)


def basket_position(name: str) -> np.ndarray:
    return BASKET_POS[name].copy()


def leg_config(obj: str, target: str, *, horizon: int = 300,
               blocked_targets: Tuple[str, ...] = ()) -> SceneConfig:
    """SceneConfig for one leg. Deterministic in (obj, target, blocked)."""
    cfg = SceneConfig(
        horizon=horizon,
        p_init=OBJECT_POS[obj].copy(),
        p_goal=basket_position(target),
        obstacle=_ABSENT,
    )
    # NOTE: an unavailable basket is deliberately NOT modelled as an obstacle.
    # A basket that has been taken off the table is an *absent target*, not an
    # obstruction: there is nothing to steer around and nothing to wait out.
    # Modelling it as a permanent obstacle made every repair candidate demand
    # `not obstacle_present`, which no operator could ever achieve, so the
    # rollout verifier hard-rejected all of them and the episode fell back --
    # correct verifier behaviour applied to an incorrectly stated problem.
    # Absence is carried by `blocked_targets` and shows up in
    # `placement_valid()`.
    return cfg


class BasketLegEnv(Synthetic2DEnv):
    """One leg, in the frozen environment.

    Adds exactly two things the frozen env does not have, both of which are
    *task* facts rather than physics: which object is being carried, and the
    ability for the semantic layer to retarget or block the goal mid-leg.
    """

    def __init__(self, obj: str, target: str, seed: int = 0,
                 horizon: int = 300, blocked_targets: Tuple[str, ...] = ()):
        self.object_name = obj
        self.target_name = target
        self._blocked = tuple(blocked_targets)
        super().__init__(leg_config(obj, target, horizon=horizon,
                                    blocked_targets=blocked_targets), seed=seed)

    # --- semantic-layer hooks (never called by the physics) --------------
    def retarget(self, new_target: str) -> None:
        """A user redirection. The frozen env reports this as target_relocated
        through `target_displacement`, with no special-casing anywhere."""
        self.target_name = new_target
        self.goal = basket_position(new_target)

    def set_blocked(self, blocked: Tuple[str, ...]) -> None:
        """Basket availability changed. Re-derives the obstacle from the config
        builder so blocked/unblocked go through one code path."""
        self._blocked = tuple(blocked)
        self.cfg.obstacle = leg_config(self.object_name, self.target_name,
                                       horizon=self.cfg.horizon,
                                       blocked_targets=self._blocked).obstacle

    @property
    def blocked_targets(self) -> Tuple[str, ...]:
        return self._blocked

    def at_goal(self, tol: float = 0.12) -> bool:
        return bool(np.linalg.norm(self.state[:2] - self.goal) <= tol)

    def placement_valid(self) -> bool:
        """A placement counts only if the basket is actually there."""
        return self.at_goal() and self.target_name not in self._blocked
