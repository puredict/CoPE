"""Small rigid-body geometry helpers shared by the GPU metrics.

Kept dependency-free (numpy only) so the whole `gpu_metrics` package is
CPU-testable with synthetic inputs and never imports a simulator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np


def quat_to_matrix(q: Sequence[float]) -> np.ndarray:
    """Rotation matrix from a quaternion in **xyzw** order (OmniGibson's order)."""
    x, y, z, w = (float(v) for v in q)
    n = np.sqrt(x * x + y * y + z * z + w * w)
    if n < 1e-12:
        return np.eye(3)
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def body_axis(q: Sequence[float], axis: int = 2) -> np.ndarray:
    """World-frame unit vector of a body axis (0=x, 1=y, 2=z)."""
    v = quat_to_matrix(q)[:, axis]
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else np.array([0.0, 0.0, 1.0])


def angle_between_deg(a: np.ndarray, b: np.ndarray, undirected: bool = True) -> float:
    """Angle between two vectors in degrees.  ``undirected`` folds 180 deg onto 0,
    which is what we want for a pen axis (either end may point 'up')."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-12 or nb < 1e-12:
        return float("nan")
    c = float(np.dot(a, b) / (na * nb))
    if undirected:
        c = abs(c)
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


def radial_distance_to_axis(point: np.ndarray, axis_origin: np.ndarray,
                            axis_dir: np.ndarray) -> float:
    """Perpendicular distance from ``point`` to the infinite line through
    ``axis_origin`` along ``axis_dir``."""
    p = np.asarray(point, float) - np.asarray(axis_origin, float)
    d = np.asarray(axis_dir, float)
    d = d / (np.linalg.norm(d) + 1e-12)
    return float(np.linalg.norm(p - np.dot(p, d) * d))


def axial_coordinate(point: np.ndarray, axis_origin: np.ndarray,
                     axis_dir: np.ndarray) -> float:
    """Signed coordinate of ``point`` along the holder axis, measured from
    ``axis_origin``.  Positive = toward ``axis_dir`` (i.e. up, out of the bore)."""
    p = np.asarray(point, float) - np.asarray(axis_origin, float)
    d = np.asarray(axis_dir, float)
    d = d / (np.linalg.norm(d) + 1e-12)
    return float(np.dot(p, d))


@dataclass(frozen=True)
class RigidBodyState:
    """One rigid body at one instant.  Velocities optional (None -> unavailable)."""

    position: np.ndarray
    orientation: np.ndarray                      # xyzw
    linear_velocity: Optional[np.ndarray] = None
    angular_velocity: Optional[np.ndarray] = None

    @staticmethod
    def of(position, orientation, lin=None, ang=None) -> "RigidBodyState":
        return RigidBodyState(
            np.asarray(position, float), np.asarray(orientation, float),
            None if lin is None else np.asarray(lin, float),
            None if ang is None else np.asarray(ang, float))


@dataclass(frozen=True)
class PenGeometry:
    """Pen as a capsule along a body axis."""
    length: float
    radius: float
    long_axis: int = 2                            # body axis of the pen's length


@dataclass(frozen=True)
class HolderGeometry:
    """Pencil holder as an open cylinder (bore) along a body axis.

    ``rim_height`` and ``bore_depth`` are measured from the body origin along
    ``+axis``: the rim plane sits at ``+rim_height``; the bore floor at
    ``rim_height - bore_depth``.
    """
    inner_radius: float
    rim_height: float
    bore_depth: float
    axis: int = 2

    @property
    def floor_height(self) -> float:
        return self.rim_height - self.bore_depth
