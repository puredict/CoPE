"""Control arm: the interruption is delivered but the task state is NOT changed.

This is the floor. It keeps executing the original goals, so it will pursue a
cancelled goal and use a stale target. It exists to show what the interruption
costs when nothing adapts.
"""
from __future__ import annotations
from typing import Any, Dict

from ..recovery_manager import ExecutorRequest, RecoveryManager
from ..state_store import StateStore
from .adaptation_input import AdaptationInput


class NoAdaptationPolicy:
    """Ablates the SEMANTIC update only.

    It still enters the same downstream repair stack, so the arm isolates
    "did not update the task state" rather than confounding that with "had no
    repair engine". Because the constraint state does not change, the goal
    compiler derives requirements from the world alone.
    """

    name = "no_adaptation"

    def __init__(self, store: StateStore, horizon_steps: int = 900,
                 repair_engine=None):
        self.store = store
        self.mgr = RecoveryManager(store, horizon_steps, repair_engine)
        self.n_model_calls = 0
        self.n_slots_edited = 0
        self.n_slots_emitted = 0
        self.last_repair = None

    def adapt(self, inp: AdaptationInput) -> ExecutorRequest:
        self.store.trace.record("no_adaptation", event_id=inp.event_id,
                                note="interruption observed; state unchanged")
        before = self.store.state
        self.last_repair = self.mgr.enter_repair_pipeline(
            before=before, after=self.store.state, adaptation=None,
            adaptation_kind="none", world=inp.world_state,
            event_id=inp.event_id, step=inp.event_step)
        return self.mgr.compile(budget=inp.compute_budget)
