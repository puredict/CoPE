"""Simulator adapters used by the CoPE/FSR-PC experiment harness.

Heavy simulator dependencies are imported lazily. Importing :mod:`cope` on a
CPU-only machine therefore keeps the original Synthetic2D tests runnable.
"""

from .base import (
    BackendCheckpoint,
    BackendUnavailable,
    SimulatorRepairBackend,
)


def make_backend(name: str):
    """Construct a backend by explicit name; unknown names fail fast."""

    if name == "synthetic2d":
        from .synthetic2d import Synthetic2DBackend

        return Synthetic2DBackend()
    if name == "libero_mujoco":
        from .libero_mujoco import LiberoMujocoBackend

        return LiberoMujocoBackend()
    raise BackendUnavailable(
        f"unknown simulator backend {name!r}; available="
        "['synthetic2d', 'libero_mujoco']"
    )


__all__ = [
    "BackendCheckpoint",
    "BackendUnavailable",
    "SimulatorRepairBackend",
    "make_backend",
]
