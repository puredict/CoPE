"""Shared helpers for recovery policies."""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..execution.provenance_logger import ActionRecord
from ..program.contracts import ball_contract
from ..program.stage import Mode, StageSpec
from ..repair.operator import RepairParams
from ..synthetic.dynamics import SceneConfig


def build_params(cfg: SceneConfig, handoff_pose: Optional[np.ndarray] = None,
                 target_pos: Optional[np.ndarray] = None,
                 task_goal: Optional[np.ndarray] = None) -> RepairParams:
    return RepairParams(
        theta_pour=cfg.theta_pour,
        theta_hold=cfg.theta_hold,
        d_safe=cfg.d_safe,
        d_react=cfg.d_react,
        clear_margin=0.05,
        handoff_pose=handoff_pose,
        handoff_theta=cfg.theta_pour,
        target_pos=target_pos,
        task_goal=task_goal if task_goal is not None else cfg.p_goal,
        tol_theta=0.10,
        tol_pos=0.08,
        max_steps=cfg.horizon,
    )


def nominal_pour_stage(behavior: str = "progress") -> StageSpec:
    return StageSpec(
        stage_id="pour",
        mode=Mode.POUR,
        kind="nominal",
        metadata={"behavior": behavior, "exit_kind": "nominal",
                  "target_theta": None, "operator": "Pour"},
    )


def resume_contract(handoff_pose: np.ndarray, theta_pour: float, radius: float = 0.12):
    """Pre(s_i^resumed): back near the handoff pose with pouring orientation."""
    target = np.array([handoff_pose[0], handoff_pose[1], theta_pour], float)
    return ball_contract("resume", target, radius, weight=np.array([1.0, 1.0, 0.6]))


def record(t, action, stage: StageSpec, stage_state: str,
           event_id=None, template=None, cont_ts=None) -> ActionRecord:
    return ActionRecord(
        t=t,
        action=np.asarray(action, float),
        stage_id=stage.stage_id,
        stage_mode=stage.mode.value,
        stage_kind=stage.kind,
        stage_state=stage_state,
        event_id=event_id,
        repair_template=template,
        continuation_ts=cont_ts,
    )
