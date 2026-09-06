"""Single source of truth for action limiting.

P0-A: the environment and the rollout verifier MUST clip actions identically,
otherwise the verifier predicts a trajectory the world cannot execute (or vice
versa).  Previously the environment clipped each translational axis
independently -- admitting up to sqrt(2)*v_max on a diagonal -- while the
rollout clipped the 2-D norm.  Both now call ``clip_action``.

Convention: **norm-limited translation**.  ||(dx, dy)|| <= v_max, and
|dtheta| <= w_max.  Norm limiting is the physically meaningful choice (a
diagonal move is not faster than an axis-aligned one) and it is what the
feasibility/reachability arithmetic assumes.
"""

from __future__ import annotations

import numpy as np


def clip_action(action: np.ndarray, v_max: float, w_max: float) -> np.ndarray:
    """Limit a (dx, dy, dtheta) action: translation by 2-D norm, rotation by
    magnitude.  Returns a new array; the input is not modified."""
    a = np.asarray(action, dtype=float).copy()
    n = float(np.linalg.norm(a[:2]))
    if n > v_max:
        a[:2] *= v_max / n
    a[2] = float(np.clip(a[2], -w_max, w_max))
    return a
