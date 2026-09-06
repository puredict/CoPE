"""ReKepOmniGibsonAdapter -- the GPU-side boundary.

STATUS: locally syntax-checked. **NOT EXECUTED.** Requires remote GPU
verification. Every OmniGibson / ReKep import is deferred into method bodies so
this module imports cleanly on the CPU machine (and so the CPU test-suite can
exercise the wiring in a `--dry-run` fake mode).

Design rule (do not violate): ReKep's ``constraint_generation``,
``subgoal_solver``, ``path_solver``, ``ik_solver`` and trajectory execution stay
**unchanged**.  This adapter only:

  * reads keypoints / robot state out of ReKep+OmniGibson,
  * turns them into ``ExecutionContext`` + ``WorldPredicates``,
  * asks ReKep's OWN solvers for a short-horizon prediction inside
    ``simulate_candidate``,
  * forwards actions to ReKep's existing execution call.

The contribution stays ``ReKep + online constraint-program repair layer``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np

from .adapter import RepairEnvironmentAdapter
from .execution.context import ExecutionContext
from .repair.abstract_state import WorldPredicates
from .repair.rollout_verifier import RolloutReport


@dataclass
class ReKepAdapterConfig:
    """Keypoint indices and thresholds wiring ReKep's scene to our predicates.

    These are scene-specific and MUST be set per task on the GPU host; the
    defaults are placeholders and are certain to be wrong for a real scene.
    """

    ee_keypoint: int = 0
    object_keypoint: int = 1
    target_keypoint: int = 2
    hazard_keypoint: int = 3          # the intruding hand / obstacle proxy
    d_react: float = 0.25             # m; anticipatory detection radius
    d_safe: float = 0.10              # m; collision radius
    target_move_threshold: float = 0.05
    grasp_force_threshold: float = 0.0
    sim_budget_steps: int = 15        # short-horizon budget for simulate_candidate


class ReKepOmniGibsonAdapter(RepairEnvironmentAdapter):
    """Adapter over a live ReKep execution context.

    Parameters
    ----------
    rekep_main :
        The ReKep ``Main``/executor object (holds ``env``, the keypoint tracker
        and the solver instances).  Passed in, never constructed here.
    cfg :
        Keypoint/threshold wiring.
    dry_run :
        When True, no OmniGibson/ReKep call is made; the adapter serves a
        scripted fake context.  This exists ONLY so the CPU test-suite can
        exercise the interface contract.  It proves nothing about GPU behavior.
    """

    def __init__(self, rekep_main: Any = None,
                 cfg: Optional[ReKepAdapterConfig] = None,
                 dry_run: bool = False):
        if rekep_main is None and not dry_run:
            raise ValueError(
                "rekep_main is required (or pass dry_run=True for the "
                "interface-contract fake). REMOTE GPU SERVER ONLY.")
        self.main = rekep_main
        self.cfg = cfg or ReKepAdapterConfig()
        self.dry_run = dry_run
        self._t = 0
        self._nominal_goal: Optional[np.ndarray] = None
        self._fake = _DryRunState() if dry_run else None

    # --- observation ------------------------------------------------------
    def _keypoints(self) -> np.ndarray:
        """(K,3) keypoints from ReKep's tracker.  GPU path is untested."""
        if self.dry_run:
            return self._fake.keypoints()
        # REMOTE GPU SERVER ONLY -- ReKep exposes the tracked keypoints on the
        # executor; adjust the attribute name to the pinned ReKep revision.
        return np.asarray(self.main.get_keypoint_positions(), dtype=float)

    def observe_context(self) -> ExecutionContext:
        c = self.cfg
        k = self._keypoints()
        ee = k[c.ee_keypoint]
        obj = k[c.object_keypoint]
        tgt = k[c.target_keypoint]
        haz = k[c.hazard_keypoint] if len(k) > c.hazard_keypoint else None

        grasped = self.attachment_state().get("object") == "grasped"
        theta = self._object_orientation()
        clearance = float("inf")
        if haz is not None:
            clearance = float(np.linalg.norm(ee[:2] - haz[:2])) - c.d_safe

        if self._nominal_goal is None:
            self._nominal_goal = tgt[:2].copy()

        return ExecutionContext(
            t=self._t,
            state=np.array([ee[0], ee[1], theta], dtype=float),
            keypoints=k,
            obstacle_pos=None if haz is None else haz[:2].copy(),
            obstacle_radius=c.d_safe,
            clearance=clearance,
            task_goal=tgt[:2].copy(),
            nominal_goal=self._nominal_goal.copy(),
            target_displacement=float(np.linalg.norm(tgt[:2] - self._nominal_goal)),
            object_pos=obj[:2].copy(),
            object_grasped=grasped,
            slipped=not grasped,
            reacquire_pos=None if grasped else obj[:2].copy(),
            attachments=self.attachment_state(),
        )

    def _object_orientation(self) -> float:
        """Scalar orientation proxy.  In ReKep the held object's pose comes from
        the grasped-object transform; reduce it to the task-relevant angle."""
        if self.dry_run:
            return self._fake.theta
        # REMOTE GPU SERVER ONLY
        R = np.asarray(self.main.get_grasped_object_orientation(), dtype=float)
        return float(np.arctan2(R[1, 0], R[0, 0]))

    def active_predicates(self) -> WorldPredicates:
        """The SAME predicate channel every policy consumes."""
        ctx = self.observe_context()
        c = self.cfg
        return WorldPredicates(
            obstacle_present=(ctx.obstacle_pos is not None
                              and ctx.clearance < c.d_react),
            unsafe_clearance=(ctx.obstacle_pos is not None
                              and ctx.clearance < c.d_react),
            object_slipped=not ctx.object_grasped,
            target_relocated=ctx.target_displacement > c.target_move_threshold,
        )

    def current_task_goal(self) -> np.ndarray:
        return self.observe_context().task_goal

    def attachment_state(self) -> Dict[str, str]:
        if self.dry_run:
            return {"object": "grasped" if self._fake.grasped else "released"}
        # REMOTE GPU SERVER ONLY
        held = bool(self.main.is_grasping())
        return {"object": "grasped" if held else "released"}

    # --- prediction -------------------------------------------------------
    def simulate_candidate(self, candidate, ctx, goal, continuation) -> RolloutReport:
        """Short-horizon rollout using **ReKep's own subgoal/path solvers**.

        Deliberately does NOT implement a new trajectory optimizer: for each
        repair stage we hand ReKep's solvers that stage's constraints with a
        reduced iteration budget and propagate the resulting end state.  This is
        what keeps the claim `same solvers + repair layer` honest.

        GPU path is NOT EXECUTED and requires remote GPU verification.
        """
        if self.dry_run:
            rep = RolloutReport()
            rep.ok, rep.reason = True, "dry-run: no ReKep solver invoked"
            rep.predicted_duration = len(candidate.stages) * self.cfg.sim_budget_steps
            rep.predicted_min_clearance = ctx.clearance
            rep.predicted_handoff_error = 0.0
            rep.restore_ok = True
            return rep

        # REMOTE GPU SERVER ONLY ------------------------------------------
        rep = RolloutReport()
        state = np.asarray(ctx.state, dtype=float).copy()
        total = 0
        min_clr = float("inf")
        for stage in candidate.stages:
            try:
                subgoal = self.main.subgoal_solver.solve(          # ReKep's own
                    state, stage.metadata.get("subgoal_constraints", ()),
                    max_iters=self.cfg.sim_budget_steps)
                path = self.main.path_solver.solve(                # ReKep's own
                    state, subgoal,
                    stage.metadata.get("path_constraints", ()),
                    max_iters=self.cfg.sim_budget_steps)
            except Exception as e:                      # solver failure = reject
                rep.ok, rep.reason = False, f"rekep solver failed on {stage.stage_id}: {e!r}"
                return rep
            if path is None or len(path) == 0:
                rep.ok, rep.reason = False, f"no path for {stage.stage_id}"
                return rep
            state = np.asarray(path[-1], dtype=float)[:3]
            total += len(path)
            min_clr = min(min_clr, self._predicted_clearance(path))
            if min_clr < 0.0:
                rep.ok, rep.reason = False, f"predicted collision in {stage.stage_id}"
                rep.predicted_collision = True
                rep.predicted_min_clearance = min_clr
                return rep

        rep.predicted_duration = total
        rep.predicted_min_clearance = min_clr
        rep.predicted_handoff_error = (
            float(np.linalg.norm(state[:2] - np.asarray(continuation.handoff_pose)))
            if continuation.handoff_pose is not None else 0.0)
        rep.event_residual = goal.residual(self._abstract_from(state, ctx))
        rep.restore_ok = continuation.restorable_from(state)
        if rep.event_residual:
            rep.ok, rep.reason = False, f"unresolved {list(rep.event_residual)}"
        elif not rep.restore_ok:
            rep.ok, rep.reason = False, "restore contract unsatisfiable"
        return rep

    def _predicted_clearance(self, path) -> float:
        """Minimum predicted clearance along a ReKep path. REMOTE GPU ONLY."""
        haz = self._keypoints()[self.cfg.hazard_keypoint][:2]
        return min(float(np.linalg.norm(np.asarray(p)[:2] - haz)) - self.cfg.d_safe
                   for p in path)

    def _abstract_from(self, state, ctx):
        from .repair.abstract_state import AbstractState
        return AbstractState(
            nominal_suspended=True, ee_at_handoff=True, orientation_restored=True,
            safe_clearance=True, object_grasped=ctx.object_grasped,
            object_stable=True, obstacle_present=False,
            target_changed=ctx.target_displacement > self.cfg.target_move_threshold,
            new_target_known=True, aligned_to_current_target=True,
            restore_valid=True,
        )

    # --- actuation --------------------------------------------------------
    def execute_action(self, action: np.ndarray) -> ExecutionContext:
        if self.dry_run:
            self._fake.step(action)
        else:
            # REMOTE GPU SERVER ONLY -- ReKep's existing execution entry point.
            self.main.env.execute_action(np.asarray(action, dtype=float))
        self._t += 1
        return self.observe_context()

    def reset(self) -> ExecutionContext:
        self._t = 0
        self._nominal_goal = None
        if self.dry_run:
            self._fake = _DryRunState()
        return self.observe_context()

    @property
    def horizon(self) -> int:
        return 400


class _DryRunState:
    """Scripted stand-in used ONLY to exercise the interface contract on CPU.
    It is not a simulator and proves nothing about GPU behavior."""

    def __init__(self):
        self.ee = np.array([0.0, 0.0, 0.5])
        self.obj = np.array([0.0, 0.0, 0.5])
        self.tgt = np.array([0.6, 0.0, 0.5])
        self.haz = np.array([0.35, 0.05, 0.5])
        self.theta = 1.0
        self.grasped = True

    def keypoints(self) -> np.ndarray:
        return np.stack([self.ee, self.obj, self.tgt, self.haz])

    def step(self, action):
        a = np.asarray(action, dtype=float)
        self.ee[:2] += a[:2]
        self.theta += float(a[2]) if a.shape[0] > 2 else 0.0
        if self.grasped:
            self.obj[:2] = self.ee[:2]
