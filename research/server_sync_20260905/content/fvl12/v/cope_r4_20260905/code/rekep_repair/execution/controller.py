"""Behavior-keyed controllers for the 2D domain.

A controller maps (context, stage, continuation, params) -> desired action
(dp_x, dp_y, dtheta).  The environment clips the action to the control limits,
so controllers may output desired deltas directly.  Controllers are shared by
every method; only which stage is active differs.  This is what lets the paper
isolate the effect of program repair from the trajectory controller.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..program.continuation import Continuation
from ..program.stage import StageSpec
from ..repair.operator import RepairParams
from .context import ExecutionContext

K_THETA = 0.6
K_POS = 0.5
K_REP = 1.2


def _repulsion(ctx: ExecutionContext, d_safe: float, margin: float) -> np.ndarray:
    if ctx.obstacle_pos is None or ctx.clearance >= d_safe + margin:
        return np.zeros(2)
    away = ctx.position - ctx.obstacle_pos
    n = np.linalg.norm(away)
    if n < 1e-6:
        away = np.array([1.0, 0.0])
        n = 1.0
    pen = (d_safe + margin) - ctx.clearance
    return K_REP * pen * (away / n)


def _rot(target_theta: float, ctx: ExecutionContext) -> float:
    return K_THETA * (target_theta - ctx.theta)


def control(
    behavior: str,
    ctx: ExecutionContext,
    stage: StageSpec,
    continuation: Optional[Continuation],
    params: RepairParams,
    goal: np.ndarray,
) -> np.ndarray:
    m = stage.metadata
    _tt = m.get("target_theta")
    target_theta = float(_tt) if _tt is not None else params.theta_pour
    d_safe, margin = params.d_safe, params.clear_margin

    if behavior == "progress":
        dp = K_POS * (goal - ctx.position) + _repulsion(ctx, d_safe, margin)
        return np.array([dp[0], dp[1], _rot(params.theta_pour, ctx)])

    if behavior == "progress_noavoid":
        # fixed program: ignores the obstacle entirely (no reaction)
        dp = K_POS * (goal - ctx.position)
        return np.array([dp[0], dp[1], _rot(params.theta_pour, ctx)])

    if behavior == "hold":
        # semantics: hold pose, adjust orientation only.  Does NOT retreat --
        # only Retreat opens clearance (non-overlapping operator semantics).
        return np.array([0.0, 0.0, _rot(target_theta, ctx)])

    if behavior == "retreat":
        # the ONLY operator that actively increases clearance
        dp = _repulsion(ctx, d_safe, margin)
        if np.linalg.norm(dp) < 1e-6 and ctx.obstacle_pos is not None:
            away = ctx.position - ctx.obstacle_pos
            n = np.linalg.norm(away) or 1.0
            dp = 0.5 * away / n
        return np.array([dp[0], dp[1], _rot(params.theta_hold, ctx)])

    if behavior == "wait":
        # maintain a stationary/stabilized state and wait; no repulsion
        return np.array([0.0, 0.0, _rot(target_theta, ctx)])

    if behavior == "to_target":
        tgt = np.asarray(m.get("target_pos", ctx.target_pos), float)
        dp = K_POS * (tgt - ctx.position)
        return np.array([dp[0], dp[1], _rot(params.theta_hold, ctx)])

    if behavior == "to_handoff":
        handoff = np.asarray(m.get("handoff_pose"), float) if m.get("handoff_pose") is not None else goal
        dp = K_POS * (handoff - ctx.position) + _repulsion(ctx, d_safe, margin)
        return np.array([dp[0], dp[1], _rot(params.theta_pour, ctx)])

    if behavior == "stop":
        return np.zeros(3)

    raise ValueError(f"unknown behavior: {behavior}")
