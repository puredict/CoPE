"""Checkpoint-isolated candidate verification in a simulator backend."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

import numpy as np

from rekep_repair.execution.controller import control
from rekep_repair.execution.guard_monitor import stage_exit
from rekep_repair.repair.abstract_state import AbstractState
from rekep_repair.repair.rollout_verifier import RolloutReport


@dataclass
class SimulatorRolloutReport(RolloutReport):
    backend: str = ""
    checkpoint_id: str = ""
    checkpoint_hash: str = ""
    restore_hash: str = ""
    restore_exact: bool = False
    actual_controls: List[Dict[str, Any]] = field(default_factory=list)
    actual_checks: List[Dict[str, Any]] = field(default_factory=list)
    failure_class: str = ""

    def summary(self) -> str:
        return json.dumps(
            {
                "backend": self.backend,
                "checkpoint_id": self.checkpoint_id,
                "checkpoint_hash": self.checkpoint_hash,
                "restore_hash": self.restore_hash,
                "restore_exact": self.restore_exact,
                "ok": self.ok,
                "reason": self.reason,
                "failure_class": self.failure_class,
                "duration": self.predicted_duration,
                "collision": self.predicted_collision,
                "guard_failures": self.predicted_guard_failures,
                "handoff_error": self.predicted_handoff_error,
                "attachment": self.predicted_attachment,
                "event_residual": list(self.event_residual),
                "restore_contract_ok": self.restore_ok,
                "controls": self.actual_controls,
                "checks": self.actual_checks,
            },
            sort_keys=True,
            separators=(",", ":"),
        )


class BackendRolloutVerifier:
    """Run every candidate from one real checkpoint, then restore exactly."""

    def __init__(self, *, backend, params, horizon_budget: int):
        self.backend = backend
        self.params = params
        self.horizon_budget = int(horizon_budget)

    def verify(self, cand, ctx0, goal, continuation) -> SimulatorRolloutReport:
        checkpoint = self.backend.checkpoint(label=f"candidate-{cand.template_name}")
        rep = SimulatorRolloutReport(
            backend=self.backend.backend_name,
            checkpoint_id=checkpoint.checkpoint_id,
            checkpoint_hash=checkpoint.state_hash,
        )
        collision_before = self.backend.collision_status()["unsafe_contact_count"]
        total = 0
        min_clearance = float("inf")
        try:
            for stage in cand.stages:
                steps = 0
                guard_hit = False
                while steps <= stage.max_steps and total <= self.horizon_budget:
                    ctx = self.backend.observe()
                    min_clearance = min(min_clearance, float(ctx.clearance))
                    collision = self.backend.collision_status()
                    new_unsafe = (
                        collision["unsafe_contact_count"] > collision_before
                    )
                    attached = self.backend.attachment_status()["attached"]
                    check = {
                        "stage": stage.stage_id,
                        "step_in_stage": steps,
                        "total_step": total,
                        "guard": stage.metadata.get("exit_kind", "nominal"),
                        "new_unsafe_contact": bool(new_unsafe),
                        "attached": bool(attached),
                        "state_hash": self.backend.state_hash(),
                    }
                    rep.actual_checks.append(check)
                    if new_unsafe:
                        rep.ok = False
                        rep.reason = f"collision during {stage.stage_id}"
                        rep.failure_class = "collision"
                        rep.predicted_collision = True
                        break
                    if stage.metadata.get("requires_grasp") and not attached:
                        rep.ok = False
                        rep.reason = f"attachment loss during {stage.stage_id}"
                        rep.failure_class = "attachment_loss"
                        break
                    if steps > 0 and stage_exit(
                        stage,
                        ctx,
                        steps,
                        continuation,
                        self.params,
                        ctx.task_goal,
                    ):
                        guard_hit = True
                        break
                    action = control(
                        stage.metadata.get("behavior", "hold"),
                        ctx,
                        stage,
                        continuation,
                        self.params,
                        ctx.task_goal,
                    )
                    result = self.backend.step(action)
                    rep.actual_controls.append(
                        {
                            "stage": stage.stage_id,
                            "behavior": stage.metadata.get("behavior", "hold"),
                            **result,
                        }
                    )
                    steps += 1
                    total += 1
                if not rep.ok:
                    break
                if not guard_hit:
                    rep.ok = False
                    rep.predicted_guard_failures.append(stage.stage_id)
                    if total > self.horizon_budget:
                        rep.reason = "candidate horizon exceeded"
                        rep.failure_class = "horizon"
                    else:
                        rep.reason = f"guard timeout on {stage.stage_id}"
                        rep.failure_class = "controller_or_guard_timeout"
                    break

            final_ctx = self.backend.observe()
            rep.predicted_duration = total
            rep.predicted_min_clearance = min_clearance
            rep.predicted_attachment = (
                "grasped"
                if self.backend.attachment_status()["attached"]
                else "released"
            )
            rep.predicted_handoff_error = continuation.handoff_error(final_ctx.state)
            rep.restore_ok = continuation.restorable_from(
                final_ctx.state, final_ctx.keypoints
            )
            realized = self._realized_state(final_ctx, cand, rep)
            rep.event_residual = goal.residual(realized)
            if rep.ok and rep.event_residual:
                rep.ok = False
                rep.reason = f"unresolved requirements {list(rep.event_residual)}"
                rep.failure_class = "event_residual"
            if rep.ok and not rep.restore_ok:
                rep.ok = False
                rep.reason = "restore contract not satisfiable at rollout end"
                rep.failure_class = "invalid_handoff"
        except Exception as exc:
            rep.ok = False
            rep.reason = f"backend rollout exception: {type(exc).__name__}: {exc}"
            rep.failure_class = "solver_or_controller_failure"
        finally:
            try:
                restored = self.backend.restore(checkpoint)
                rep.restore_hash = restored["actual_hash"]
                rep.restore_exact = bool(restored["exact"])
            except Exception as exc:
                rep.restore_exact = False
                rep.ok = False
                rep.reason = f"checkpoint restore failure: {type(exc).__name__}: {exc}"
                rep.failure_class = "restore_failure"
        return rep

    @staticmethod
    def _realized_state(ctx, cand, rep: SimulatorRolloutReport) -> AbstractState:
        operators = {
            str(stage.metadata.get("operator", "")) for stage in cand.stages
        }
        target_changed = bool(ctx.target_displacement > 1e-6)
        return AbstractState(
            nominal_suspended=True,
            ee_at_handoff=bool(rep.predicted_handoff_error < 0.08),
            orientation_restored=True,
            safe_clearance=not rep.predicted_collision,
            object_grasped=rep.predicted_attachment == "grasped",
            object_stable=(
                rep.predicted_attachment == "grasped"
                and ("Stabilize" in operators or not ctx.slipped)
            ),
            obstacle_present=False,
            target_changed=target_changed,
            new_target_known=True,
            aligned_to_current_target=(
                not target_changed or "UpdateTargetContract" in operators
            ),
            restore_valid=bool(rep.restore_ok),
        )
