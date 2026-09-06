"""Paired statistics: Wilson intervals, paired bootstrap, McNemar, Holm."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np


def wilson_interval(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score interval for a proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def mcnemar_exact(a: Sequence[bool], b: Sequence[bool]) -> Tuple[int, int, float]:
    """Exact (binomial) McNemar test on paired binary outcomes.
    Returns (b01, b10, p_value): b01 = a wrong & b right, b10 = a right & b wrong."""
    a, b = list(a), list(b)
    b01 = sum(1 for x, y in zip(a, b) if (not x) and y)
    b10 = sum(1 for x, y in zip(a, b) if x and (not y))
    n = b01 + b10
    if n == 0:
        return b01, b10, 1.0
    k = min(b01, b10)
    # two-sided exact binomial with p=0.5
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return b01, b10, min(1.0, 2 * tail)


def paired_bootstrap_diff(a: Sequence[float], b: Sequence[float],
                          n_boot: int = 10000, seed: int = 0,
                          alpha: float = 0.05) -> Tuple[float, float, float]:
    """Paired bootstrap CI for mean(b) - mean(a).  Returns (diff, lo, hi)."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    assert a.shape == b.shape and a.size > 0
    d = b - a
    obs = float(d.mean())
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, d.size, size=(n_boot, d.size))
    means = d[idx].mean(axis=1)
    lo = float(np.quantile(means, alpha / 2))
    hi = float(np.quantile(means, 1 - alpha / 2))
    return obs, lo, hi


def holm_correction(pvals: Dict[str, float]) -> Dict[str, float]:
    """Holm-Bonferroni step-down adjusted p-values."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    adjusted: Dict[str, float] = {}
    prev = 0.0
    for i, (k, p) in enumerate(items):
        val = min(1.0, (m - i) * p)
        val = max(val, prev)          # enforce monotonicity
        adjusted[k] = val
        prev = val
    return adjusted


@dataclass
class ProportionSummary:
    label: str
    k: int
    n: int

    @property
    def rate(self) -> float:
        return self.k / self.n if self.n else 0.0

    def wilson(self) -> Tuple[float, float]:
        return wilson_interval(self.k, self.n)

    def fmt(self) -> str:
        lo, hi = self.wilson()
        return f"{self.rate:.3f} [{lo:.3f}, {hi:.3f}]"
