"""Reproducible randomized scene distributions.

Every method receives the IDENTICAL sampled episode (paired seeds): the sampler
is a pure function of (family, condition, severity, seed), so pairing is exact
by construction rather than by convention.

Three task families, not one pouring proxy:
  * ``upright_transport``  -- carry the object upright to a goal
  * ``constrained_place``  -- narrow corridor, tighter tolerance
  * ``align_insert``       -- alignment/insertion proxy, tight orientation

Conditions are predicate combinations; severity scales disturbance magnitude.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Tuple

import numpy as np

from ..synthetic.dynamics import Obstacle, SceneConfig

FAMILIES = ("upright_transport", "constrained_place", "align_insert")
CONDITIONS: Dict[str, FrozenSet[str]] = {
    "none": frozenset(),
    "obstacle": frozenset({"obstacle_present"}),
    "slip": frozenset({"object_slipped"}),
    "relocation": frozenset({"target_relocated"}),
    "obstacle+slip": frozenset({"obstacle_present", "object_slipped"}),
    "obstacle+relocation": frozenset({"obstacle_present", "target_relocated"}),
    "slip+relocation": frozenset({"object_slipped", "target_relocated"}),
}
SEVERITIES = ("low", "medium", "high")

_FAR = dict(p_start=np.array([9.0, 9.0]), p_end=np.array([9.0, 9.0]),
            radius=0.05, t_enter=0, t_exit=0)


@dataclass(frozen=True)
class EpisodeSpec:
    family: str
    condition: str
    severity: str
    seed: int

    def key(self) -> str:
        return f"{self.family}|{self.condition}|{self.severity}|{self.seed}"


def _family_params(family: str) -> dict:
    if family == "upright_transport":
        return dict(theta_pour=1.0, eps_goal=0.12, eps_theta=0.25, eps_danger=0.20,
                    v_max=0.06, w_max=0.30)
    if family == "constrained_place":
        return dict(theta_pour=0.8, eps_goal=0.10, eps_theta=0.22, eps_danger=0.18,
                    v_max=0.05, w_max=0.28)
    # align_insert: tightest orientation requirement
    return dict(theta_pour=1.2, eps_goal=0.10, eps_theta=0.18, eps_danger=0.18,
                v_max=0.05, w_max=0.32)


_SEV = {"low": 0.5, "medium": 1.0, "high": 1.5}


def _stable_seed(key: str) -> int:
    """Process-STABLE hash.  Python's built-in hash() is salted per process
    (PYTHONHASHSEED), so using it here silently made scenes differ between
    runs -- the benchmark was not reproducible across processes."""
    import hashlib
    return int(hashlib.blake2b(key.encode(), digest_size=4).hexdigest(), 16)


def sample_scene(spec: EpisodeSpec) -> SceneConfig:
    """Deterministic function of the spec -> identical for every method AND
    identical across processes."""
    rng = np.random.default_rng(_stable_seed(spec.key()))
    combo = CONDITIONS[spec.condition]
    s = _SEV[spec.severity]
    fp = _family_params(spec.family)

    p_init = np.array([rng.uniform(0.0, 0.25), rng.uniform(-0.10, 0.10)])
    p_goal = np.array([rng.uniform(0.90, 1.10), rng.uniform(-0.15, 0.15)])

    if "obstacle_present" in combo:
        # place the obstacle near the straight-line path
        alpha = rng.uniform(0.40, 0.62)
        base = p_init + alpha * (p_goal - p_init)
        off = rng.normal(scale=0.04, size=2)
        obs = dict(p_start=base + off, p_end=base + off,
                   radius=float(np.clip(0.09 + 0.04 * s, 0.07, 0.20)),
                   t_enter=int(rng.integers(1, 4)),
                   t_exit=int(np.clip(28 + 14 * s + rng.integers(-4, 5), 12, 70)))
    else:
        obs = dict(_FAR)

    slip_time = reloc_time = None
    drop = np.array([0.02, -0.03])
    reloc_delta = np.array([0.0, 0.0])

    if "object_slipped" in combo:
        # For COMPOUND conditions the slip must be active at the SAME detection
        # instant as the other predicate, otherwise the deferral policy turns it
        # into two sequential single-predicate events and nothing is ever
        # composed.  Firing it at t=1 guarantees a genuine predicate union.
        slip_time = 1 if len(combo) > 1 else int(rng.integers(2, 9))
        mag = 0.18 + 0.08 * s
        if "obstacle_present" in combo:
            # drop toward the obstacle so the two disturbances genuinely interact
            d = obs["p_start"] - p_init
            d = d / (np.linalg.norm(d) + 1e-9)
            drop = d * mag * 0.85 + rng.normal(scale=0.02, size=2)
        else:
            ang = rng.uniform(0, 2 * np.pi)
            drop = np.array([np.cos(ang), np.sin(ang)]) * mag

    if "target_relocated" in combo:
        reloc_time = 1 if len(combo) > 1 else int(rng.integers(2, 8))
        ang = rng.uniform(0, 2 * np.pi)
        reloc_delta = np.array([np.cos(ang), np.sin(ang)]) * (0.20 + 0.14 * s)

    return SceneConfig(
        horizon=140,
        p_init=p_init, p_goal=p_goal,
        obstacle=Obstacle(**obs),
        slip_time=slip_time, drop_offset=drop,
        relocation_time=reloc_time, relocation_delta=reloc_delta,
        **fp,
    )


def episode_grid(families=FAMILIES, conditions=None, severities=SEVERITIES,
                 n_seeds: int = 50) -> List[EpisodeSpec]:
    conditions = conditions or [c for c in CONDITIONS if c != "none"]
    out: List[EpisodeSpec] = []
    for f in families:
        for c in conditions:
            for sev in severities:
                for seed in range(n_seeds):
                    out.append(EpisodeSpec(f, c, sev, seed))
    return out
