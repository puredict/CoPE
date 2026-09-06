"""Bounded safe fallback: when repair cannot be constructed or validated, the
system must reach a well-defined safe-stop state within a bounded horizon
(Theorem 4 spirit).  Here the fallback simply commands zero motion and marks
the program failed-safe after ``max_fallback_steps``.
"""

from __future__ import annotations

import numpy as np


class SafeFallback:
    def __init__(self, max_fallback_steps: int = 5):
        self.max_fallback_steps = max_fallback_steps
        self.steps = 0
        self.active = False

    def engage(self) -> None:
        self.active = True
        self.steps = 0

    def action(self) -> np.ndarray:
        self.steps += 1
        return np.zeros(3)

    def exhausted(self) -> bool:
        return self.steps >= self.max_fallback_steps
