"""2D synthetic theory environment and experiments (CPU-only)."""

from .conflict_bound import (
    conflict_lower_bound,
    validate_bound_ball,
    sweep_delta,
    sweep_ratio,
    BoundCheck,
)

__all__ = [
    "conflict_lower_bound",
    "validate_bound_ball",
    "sweep_delta",
    "sweep_ratio",
    "BoundCheck",
]
