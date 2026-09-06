"""GPU-side metrics, verification and contracts (P0-1 .. P0-4).

Pure-numpy and simulator-agnostic: every module here is importable and testable
on a CPU-only machine. The simulator appears only behind the
``ShadowRolloutHost`` protocol.
"""

from .geometry import (
    HolderGeometry, PenGeometry, RigidBodyState,
    angle_between_deg, axial_coordinate, body_axis,
    quat_to_matrix, radial_distance_to_axis,
)
from .pen_in_holder import (
    PenInHolderEvaluator, PenInHolderResult, PenInHolderThresholds,
    evaluate_from_arrays, UNAVAILABLE,
)
from .restore_contract import (
    ContinuationRestoreContract, RestoreEvaluation, RestoreTolerances,
    quat_angle_deg,
)
from .gpu_rollout import (
    CandidateRolloutResult, GPUCandidateVerifier, RolloutLimits,
    ShadowRolloutHost, StateIsolationError, select_best,
)
from .structured_log import EVENTS, StructuredLogger
from .pilot_spec import (
    METHODS, SEVERITIES_M, DisturbanceSpec, PilotSpec,
    assert_paired, disturbance_for, pilot_grid,
)

__all__ = [
    "HolderGeometry", "PenGeometry", "RigidBodyState", "angle_between_deg",
    "axial_coordinate", "body_axis", "quat_to_matrix", "radial_distance_to_axis",
    "PenInHolderEvaluator", "PenInHolderResult", "PenInHolderThresholds",
    "evaluate_from_arrays", "UNAVAILABLE",
    "ContinuationRestoreContract", "RestoreEvaluation", "RestoreTolerances",
    "quat_angle_deg",
    "CandidateRolloutResult", "GPUCandidateVerifier", "RolloutLimits",
    "ShadowRolloutHost", "StateIsolationError", "select_best",
    "EVENTS", "StructuredLogger",
    "METHODS", "SEVERITIES_M", "DisturbanceSpec", "PilotSpec",
    "assert_paired", "disturbance_for", "pilot_grid",
]
