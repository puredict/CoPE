"""P0-1 --- pen-in-holder task-success evaluator.

Evaluates task success from **simulator geometry**, never from program
completion, never from a hand-assigned boolean.

Design constraints honoured here:

* Every quantity is *measured* from poses + declared body geometry. Anything that
  cannot be measured from the supplied state is returned as ``None`` and listed
  in ``unavailable`` -- it is **never guessed**.
* ``gripper_released`` is **not** a success condition by default. The official
  ReKep pen task's own successful runs are the reference, and if ReKep completes
  while still grasping then requiring release would be an artificial criterion.
  It is recorded as an observation (``attachment_state``) and can be switched on
  explicitly via ``PenInHolderThresholds.require_release``.
* Thresholds carry physical meaning (holder bore radius, pen radius, insertion
  depth as a fraction of bore depth) and are documented in
  ``docs/GPU_SUCCESS_METRIC.md``.

The module imports nothing simulator-specific, so it is fully CPU-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from .geometry import (
    HolderGeometry,
    PenGeometry,
    RigidBodyState,
    angle_between_deg,
    axial_coordinate,
    body_axis,
    radial_distance_to_axis,
)

UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class PenInHolderThresholds:
    """Success thresholds. Each carries a physical justification.

    Calibration procedure (see docs/GPU_SUCCESS_METRIC.md):
      positives  = the official/wrapped nominal runs that visibly insert the pen
      negatives  = repaired seeds 0, 3, 5, 7 (pen gripped away from holder, or
                   lying on the table)
      unlabeled  = repaired seeds 1, 2, 4, 6  -- deliberately NOT used to set a
                   threshold; they are the cases the metric must adjudicate.
    """

    # Radial clearance the pen axis may have from the holder axis. Physically
    # the pen must fit inside the bore: bore_radius - pen_radius. A fraction < 1
    # keeps a margin so a pen resting on the rim does not count.
    xy_margin_fraction: float = 0.85
    # Minimum insertion below the rim, as a fraction of bore depth. 0.25 means
    # the tip must be at least a quarter of the way down the bore -- enough to
    # exclude a pen merely leaning on the rim.
    min_depth_fraction: float = 0.25
    # Maximum tilt of the pen axis relative to the holder axis. A pen inside a
    # narrow bore is mechanically constrained to near-alignment; 30 deg is
    # permissive but excludes a pen lying across the rim.
    max_tilt_deg: float = 30.0
    # Stability: max speed over the final K steps.
    stable_steps: int = 10
    max_linear_speed: float = 0.02      # m/step-equivalent
    max_angular_speed: float = 0.35     # rad/step-equivalent
    # Off by default -- see module docstring.
    require_release: bool = False

    def eps_xy(self, holder: HolderGeometry, pen: PenGeometry) -> float:
        return max(0.0, (holder.inner_radius - pen.radius)) * self.xy_margin_fraction

    def eps_depth(self, holder: HolderGeometry) -> float:
        return holder.bore_depth * self.min_depth_fraction


@dataclass
class PenInHolderResult:
    """Full measurement record for one terminal evaluation."""

    # --- verdict
    task_success: Optional[bool] = None
    inside_holder: Optional[bool] = None
    success_failure_reasons: List[str] = field(default_factory=list)
    unavailable: List[str] = field(default_factory=list)

    # --- measurements (None => not measurable from the supplied state)
    xy_error: Optional[float] = None
    insertion_depth: Optional[float] = None
    tilt_error_deg: Optional[float] = None
    stable_steps: Optional[int] = None
    attachment_state: Optional[str] = None

    pen_position: Optional[List[float]] = None
    pen_orientation: Optional[List[float]] = None
    pen_tip_position: Optional[List[float]] = None
    pen_butt_position: Optional[List[float]] = None
    pen_axis: Optional[List[float]] = None
    holder_position: Optional[List[float]] = None
    holder_orientation: Optional[List[float]] = None
    holder_axis: Optional[List[float]] = None
    holder_rim_world_height: Optional[float] = None
    max_linear_speed: Optional[float] = None
    max_angular_speed: Optional[float] = None

    # --- thresholds actually applied (for provenance)
    eps_xy: Optional[float] = None
    eps_depth: Optional[float] = None
    eps_tilt_deg: Optional[float] = None

    def to_dict(self) -> Dict:
        def conv(v):
            if isinstance(v, np.ndarray):
                return [float(x) for x in v]
            if isinstance(v, (np.floating, np.integer)):
                return v.item()
            return v
        return {k: conv(v) for k, v in self.__dict__.items()}


class PenInHolderEvaluator:
    """Geometric success evaluator for the ReKep pen-in-holder task."""

    def __init__(self, pen: PenGeometry, holder: HolderGeometry,
                 thresholds: Optional[PenInHolderThresholds] = None):
        self.pen = pen
        self.holder = holder
        self.t = thresholds or PenInHolderThresholds()

    # ------------------------------------------------------------------
    def evaluate(
        self,
        pen_state: RigidBodyState,
        holder_state: RigidBodyState,
        attachment_state: Optional[str] = None,
        history: Optional[Sequence[RigidBodyState]] = None,
    ) -> PenInHolderResult:
        """Evaluate one terminal state.

        ``history`` -- the last K pen states, used for the stability test. If it
        is None or shorter than ``stable_steps``, stability is reported
        UNAVAILABLE and success is withheld rather than assumed.
        """
        r = PenInHolderResult()
        r.attachment_state = attachment_state
        r.eps_xy = self.t.eps_xy(self.holder, self.pen)
        r.eps_depth = self.t.eps_depth(self.holder)
        r.eps_tilt_deg = self.t.max_tilt_deg

        # --- axes and tips ------------------------------------------------
        p_axis = body_axis(pen_state.orientation, self.pen.long_axis)
        h_axis = body_axis(holder_state.orientation, self.holder.axis)
        half = 0.5 * self.pen.length
        tip_a = pen_state.position + half * p_axis
        tip_b = pen_state.position - half * p_axis
        # the "tip" is whichever end is deeper along -holder_axis
        ca = axial_coordinate(tip_a, holder_state.position, h_axis)
        cb = axial_coordinate(tip_b, holder_state.position, h_axis)
        tip, butt = (tip_a, tip_b) if ca <= cb else (tip_b, tip_a)

        r.pen_position = list(map(float, pen_state.position))
        r.pen_orientation = list(map(float, pen_state.orientation))
        r.pen_axis = list(map(float, p_axis))
        r.pen_tip_position = list(map(float, tip))
        r.pen_butt_position = list(map(float, butt))
        r.holder_position = list(map(float, holder_state.position))
        r.holder_orientation = list(map(float, holder_state.orientation))
        r.holder_axis = list(map(float, h_axis))
        r.holder_rim_world_height = float(
            axial_coordinate(holder_state.position, holder_state.position, h_axis)
            + self.holder.rim_height)

        # --- core measurements --------------------------------------------
        r.xy_error = radial_distance_to_axis(tip, holder_state.position, h_axis)
        tip_axial = axial_coordinate(tip, holder_state.position, h_axis)
        r.insertion_depth = float(self.holder.rim_height - tip_axial)
        r.tilt_error_deg = angle_between_deg(p_axis, h_axis, undirected=True)

        # --- stability -----------------------------------------------------
        if history is not None and len(history) >= self.t.stable_steps:
            win = list(history)[-self.t.stable_steps:]
            lins = [s.linear_velocity for s in win if s.linear_velocity is not None]
            angs = [s.angular_velocity for s in win if s.angular_velocity is not None]
            if lins and angs:
                r.max_linear_speed = float(max(np.linalg.norm(v) for v in lins))
                r.max_angular_speed = float(max(np.linalg.norm(v) for v in angs))
                r.stable_steps = int(self.t.stable_steps)
            else:
                # fall back to positional drift across the window
                pos = np.stack([s.position for s in win])
                r.max_linear_speed = float(np.abs(np.diff(pos, axis=0)).max())
                r.max_angular_speed = None
                r.stable_steps = int(self.t.stable_steps)
                r.unavailable.append("angular_velocity")
        else:
            r.unavailable.append("stability_history")

        # --- containment ---------------------------------------------------
        radially_in = r.xy_error <= (self.holder.inner_radius - self.pen.radius)
        below_rim = tip_axial <= self.holder.rim_height
        above_floor = tip_axial >= self.holder.floor_height - 1e-6
        r.inside_holder = bool(radially_in and below_rim and above_floor)

        # --- verdict ---------------------------------------------------------
        reasons: List[str] = []
        if not r.inside_holder:
            if not radially_in:
                reasons.append(
                    f"tip outside bore radius: xy_error={r.xy_error:.4f} m > "
                    f"{self.holder.inner_radius - self.pen.radius:.4f} m")
            if not below_rim:
                reasons.append(
                    f"tip above rim: axial={tip_axial:.4f} m > "
                    f"rim={self.holder.rim_height:.4f} m")
            if not above_floor:
                reasons.append("tip below bore floor (penetration)")
        if r.xy_error > r.eps_xy:
            reasons.append(f"xy_error {r.xy_error:.4f} > eps_xy {r.eps_xy:.4f}")
        if r.insertion_depth < r.eps_depth:
            reasons.append(
                f"insertion_depth {r.insertion_depth:.4f} < eps_depth {r.eps_depth:.4f}")
        if r.tilt_error_deg > r.eps_tilt_deg:
            reasons.append(
                f"tilt {r.tilt_error_deg:.1f} deg > {r.eps_tilt_deg:.1f} deg")
        if r.stable_steps is None:
            reasons.append("stability UNAVAILABLE (insufficient history)")
        else:
            if r.max_linear_speed is not None and \
                    r.max_linear_speed > self.t.max_linear_speed:
                reasons.append(
                    f"unstable: linear {r.max_linear_speed:.4f} > "
                    f"{self.t.max_linear_speed:.4f}")
            if r.max_angular_speed is not None and \
                    r.max_angular_speed > self.t.max_angular_speed:
                reasons.append(
                    f"unstable: angular {r.max_angular_speed:.4f} > "
                    f"{self.t.max_angular_speed:.4f}")
        if self.t.require_release and attachment_state == "grasped":
            reasons.append("still grasped and require_release=True")

        r.success_failure_reasons = reasons
        # Withhold success if anything essential was unavailable.
        blocking_unavailable = [u for u in r.unavailable if u == "stability_history"]
        if blocking_unavailable:
            r.task_success = None
            r.success_failure_reasons.append(
                "task_success withheld: " + ", ".join(blocking_unavailable))
        else:
            r.task_success = len(reasons) == 0
        return r


def evaluate_from_arrays(pen_pos, pen_quat, holder_pos, holder_quat,
                         pen: PenGeometry, holder: HolderGeometry,
                         attachment_state=None, history=None,
                         thresholds: Optional[PenInHolderThresholds] = None
                         ) -> PenInHolderResult:
    """Convenience wrapper for callers holding raw arrays."""
    return PenInHolderEvaluator(pen, holder, thresholds).evaluate(
        RigidBodyState.of(pen_pos, pen_quat),
        RigidBodyState.of(holder_pos, holder_quat),
        attachment_state=attachment_state, history=history)
