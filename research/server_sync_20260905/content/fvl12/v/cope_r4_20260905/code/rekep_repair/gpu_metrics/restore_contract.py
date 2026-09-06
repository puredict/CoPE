"""P0-3 --- a non-tautological, continuation-specific restore contract.

Replaces the v1 GPU gate

    Contract(predicate=lambda state, keypoints=None: self._native_solver_verified)

whose flag was set ``True`` immediately before the gate was evaluated, so it
could never reject. The contract below is evaluated on **observed simulator
state** and returns both a boolean and numeric margins, so a failure is
diagnosable and the gate can genuinely refuse resumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from .geometry import RigidBodyState, angle_between_deg, body_axis, quat_to_matrix


def quat_angle_deg(qa: Sequence[float], qb: Sequence[float]) -> float:
    """Geodesic angle between two orientations (xyzw), in degrees."""
    a = np.asarray(qa, float); b = np.asarray(qb, float)
    a = a / (np.linalg.norm(a) + 1e-12)
    b = b / (np.linalg.norm(b) + 1e-12)
    d = abs(float(np.dot(a, b)))
    return float(np.degrees(2.0 * np.arccos(np.clip(d, -1.0, 1.0))))


@dataclass(frozen=True)
class RestoreTolerances:
    """Declared tolerances. All have a physical meaning and are logged."""
    ee_position_m: float = 0.05        # handoff positional tolerance
    ee_orientation_deg: float = 25.0   # handoff orientation tolerance
    target_contract_m: float = 0.02    # active target must match the relocated one
    pen_pose_m: float = 0.08           # pen must be compatible with the resumed stage
    require_attachment: bool = True    # continuation captured a grasp -> must persist
    require_collision_free: bool = True


@dataclass
class RestoreEvaluation:
    restore_valid: bool = False
    target_contract_error: Optional[float] = None
    ee_position_error: Optional[float] = None
    ee_orientation_error: Optional[float] = None
    pen_pose_error: Optional[float] = None
    attachment_valid: Optional[bool] = None
    collision_free: Optional[bool] = None
    stage_entry_satisfied: Optional[bool] = None
    failure_reasons: List[str] = field(default_factory=list)
    unavailable: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return dict(self.__dict__)


class ContinuationRestoreContract:
    """Continuation-specific restore contract for pen-in-holder relocation.

    Constructed from the captured continuation; evaluated against live state.
    """

    def __init__(
        self,
        handoff_ee_position: np.ndarray,
        handoff_ee_orientation: np.ndarray,
        required_attachment: str,
        relocated_target_position: np.ndarray,
        reference_pen_position: Optional[np.ndarray] = None,
        tolerances: Optional[RestoreTolerances] = None,
        name: str = "continuation-restore-pen-in-holder",
    ):
        self.name = name
        self.handoff_ee_position = np.asarray(handoff_ee_position, float)[:3]
        self.handoff_ee_orientation = np.asarray(handoff_ee_orientation, float)
        self.required_attachment = required_attachment
        self.relocated_target_position = np.asarray(relocated_target_position, float)[:3]
        self.reference_pen_position = (
            None if reference_pen_position is None
            else np.asarray(reference_pen_position, float)[:3])
        self.tol = tolerances or RestoreTolerances()

    # ------------------------------------------------------------------
    def evaluate(
        self,
        ee_position: np.ndarray,
        ee_orientation: Optional[np.ndarray],
        active_target_position: np.ndarray,
        attachment_state: str,
        pen_state: Optional[RigidBodyState] = None,
        collision_free: Optional[bool] = None,
        stage_entry_satisfied: Optional[bool] = None,
    ) -> RestoreEvaluation:
        ev = RestoreEvaluation()
        tol = self.tol
        reasons: List[str] = []

        # 1. the active task target must be the RELOCATED holder target
        ev.target_contract_error = float(np.linalg.norm(
            np.asarray(active_target_position, float)[:3]
            - self.relocated_target_position))
        if ev.target_contract_error > tol.target_contract_m:
            reasons.append(
                f"target contract not updated: error "
                f"{ev.target_contract_error:.4f} m > {tol.target_contract_m:.4f} m")

        # 2. end effector within the declared handoff positional tolerance
        ev.ee_position_error = float(np.linalg.norm(
            np.asarray(ee_position, float)[:3] - self.handoff_ee_position))
        if ev.ee_position_error > tol.ee_position_m:
            reasons.append(
                f"ee position error {ev.ee_position_error:.4f} m > "
                f"{tol.ee_position_m:.4f} m")

        # 3. end-effector orientation within tolerance
        if ee_orientation is None or len(np.asarray(ee_orientation).ravel()) < 4:
            ev.unavailable.append("ee_orientation")
        else:
            ev.ee_orientation_error = quat_angle_deg(
                np.asarray(ee_orientation, float).ravel()[-4:],
                self.handoff_ee_orientation.ravel()[-4:])
            if ev.ee_orientation_error > tol.ee_orientation_deg:
                reasons.append(
                    f"ee orientation error {ev.ee_orientation_error:.1f} deg > "
                    f"{tol.ee_orientation_deg:.1f} deg")

        # 4. attachment matches the continuation requirement
        ev.attachment_valid = (attachment_state == self.required_attachment)
        if tol.require_attachment and not ev.attachment_valid:
            reasons.append(
                f"attachment '{attachment_state}' != required "
                f"'{self.required_attachment}'")

        # 5. pen pose compatible with the resumed stage
        if pen_state is None or self.reference_pen_position is None:
            ev.unavailable.append("pen_pose")
        else:
            ev.pen_pose_error = float(np.linalg.norm(
                pen_state.position[:3] - self.reference_pen_position))
            if ev.pen_pose_error > tol.pen_pose_m:
                reasons.append(
                    f"pen pose error {ev.pen_pose_error:.4f} m > "
                    f"{tol.pen_pose_m:.4f} m")

        # 6. endpoint collision-free
        ev.collision_free = collision_free
        if tol.require_collision_free:
            if collision_free is None:
                ev.unavailable.append("collision_free")
                reasons.append("collision status UNAVAILABLE")
            elif not collision_free:
                reasons.append("candidate endpoint is in collision")

        # 7. ReKep stage entry constraints
        ev.stage_entry_satisfied = stage_entry_satisfied
        if stage_entry_satisfied is False:
            reasons.append("resumed-stage entry constraints not satisfied")
        elif stage_entry_satisfied is None:
            ev.unavailable.append("stage_entry_constraints")

        ev.failure_reasons = reasons
        ev.restore_valid = (len(reasons) == 0)
        return ev

    # ------------------------------------------------------------------
    def as_task_program_contract(self, state_provider):
        """Wrap as a `program.contracts.Contract` for `TaskProgram`.

        ``state_provider()`` must return the kwargs dict for :meth:`evaluate`.
        The predicate calls it **at gate time**, so the decision is made on live
        observed state -- not on a flag latched beforehand.
        """
        from ..program.contracts import Contract

        def predicate(state, keypoints=None):
            return bool(self.evaluate(**state_provider()).restore_valid)

        def margin(state, keypoints=None):
            ev = self.evaluate(**state_provider())
            if ev.ee_position_error is None:
                return -1.0
            return float(self.tol.ee_position_m - ev.ee_position_error)

        return Contract(name=self.name, predicate=predicate, margin_fn=margin)
