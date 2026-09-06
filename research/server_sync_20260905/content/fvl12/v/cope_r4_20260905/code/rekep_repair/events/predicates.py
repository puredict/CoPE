"""Deterministic keypoint/state predicates used by the event detector.

Per Sec. 5.2 the first version uses simulator ground truth / deterministic
predicates rather than a VLM, so that repair efficacy is isolated from
detection error.  Noise is injected separately (noise_model) for the
robustness study.
"""

from __future__ import annotations

from ..execution.context import ExecutionContext


def obstacle_intrusion(ctx: ExecutionContext, d_safe: float) -> bool:
    return ctx.obstacle_pos is not None and ctx.clearance < d_safe


def object_slipped(ctx: ExecutionContext) -> bool:
    return bool(ctx.slipped)


def target_relocated(ctx: ExecutionContext, threshold: float) -> bool:
    return ctx.target_displacement > threshold


def intrusion_severity(ctx: ExecutionContext, d_safe: float) -> float:
    """Normalized severity in [0, 1]: how far inside the safety margin."""
    if ctx.obstacle_pos is None:
        return 0.0
    return float(max(0.0, min(1.0, (d_safe - ctx.clearance) / max(d_safe, 1e-6))))
