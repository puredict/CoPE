"""Executor -- the single closed-loop harness every method runs through.

The executor is generic: it steps the environment, asks the plugged-in
RecoveryPolicy for an action, logs provenance, and evaluates uniform metrics.
All methods therefore share environment, dynamics, control limits, horizon,
seed, and metric logger; they differ only in the RecoveryPolicy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from ..synthetic.dynamics import Rollout, SceneConfig
from ..synthetic.env import Synthetic2DEnv
from .context import ExecutionContext
from .provenance_logger import ActionRecord, ProvenanceLog


class RecoveryPolicy:
    """Interface for a recovery policy (a 'method')."""

    name: str = "base"

    def reset(self, env: Synthetic2DEnv) -> None:
        raise NotImplementedError

    def act(self, ctx: ExecutionContext) -> tuple:
        """Return (action: np.ndarray(3,), ActionRecord)."""
        raise NotImplementedError

    def finished(self) -> bool:
        return False

    def trace_lines(self) -> List[str]:
        return []


@dataclass
class EpisodeResult:
    method: str
    rollout: Rollout
    provenance: ProvenanceLog
    trace: List[str] = field(default_factory=list)
    failed_safe: bool = False

    def report(self) -> dict:
        r = self.rollout.report()
        r["continuation_linked_provenance"] = round(self.provenance.continuation_linked_coverage(), 4)
        r["event_attribution"] = round(self.provenance.event_attribution_coverage(), 4)
        r["policy_attribution"] = round(self.provenance.policy_attribution_coverage(), 4)
        r["failed_safe"] = self.failed_safe
        return r


class Executor:
    def __init__(self, env: Synthetic2DEnv):
        self.env = env

    def run(self, policy: RecoveryPolicy) -> EpisodeResult:
        cfg = self.env.cfg
        ctx = self.env.reset()
        policy.reset(self.env)
        log = ProvenanceLog()
        states = [self.env.state.copy()]

        for _ in range(cfg.horizon):
            action, rec = policy.act(ctx)
            log.add(rec)
            ctx = self.env.step(action)
            states.append(self.env.state.copy())
            if policy.finished():
                break

        arr = np.array(states)
        final_goal = self.env.goal.copy()
        delivered = bool(
            self.env.grasped
            and np.linalg.norm(self.env.state[:2] - final_goal) <= cfg.eps_goal
        )
        rollout = Rollout(
            positions=arr[:, :2],
            thetas=arr[:, 2],
            cfg=cfg,
            method=policy.name,
            final_goal=final_goal,
            object_delivered=delivered,
            failed_safe=bool(getattr(policy, 'failed_safe', False)),
        )
        return EpisodeResult(
            method=policy.name,
            rollout=rollout,
            provenance=log,
            trace=policy.trace_lines(),
            failed_safe=getattr(policy, "failed_safe", False),
        )
