"""Continuation and handoff contracts for ReKep-R.

A *contract* is a predicate over the execution state that must hold at a
program boundary. Two kinds matter for repair:

* ``EntryContract``  -- the precondition ``Pre(s)`` of a stage ``s``.  A repair
  is only *restorable* if its final restore stage lands in the entry contract
  of the interrupted (or next) nominal stage.
* ``HandoffContract`` -- a stricter, pose-level contract used by the restore
  stage to hand control back smoothly (realignment).

Contracts are intentionally lightweight and side-effect free so they can be
evaluated cheaply inside the receding-horizon loop.  They operate on the
synthetic state ``x`` and, optionally, keypoints ``k``.  In the OmniGibson
port the same interface is backed by keypoint predicates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np


# A predicate maps (state, keypoints) -> bool.  keypoints may be None in the
# synthetic domain where the state is fully observed.
Predicate = Callable[[np.ndarray, Optional[np.ndarray]], bool]


@dataclass(frozen=True)
class Contract:
    """A named predicate over execution state.

    ``margin`` returns a signed slack: >= 0 means satisfied.  This lets the
    scorer measure *how close* a restore state is to a contract, not only a
    boolean, which is what ``L_realign`` needs.
    """

    name: str
    predicate: Predicate
    margin_fn: Optional[Callable[[np.ndarray, Optional[np.ndarray]], float]] = None

    def holds(self, x: np.ndarray, k: Optional[np.ndarray] = None) -> bool:
        return bool(self.predicate(x, k))

    def margin(self, x: np.ndarray, k: Optional[np.ndarray] = None) -> float:
        if self.margin_fn is not None:
            return float(self.margin_fn(x, k))
        # Fall back to a hard 0/1 slack if no continuous margin is provided.
        return 0.0 if self.holds(x, k) else -1.0


def ball_contract(
    name: str,
    target: np.ndarray,
    radius: float,
    weight: Optional[np.ndarray] = None,
) -> Contract:
    """Contract satisfied when ``||x_sel - target||_W <= radius``.

    ``weight`` selects/weights the state dimensions that matter for this
    contract (e.g. only orientation for a pouring-angle handoff).
    """
    target = np.asarray(target, dtype=float)
    dim = target.shape[0]
    W = np.ones(dim) if weight is None else np.asarray(weight, dtype=float)

    def _dist(x: np.ndarray) -> float:
        xs = np.asarray(x, dtype=float)[:dim]
        return float(np.sqrt(np.sum(W * (xs - target) ** 2)))

    return Contract(
        name=name,
        predicate=lambda x, k=None: _dist(x) <= radius,
        margin_fn=lambda x, k=None: radius - _dist(x),
    )


ALWAYS = Contract(name="always", predicate=lambda x, k=None: True, margin_fn=lambda x, k=None: 1.0)
