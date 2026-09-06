"""Ours -- online continuation-carrying program repair.

Full runtime pipeline (Algorithm 1):

    detect event -> capture continuation -> generate candidates
      -> reject illegal -> reject infeasible -> score/select
      -> interrupt active stage -> splice [repair..., resumed] before successor
      -> execute repair stages -> validate restore contract -> resume

The final repair sequence is selected by the RepairManager, never by a
hard-coded method branch.  If nothing survives, the policy engages a bounded
safe fallback.
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np

from ..events.detector import EventDetector
from ..execution.context import ExecutionContext
from ..execution.controller import control
from ..execution.executor import RecoveryPolicy
from ..execution.fallback import SafeFallback
from ..execution.guard_monitor import stage_exit
from ..program.continuation import Continuation
from ..program.stage import StageState
from ..program.task_program import RestorationBlocked, TaskProgram
from ..repair.abstract_state import goal_from_predicates, state_from_predicates
from ..repair.feasibility_filter import ControlLimits
from ..repair.repair_manager import RepairManager
from ..repair.synthesis_generator import SynthesisGenerator
from .common import build_params, nominal_pour_stage, record, resume_contract


class OnlineRepairPolicy(RecoveryPolicy):
    name = "online_repair"

    def reset(self, env) -> None:
        self.env = env
        self.cfg = env.cfg
        self.base_params = build_params(self.cfg)
        self.detector = EventDetector(d_safe=self.cfg.d_react)
        self.limits = ControlLimits(
            v_max=self.cfg.v_max, w_max=self.cfg.w_max,
            ws_lo=self.cfg.ws_lo, ws_hi=self.cfg.ws_hi,
        )
        self.program = TaskProgram([nominal_pour_stage(behavior="progress")])
        self.continuation: Optional[Continuation] = None
        self.params = self.base_params
        self.template: Optional[str] = None
        self.cur_steps = 0
        self.fallback = SafeFallback(max_fallback_steps=5)
        self.failed_safe = False
        self._trace: List[str] = []
        self._last_plan = None
        self._last_init = None
        self.deferred_events = []
        self._handled = set()
        self._pending_key = None
        self._done = False

    # --- main step --------------------------------------------------------
    def act(self, ctx: ExecutionContext):
        if self.fallback.active:
            a = self.fallback.action()
            if self.fallback.exhausted():
                self._done = True
            stage = self.program.active_stage()
            return a, record(ctx.t, a, stage, "FAILED")

        # advance any stages whose guard is already satisfied by the current ctx
        self._maybe_advance(ctx)
        if self._done:
            stage = self.program.active_stage()
            in_rep = stage.kind in ("repair", "resumed")
            return np.zeros(3), record(
                ctx.t, np.zeros(3), stage, "COMPLETED",
                event_id=self.continuation.event_id if in_rep and self.continuation else None,
                template=self.template if in_rep else None,
                cont_ts=self.continuation.timestamp if in_rep and self.continuation else None,
            )

        # --- event-during-execution policy (explicit, never silent) ---------
        # ACTIVE  : nominal work            -> plan a repair.
        # RESUMED : the resumed instance is nominal work on the interrupted
        #           stage, so a NEW disturbance there also warrants a repair
        #           (this is how a second interruption in one episode arises).
        # REPAIR_ACTIVE: an event arriving mid-repair is DEFERRED, not ignored:
        #           the running repair has a bounded horizon and a safe
        #           fallback, and replanning mid-repair risks livelock. It is
        #           recorded and re-detected once the repair completes.
        st = self.program.active_state()
        if st in (StageState.ACTIVE, StageState.RESUMED) and not self._mid_repair(st):
            ev = self.detector.detect(ctx)
            # Latch: a predicate combination already repaired must not
            # re-trigger.  Some predicates are permanent (a relocated target
            # stays relocated); without latching the resumed stage would be
            # re-interrupted forever and never finish.
            key = self.env.predicates(self.cfg.d_react).key()
            if ev.requires_program_repair and key and key not in self._handled:
                self._pending_key = key
                self._plan_and_splice(ev, ctx)
        elif st == StageState.REPAIR_ACTIVE:
            ev = self.detector.detect(ctx)
            if ev.requires_program_repair:
                self.deferred_events.append((ctx.t, ev.event_id, ev.event_type.value))

        # drive the (possibly new) active stage
        stage = self.program.active_stage()
        behavior = stage.metadata.get("behavior", "progress")
        a = control(behavior, ctx, stage, self.continuation, self.params, ctx.task_goal)
        state = self.program.active_state()
        in_rep = state in (StageState.REPAIR_ACTIVE, StageState.RESUMED)
        rec = record(
            ctx.t, a, stage, state.value,
            event_id=self.continuation.event_id if in_rep and self.continuation else None,
            template=self.template if in_rep else None,
            cont_ts=self.continuation.timestamp if in_rep and self.continuation else None,
        )
        self.cur_steps += 1
        return a, rec

    # --- pipeline ---------------------------------------------------------
    def _plan_and_splice(self, ev, ctx: ExecutionContext) -> None:
        handoff = self._handoff_for(ctx)
        cont = Continuation(
            interrupted_stage_id=self.program.active_id(),
            stage_mode=self.program.active_stage().mode,
            state=ctx.state.copy(),
            ee_pose=ctx.state.copy(),
            attachment_state=dict(ctx.attachments),
            nominal_target=ctx.task_goal.copy(),
            resume_contract=(resume_contract(handoff, self.cfg.theta_pour)
                             if handoff is not None else None),
            handoff_pose=handoff,
            progress_marker=float(np.linalg.norm(ctx.position - self.cfg.p_init)),
            timestamp=ctx.t,
            event_id=ev.event_id,
        )
        # reacquire target is the dropped object; task target is the CURRENT goal
        target = ctx.reacquire_pos if not ctx.object_grasped else None
        self.params = build_params(self.cfg, handoff_pose=handoff, target_pos=target,
                                   task_goal=ctx.task_goal)

        # The full active predicate set -- the SAME channel every policy gets.
        preds = self.env.predicates(self.cfg.d_react)
        abstract_init = state_from_predicates(preds)
        goal = self._repair_goal(preds)

        self.generator = self._make_generator(self.params)
        manager = self._build_manager(
            params=self.params, limits=self.limits,
            weights=self._score_weights(),
            anchor_id=self.program.active_id(),
            successor_id=self.program.next_id() or "__succ__",
            generator=self.generator,
            cfg=self.cfg,
            horizon_budget=self.cfg.horizon,
        )
        result = manager.plan(ev, cont, abstract_init, goal, ctx=ctx, env=self.env)
        self._trace.append(result.summary())
        self._last_plan = getattr(self.generator, "last_plan", None)
        self._last_init = abstract_init

        if result.selected is None:
            self.fallback.engage()
            self.program.activate_safe_fallback(reason="no-candidate")
            self.failed_safe = True
            return

        self.continuation = cont
        self.template = result.selected.template_name
        self.program.set_pending_continuation(cont)
        self.program.interrupt_active_stage(cont)
        self.program.splice_repair_before_successor(result.selected.stages, cont)
        if self._pending_key:
            self._handled.add(self._pending_key)
        self.cur_steps = 0

    # --- ablation hooks (overridden in policies/ablations.py) -------------
    def _handoff_for(self, ctx):
        return ctx.position.copy()

    def _repair_goal(self, preds):
        return goal_from_predicates(preds)

    def _build_manager(self, **kw):
        return RepairManager(**kw)

    def _score_weights(self):
        from ..repair.scorer import ScoreWeights
        return ScoreWeights()

    def _validate_restore(self, ctx) -> bool:
        return self.program.mark_restore_validated(ctx.state, ctx.keypoints)

    def _record_provenance(self) -> bool:
        return True

    def _mid_repair(self, st) -> bool:
        """True while repair operator stages are running (not the resumed
        instance, which is nominal work on the interrupted stage)."""
        return st == StageState.REPAIR_ACTIVE

    def _make_generator(self, params):
        """Runtime operator synthesis.  Overridden by TemplateRepairPolicy to
        use prewritten templates instead."""
        return SynthesisGenerator(params)

    def _maybe_advance(self, ctx: ExecutionContext) -> None:
        # loop because several zero-length guards can fire on one tick
        for _ in range(16):
            if self.program.finished or self.fallback.active:
                return
            stage = self.program.active_stage()
            exit_kind = stage.metadata.get("exit_kind", "nominal")

            satisfied = stage_exit(
                stage, ctx, self.cur_steps, self.continuation, self.params, ctx.task_goal
            )

            # bounded termination for repair stages
            if not satisfied and stage.kind == "repair" and self.cur_steps > stage.max_steps:
                self.fallback.engage()
                self.program.activate_safe_fallback(reason=f"{stage.stage_id}-timeout")
                self.failed_safe = True
                return

            if not satisfied:
                return

            # restore gate: validate the continuation contract before entering RESUMED
            if exit_kind == "restore_contract":
                ok = self._validate_restore(ctx)
                if not ok:
                    if self.cur_steps > stage.max_steps:
                        self.fallback.engage()
                        self.program.activate_safe_fallback(reason="restore-unvalidated")
                        self.failed_safe = True
                    return  # keep driving the Resume stage toward handoff

            try:
                alive = self.program.advance()
            except RestorationBlocked:
                self.fallback.engage()
                self.program.activate_safe_fallback(reason="restoration-blocked")
                self.failed_safe = True
                return
            self.cur_steps = 0
            if not alive:
                self._done = True
                return

    def finished(self) -> bool:
        return self._done or self.program.finished

    def trace_lines(self) -> List[str]:
        return self._trace
