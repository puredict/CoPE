"""Typed repair operators.

Each operator is a *typed* factory that, given the detected event, the captured
continuation, and scene parameters, instantiates a concrete ``StageSpec``.  The
runtime system composes these into a repair program -- it does not select a
pre-written sequence by a hard-coded method branch.

Controllers key on ``behavior`` and the guard monitor keys on ``exit_kind``
(both stored in stage metadata), so operators stay independent of how they are
executed.  Attachment requirements and restore/terminal flags feed the legality
filter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Optional

import numpy as np

from ..events.event import EventType
from ..program.stage import Mode, StageSpec


@dataclass(frozen=True)
class RepairParams:
    """Scene parameters operators need to instantiate stages."""

    theta_pour: float
    theta_hold: float
    d_safe: float
    d_react: float = 0.35
    clear_margin: float = 0.05
    handoff_pose: Optional[np.ndarray] = None      # (px, py) for realignment
    handoff_theta: Optional[float] = None
    target_pos: Optional[np.ndarray] = None        # reacquire position
    task_goal: Optional[np.ndarray] = None         # CURRENT task goal (may relocate)
    tol_theta: float = 0.08
    tol_pos: float = 0.06
    max_steps: int = 30


@dataclass(frozen=True)
class OperatorSpec:
    """Static description of an operator used by legality/feasibility/scoring."""

    name: str
    mode: Mode
    behavior: str                 # controller key
    exit_kind: str                # guard key
    resolves: FrozenSet[EventType] = frozenset()
    provides_restore: bool = False
    terminal: bool = False
    requires_grasp: bool = False     # stage needs the object held to run
    establishes_grasp: bool = False  # stage (re)acquires the object
    max_steps: Optional[int] = None  # per-operator horizon; None -> params.max_steps


class RepairOperator:
    spec: OperatorSpec

    def instantiate(self, idx: int, event, continuation, params: RepairParams) -> StageSpec:
        s = self.spec
        meta: Dict[str, object] = {
            "behavior": s.behavior,
            "exit_kind": s.exit_kind,
            "operator": s.name,
            "target_theta": self._target_theta(params),
            "requires_grasp": s.requires_grasp,
            "establishes_grasp": s.establishes_grasp,
            "provides_restore": s.provides_restore,
            "terminal": s.terminal,
        }
        if params.handoff_pose is not None:
            meta["handoff_pose"] = np.asarray(params.handoff_pose, float)
        if params.target_pos is not None:
            meta["target_pos"] = np.asarray(params.target_pos, float)
        return StageSpec(
            stage_id=f"{s.name.lower()}#{idx}",
            mode=s.mode,
            kind="repair",
            max_steps=s.max_steps if s.max_steps is not None else params.max_steps,
            metadata=meta,
        )

    def _target_theta(self, params: RepairParams) -> float:
        raise NotImplementedError


class Suspend(RepairOperator):
    spec = OperatorSpec("Suspend", Mode.SUSPEND, "hold", "one_step",
                        resolves=frozenset(), max_steps=3)
    def _target_theta(self, p): return p.theta_hold


class Stabilize(RepairOperator):
    spec = OperatorSpec("Stabilize", Mode.STABILIZE, "hold", "theta_hold",
                        resolves=frozenset({EventType.OBJECT_SLIP}), max_steps=20)
    def _target_theta(self, p): return p.theta_hold


class Retreat(RepairOperator):
    spec = OperatorSpec("Retreat", Mode.RETREAT, "retreat", "clear_safe",
                        resolves=frozenset({EventType.OBSTACLE_INTRUSION}), max_steps=40)
    def _target_theta(self, p): return p.theta_hold


class WaitUntilClear(RepairOperator):
    spec = OperatorSpec("WaitUntilClear", Mode.WAIT, "wait", "obstacle_gone",
                        resolves=frozenset({EventType.OBSTACLE_INTRUSION}))
    def _target_theta(self, p): return p.theta_hold


class ReacquireTarget(RepairOperator):
    spec = OperatorSpec("ReacquireTarget", Mode.REGRASP, "to_target", "target_reached",
                        resolves=frozenset({EventType.OBJECT_SLIP, EventType.TARGET_RELOCATION}),
                        establishes_grasp=True, max_steps=40)
    def _target_theta(self, p): return p.theta_hold


class UpdateTargetContract(RepairOperator):
    """Adopt the relocated target as the task's current goal contract.  Purely
    a program-level update (no motion), so it is a one-step stage."""
    spec = OperatorSpec("UpdateTargetContract", Mode.REALIGN, "hold", "one_step",
                        resolves=frozenset({EventType.TARGET_RELOCATION}),
                        requires_grasp=False, max_steps=2)
    def _target_theta(self, p): return p.theta_hold


class Realign(RepairOperator):
    spec = OperatorSpec("Realign", Mode.REALIGN, "to_handoff", "handoff_reached",
                        resolves=frozenset(), requires_grasp=True, max_steps=30)
    def _target_theta(self, p):
        return p.handoff_theta if p.handoff_theta is not None else p.theta_pour


class Resume(RepairOperator):
    """The explicit restore gate: its exit is the continuation resume contract.
    Provides the restore that HasRestore requires."""
    spec = OperatorSpec("Resume", Mode.RESTORE, "to_handoff", "restore_contract",
                        resolves=frozenset(), provides_restore=True, requires_grasp=True, max_steps=8)
    def _target_theta(self, p):
        return p.handoff_theta if p.handoff_theta is not None else p.theta_pour


class SafeStop(RepairOperator):
    spec = OperatorSpec("SafeStop", Mode.SAFE_STOP, "stop", "never",
                        resolves=frozenset({EventType.PERSISTENT_INFEASIBILITY}),
                        terminal=True, requires_grasp=False)
    def _target_theta(self, p): return p.theta_hold


# registry by name
OPERATORS: Dict[str, RepairOperator] = {
    op.spec.name: op
    for op in [Suspend(), Stabilize(), Retreat(), WaitUntilClear(),
               ReacquireTarget(), UpdateTargetContract(), Realign(), Resume(), SafeStop()]
}
