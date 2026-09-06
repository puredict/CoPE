"""P0-4 --- paired-baseline specification for the GPU pilot.

Guarantees that every method arm receives an **identical** disturbance for a
given (seed, severity): same trigger step, same relocation vector, same
interpolation schedule, same detection threshold, same horizon. The method name
is deliberately *not* an input to :func:`disturbance_for`'s randomness, so it
cannot influence the disturbance.

Also fixes a v1 defect: with ``linspace(pos0, pos0-0.15y, num=5)`` and a 0.05
threshold, the detected displacement was **always exactly 0.075 m** and severity
**always 0.5** -- constants masquerading as observations. Here the interpolation
is fine-grained (``step_quantum`` well below the threshold) and the severity is
the *total* relocation magnitude, so detection and severity are decoupled.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np

METHODS = (
    "wrapped_nominal_no_disturbance",   # control: wrapper on, no disturbance
    "nominal_with_disturbance",         # disturbance, fixed ReKep structure
    "online_repair",                    # disturbance + online structural repair
)
SEVERITIES_M = (0.075, 0.150)


def _stable_seed(key: str) -> int:
    """Process-stable seed (Python's hash() is salted per process)."""
    return int(hashlib.blake2b(key.encode(), digest_size=4).hexdigest(), 16)


@dataclass(frozen=True)
class PilotSpec:
    seed: int
    severity_m: float
    method: str
    task: str = "rekep_pen_in_holder"
    horizon_steps: int = 900

    def key(self) -> str:
        """Pairing key -- deliberately EXCLUDES the method."""
        return f"{self.task}|{self.severity_m:.3f}|{self.seed}"

    def episode_id(self) -> str:
        return f"{self.task}|{self.severity_m:.3f}|{self.seed}|{self.method}"


@dataclass(frozen=True)
class DisturbanceSpec:
    """The disturbance, fully determined by (task, severity, seed)."""
    relocation_vector: np.ndarray
    trigger_step: int
    n_interpolation_steps: int
    detection_threshold_m: float
    horizon_steps: int
    apply_disturbance: bool

    @property
    def step_quantum(self) -> float:
        return float(np.linalg.norm(self.relocation_vector)) / self.n_interpolation_steps

    def schedule(self, start_position: np.ndarray) -> List[np.ndarray]:
        p0 = np.asarray(start_position, float)
        return [p0 + self.relocation_vector * (i / self.n_interpolation_steps)
                for i in range(self.n_interpolation_steps + 1)]

    def to_dict(self) -> dict:
        return {
            "relocation_vector": [float(v) for v in self.relocation_vector],
            "relocation_magnitude_m": float(np.linalg.norm(self.relocation_vector)),
            "trigger_step": self.trigger_step,
            "n_interpolation_steps": self.n_interpolation_steps,
            "step_quantum_m": round(self.step_quantum, 6),
            "detection_threshold_m": self.detection_threshold_m,
            "horizon_steps": self.horizon_steps,
            "apply_disturbance": self.apply_disturbance,
        }


def disturbance_for(spec: PilotSpec,
                    detection_threshold_m: float = 0.02) -> DisturbanceSpec:
    """Deterministic disturbance for a (task, severity, seed) pair.

    Identical for every method: the RNG is keyed on ``spec.key()``, which does
    not contain the method. The only method-dependent field is
    ``apply_disturbance`` (False for the no-disturbance control arm).
    """
    if spec.method not in METHODS:
        raise ValueError(f"unknown method {spec.method!r}; expected one of {METHODS}")
    rng = np.random.default_rng(_stable_seed(spec.key()))

    # direction in the table plane, magnitude = severity
    angle = float(rng.uniform(0.0, 2.0 * np.pi))
    vec = np.array([np.cos(angle), np.sin(angle), 0.0]) * float(spec.severity_m)

    # trigger during ReKep stage 3, jittered per seed
    trigger = int(rng.integers(150, 200))

    # 20 sub-steps -> quantum <= 0.0075 m, far below the 0.02 m threshold, so the
    # detected displacement is NOT pinned to a single value across seeds
    n_steps = 20

    return DisturbanceSpec(
        relocation_vector=vec,
        trigger_step=trigger,
        n_interpolation_steps=n_steps,
        detection_threshold_m=detection_threshold_m,
        horizon_steps=spec.horizon_steps,
        apply_disturbance=(spec.method != "wrapped_nominal_no_disturbance"),
    )


def pilot_grid(seeds_per_severity: int = 5,
               severities: Tuple[float, ...] = SEVERITIES_M,
               methods: Tuple[str, ...] = ("nominal_with_disturbance", "online_repair"),
               ) -> List[PilotSpec]:
    """The 20-episode pilot grid: 2 methods x 2 severities x 5 paired seeds."""
    out: List[PilotSpec] = []
    for sev in severities:
        for seed in range(seeds_per_severity):
            for m in methods:
                out.append(PilotSpec(seed=seed, severity_m=sev, method=m))
    return out


def assert_paired(a: PilotSpec, b: PilotSpec) -> None:
    """Raise unless two specs form a legitimate pair (same disturbance)."""
    if a.key() != b.key():
        raise AssertionError(f"not a pair: {a.key()} != {b.key()}")
    da, db = disturbance_for(a), disturbance_for(b)
    if not np.allclose(da.relocation_vector, db.relocation_vector) \
            or da.trigger_step != db.trigger_step \
            or da.n_interpolation_steps != db.n_interpolation_steps \
            or da.detection_threshold_m != db.detection_threshold_m \
            or da.horizon_steps != db.horizon_steps:
        raise AssertionError("paired specs received different disturbances")
