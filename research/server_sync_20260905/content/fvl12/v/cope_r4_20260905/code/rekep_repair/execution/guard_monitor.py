"""Stage exit guards, keyed by ``exit_kind`` in stage metadata.

Separated from StageSpec because guards read the full ExecutionContext
(obstacle, clearance, grasp), not only (x, k).  The executor consults these to
decide when to advance, including the restore-contract gate.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..program.continuation import Continuation
from ..program.stage import StageSpec
from ..repair.operator import RepairParams
from .context import ExecutionContext


def stage_exit(
    stage: StageSpec,
    ctx: ExecutionContext,
    steps_in_stage: int,
    continuation: Optional[Continuation],
    params: RepairParams,
    goal: np.ndarray,
) -> bool:
    kind = stage.metadata.get("exit_kind", "nominal")
    d_safe, margin = params.d_safe, params.clear_margin

    if kind == "one_step":
        return steps_in_stage >= 1

    if kind == "theta_hold":
        return abs(ctx.theta - params.theta_hold) < params.tol_theta

    if kind == "clear_safe":
        # must leave the reaction zone, not merely the collision zone
        return ctx.obstacle_pos is None or ctx.clearance >= params.d_react + margin

    if kind == "obstacle_gone":
        # wait until the obstacle has actually withdrawn (not merely retreated from)
        return ctx.obstacle_pos is None

    if kind == "target_reached":
        tgt = np.asarray(stage.metadata.get("target_pos", ctx.target_pos), float)
        return bool(np.linalg.norm(ctx.position - tgt) < params.tol_pos) and (not ctx.slipped)

    if kind == "handoff_reached":
        handoff = stage.metadata.get("handoff_pose")
        pos_ok = True
        if handoff is not None:
            pos_ok = bool(np.linalg.norm(ctx.position - np.asarray(handoff, float)) < params.tol_pos)
        theta_ok = abs(ctx.theta - params.theta_pour) < params.tol_theta
        return pos_ok and theta_ok

    if kind == "restore_contract":
        if continuation is None:
            return True
        return continuation.restorable_from(ctx.state, ctx.keypoints)

    if kind == "never":
        return False

    # nominal stage: reached goal + pour orientation
    goal_ok = bool(np.linalg.norm(ctx.position - goal) < params.tol_pos)
    theta_ok = abs(ctx.theta - params.theta_pour) < params.tol_theta
    return goal_ok and theta_ok
