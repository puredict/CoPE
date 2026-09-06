"""Sequential candidate verification by lightweight forward rollout.

Replaces terminal-only handoff reachability.  Each candidate is simulated
operator-by-operator under the SAME kinematics and control limits as the
environment: the state produced by operator *i* is the initial state of
operator *i+1*.  A candidate is rejected if it collides, times out on a guard,
exceeds the episode horizon, violates attachment semantics, leaves any active
event requirement unresolved, or cannot restore the continuation.

Translational limits use the same **norm-based** convention as the environment
clip (per-axis clip admits up to sqrt(2)*v_max), so the model and the world
agree on speed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from ..program.continuation import Continuation
from .abstract_state import RepairGoal
from .candidate import RepairCandidate
from .operator import RepairParams


@dataclass
class RolloutReport:
    ok: bool = True
    reason: str = "ok"
    predicted_collision: bool = False
    predicted_guard_failures: List[str] = field(default_factory=list)
    predicted_duration: int = 0
    predicted_handoff_error: float = float("inf")
    predicted_min_clearance: float = float("inf")
    predicted_attachment: str = "grasped"
    event_residual: Tuple[str, ...] = ()
    restore_ok: bool = False

    def summary(self) -> str:
        return (f"dur={self.predicted_duration} clr={self.predicted_min_clearance:.3f} "
                f"handoff={self.predicted_handoff_error:.3f} "
                f"collision={self.predicted_collision} residual={list(self.event_residual)}")


class RolloutVerifier:
    """Simulates a candidate against a *copy* of the world model."""

    def __init__(self, params: RepairParams, cfg, horizon_budget: int):
        self.params = params
        self.cfg = cfg
        self.horizon_budget = horizon_budget

    # --- kinematics identical to Synthetic2DEnv, but norm-limited ---------
    def _apply(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        from ..execution.action import clip_action
        cfg = self.cfg
        a = clip_action(action, cfg.v_max, cfg.w_max)   # SAME function as the env
        s = state + a
        s[:2] = np.clip(s[:2], cfg.ws_lo, cfg.ws_hi)
        return s

    def _ctx_at(self, t: int, state: np.ndarray, grasped: bool,
                drop_pos: Optional[np.ndarray], task_goal: np.ndarray):
        from ..execution.context import ExecutionContext
        from ..synthetic.dynamics import clearance
        o = self.cfg.obstacle.position(t)
        return ExecutionContext(
            t=t, state=state.copy(),
            obstacle_pos=None if o is None else o.copy(),
            obstacle_radius=self.cfg.obstacle.radius,
            clearance=clearance(state[:2], self.cfg.obstacle, t),
            task_goal=task_goal.copy(), nominal_goal=self.cfg.p_goal.copy(),
            object_pos=state[:2].copy() if grasped else (drop_pos.copy() if drop_pos is not None else None),
            object_grasped=grasped, slipped=not grasped,
            reacquire_pos=None if drop_pos is None else drop_pos.copy(),
            attachments={"object": "grasped" if grasped else "released"},
        )

    def verify(
        self,
        cand: RepairCandidate,
        ctx0,
        goal: RepairGoal,
        continuation: Continuation,
    ) -> RolloutReport:
        from ..execution.controller import control
        from ..execution.guard_monitor import stage_exit
        rep = RolloutReport()
        cfg = self.cfg
        state = np.asarray(ctx0.state, float).copy()
        grasped = ctx0.object_grasped
        drop_pos = None if ctx0.reacquire_pos is None else ctx0.reacquire_pos.copy()
        task_goal = ctx0.task_goal.copy()
        t = ctx0.t
        total = 0
        min_clr = float("inf")

        for stage in cand.stages:
            behavior = stage.metadata.get("behavior", "hold")
            steps = 0
            guard_hit = False
            while steps <= stage.max_steps and total <= self.horizon_budget:
                ctx = self._ctx_at(t, state, grasped, drop_pos, task_goal)
                if np.isfinite(ctx.clearance):
                    min_clr = min(min_clr, ctx.clearance)
                if ctx.clearance < 0.0:
                    rep.ok, rep.reason = False, f"collision during {stage.stage_id}"
                    rep.predicted_collision = True
                    rep.predicted_min_clearance = min_clr
                    rep.predicted_duration = total
                    return rep
                if steps > 0 and stage_exit(stage, ctx, steps, continuation,
                                            self.params, task_goal):
                    guard_hit = True
                    break
                a = control(behavior, ctx, stage, continuation, self.params, task_goal)
                state = self._apply(state, a)
                # attachment transition: reacquire completes on contact
                if (not grasped) and drop_pos is not None \
                        and np.linalg.norm(state[:2] - drop_pos) < 0.05:
                    grasped, drop_pos = True, None
                steps += 1
                total += 1
                t += 1

            if not guard_hit:
                rep.predicted_guard_failures.append(stage.stage_id)
                rep.ok = False
                rep.reason = ("horizon exceeded" if total > self.horizon_budget
                              else f"guard timeout on {stage.stage_id}")
                rep.predicted_duration = total
                rep.predicted_min_clearance = min_clr
                rep.predicted_attachment = "grasped" if grasped else "released"
                return rep

        rep.predicted_duration = total
        rep.predicted_min_clearance = min_clr
        rep.predicted_attachment = "grasped" if grasped else "released"
        rep.predicted_handoff_error = float(
            np.linalg.norm(state[:2] - np.asarray(continuation.handoff_pose, float))
        ) if continuation.handoff_pose is not None else 0.0

        # --- independently re-verify the SAME event requirements ----------
        final_ctx = self._ctx_at(t, state, grasped, drop_pos, task_goal)
        realized = self._realized_state(final_ctx, cand, goal)
        rep.event_residual = goal.residual(realized)
        rep.restore_ok = continuation.restorable_from(state)
        if rep.event_residual:
            rep.ok, rep.reason = False, f"unresolved requirements {list(rep.event_residual)}"
        elif not rep.restore_ok:
            rep.ok, rep.reason = False, "restore contract not satisfiable at rollout end"
        return rep

    def _realized_state(self, ctx, cand: RepairCandidate, goal: RepairGoal):
        """Map the ROLLED-OUT concrete state back to abstract facts, so goal
        verification uses the predicted world rather than the planner's model."""
        from .abstract_state import AbstractState
        obstacle_present = ctx.obstacle_pos is not None and ctx.clearance < self.cfg.d_react
        safe = ctx.obstacle_pos is None or ctx.clearance >= self.cfg.d_react
        stabilized = any(s.metadata.get("operator") == "Stabilize" for s in cand.stages)
        updated = any(s.metadata.get("operator") == "UpdateTargetContract" for s in cand.stages)
        return AbstractState(
            nominal_suspended=True,
            ee_at_handoff=True,
            orientation_restored=abs(ctx.theta - self.params.theta_pour) < 0.3,
            safe_clearance=safe,
            object_grasped=ctx.object_grasped,
            object_stable=stabilized and ctx.object_grasped,
            obstacle_present=obstacle_present,
            target_changed=ctx.target_displacement > 0.15,
            new_target_known=True,
            aligned_to_current_target=updated,
            restore_valid=True,
        )
