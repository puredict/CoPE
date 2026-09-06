"""Theorem 1: simultaneous-goal conflict lower bound.

A path-only reaction keeps the robot inside one stage and optimizes the nominal
objective and the interruption objective *simultaneously*:

    J(x) = lambda * d(x, A)^2 + mu * d(x, B)^2

where A is the nominal target set and B is the interruption target set with
separation ``delta = dist(A, B) > 0``.  Using ``d(x,A) + d(x,B) >= delta`` (a
triangle inequality that holds for *any* sets), we get the tight bound

    inf_x J(x) >= (lambda * mu / (lambda + mu)) * delta^2                (Thm 1)

(inf, not min: A and B need not be closed, so the value need not be attained.)
Ordered repair satisfies A and B in *different* time windows, which removes the
SIMULTANEOUS-conflict term -- the per-window simultaneous floor is 0.  It does
NOT make the total trajectory cost zero: an A -> B -> A_restore trace still pays
motion and switching cost and needs each set individually reachable with
feasible transitions.

Corollary (threshold failure, FOR FIXED WEIGHTS): fix lambda, mu > 0.  If task
success needs J(x) <= epsilon < (lambda*mu/(lambda+mu)) delta^2, then no
fixed-stage simultaneous optimum WITH THOSE WEIGHTS can succeed.  The floor is
not uniform over weights (lambda -> 0 drives it to 0), so a claim that no
weighting can succeed requires bounding the weights away from zero.
See docs/THEOREM.md.

This module both states the closed form and *validates it numerically* so the
paper's Figure 2 (bound vs. numerics) can be regenerated with one call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Tuple

import numpy as np
from scipy.optimize import minimize


DistToSet = Callable[[np.ndarray], float]


def conflict_lower_bound(lam: float, mu: float, delta: float) -> float:
    """Closed-form floor (lambda*mu/(lambda+mu)) * delta^2."""
    return (lam * mu / (lam + mu)) * delta ** 2


def point_set(center: np.ndarray) -> DistToSet:
    center = np.asarray(center, dtype=float)
    return lambda x: float(np.linalg.norm(np.asarray(x, dtype=float) - center))


def ball_set(center: np.ndarray, radius: float) -> DistToSet:
    center = np.asarray(center, dtype=float)
    return lambda x: float(max(0.0, np.linalg.norm(np.asarray(x, dtype=float) - center) - radius))


def path_only_cost(x: np.ndarray, dA: DistToSet, dB: DistToSet, lam: float, mu: float) -> float:
    return lam * dA(x) ** 2 + mu * dB(x) ** 2


def min_path_only_cost(
    dA: DistToSet,
    dB: DistToSet,
    lam: float,
    mu: float,
    x0: np.ndarray,
    n_restarts: int = 8,
    seed: int = 0,
) -> Tuple[float, np.ndarray]:
    """Numerically minimize J via multi-start L-BFGS-B (robust to the kink at
    the set boundary)."""
    rng = np.random.default_rng(seed)
    x0 = np.asarray(x0, dtype=float)
    best_val, best_x = np.inf, x0
    for r in range(n_restarts):
        start = x0 if r == 0 else x0 + rng.normal(scale=1.0, size=x0.shape)
        res = minimize(
            lambda x: path_only_cost(x, dA, dB, lam, mu),
            start,
            method="L-BFGS-B",
        )
        if res.fun < best_val:
            best_val, best_x = float(res.fun), res.x
    return best_val, best_x


@dataclass
class BoundCheck:
    delta: float
    lam: float
    mu: float
    bound: float
    numeric_min: float
    slack: float          # numeric_min - bound  (should be >= ~0)


def validate_bound_ball(
    lam: float,
    mu: float,
    delta: float,
    radius: float = 0.3,
    dim: int = 2,
) -> BoundCheck:
    """Place two balls whose *surface* separation is exactly ``delta`` and
    check the numeric minimum against the closed-form bound."""
    a = np.zeros(dim)
    b = np.zeros(dim)
    b[0] = delta + 2 * radius        # center distance so surface gap == delta
    dA, dB = ball_set(a, radius), ball_set(b, radius)
    x0 = 0.5 * (a + b)
    num, _ = min_path_only_cost(dA, dB, lam, mu, x0)
    bound = conflict_lower_bound(lam, mu, delta)
    return BoundCheck(delta, lam, mu, bound, num, num - bound)


def sweep_delta(
    deltas: List[float],
    lam: float = 2.0,
    mu: float = 5.0,
    radius: float = 0.3,
) -> List[BoundCheck]:
    """Figure 2 data: bound vs. numeric min across separation ``delta``."""
    return [validate_bound_ball(lam, mu, d, radius=radius) for d in deltas]


def sweep_ratio(
    ratios: List[float],
    delta: float = 1.0,
    mu: float = 5.0,
    radius: float = 0.3,
) -> List[BoundCheck]:
    """Vary lambda/mu at fixed delta.  NOTE: this shows the floor is positive
    for each RATIO tested at fixed mu; it does NOT show the floor is uniform
    over all weights -- driving lambda (or mu) toward 0 drives the floor to 0.
    See docs/THEOREM.md."""
    out = []
    for ratio in ratios:
        lam = ratio * mu
        out.append(validate_bound_ball(lam, mu, delta, radius=radius))
    return out
