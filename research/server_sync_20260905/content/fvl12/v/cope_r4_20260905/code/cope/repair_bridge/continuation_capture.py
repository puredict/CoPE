"""Continuation capture --- kappa_t = Capture(TaskProgram, active_stage, x_t).

Called BEFORE any physical adaptation, and before the constraint state is
mutated, so the snapshot records what the robot was doing when it was
interrupted rather than what it was asked to do afterwards.

The `Continuation` type, the resume contract and the handoff error are the
frozen engine's own (`rekep_repair.program.continuation`). Nothing is
re-implemented here; this module only fills the snapshot from the benchmark's
execution context.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

from rekep_repair.policies.common import resume_contract
from rekep_repair.program.continuation import Continuation
from rekep_repair.program.task_program import TaskProgram


def capture_continuation(program: TaskProgram, ctx: Any, event_id: str,
                         theta_pour: float,
                         p_init: Optional[np.ndarray] = None) -> Continuation:
    """Snapshot the interrupted stage.

    `handoff_pose` is the current end-effector position: the pose the repair
    must bring the robot back to before the interrupted stage may resume. That
    is what makes the restore contract non-tautological --- it is fixed at
    capture time, from the pre-adaptation state, and the repair cannot move the
    goalposts afterwards.
    """
    handoff = np.asarray(ctx.position, float).copy()
    origin = np.zeros(2) if p_init is None else np.asarray(p_init, float)
    return Continuation(
        interrupted_stage_id=program.active_id(),
        stage_mode=program.active_stage().mode,
        state=np.asarray(ctx.state, float).copy(),
        ee_pose=np.asarray(ctx.state, float).copy(),
        attachment_state=dict(ctx.attachments),
        nominal_target=(None if ctx.task_goal is None
                        else np.asarray(ctx.task_goal, float).copy()),
        resume_contract=resume_contract(handoff, theta_pour),
        handoff_pose=handoff,
        progress_marker=float(np.linalg.norm(np.asarray(ctx.position, float)
                                             - origin)),
        timestamp=int(ctx.t),
        event_id=event_id,
    )
