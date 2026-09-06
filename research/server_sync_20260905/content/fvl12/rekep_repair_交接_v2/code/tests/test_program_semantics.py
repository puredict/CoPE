"""Semantic tests for the runtime stage state machine (props 1-4)."""

from __future__ import annotations

import numpy as np
import pytest

from rekep_repair.program.stage import Mode, StageSpec, StageState
from rekep_repair.program.task_program import RestorationBlocked, TaskProgram
from .helpers import continuation, stage


def _program():
    pour = StageSpec("pour", Mode.POUR, kind="nominal",
                     metadata={"behavior": "progress", "exit_kind": "nominal"})
    finish = StageSpec("finish", Mode.PLACE, kind="nominal",
                       metadata={"behavior": "progress", "exit_kind": "nominal"})
    return TaskProgram([pour, finish])


def test_interruption_does_not_complete_active_stage():
    tp = _program()
    cont = continuation()
    tp.set_pending_continuation(cont)
    tp.interrupt_active_stage(cont)
    assert tp.state["pour"] == StageState.SUSPENDED
    assert tp.state["pour"] != StageState.COMPLETED
    assert tp.in_repair


def test_nominal_successor_unreachable_during_repair():
    tp = _program()
    cont = continuation(contract_holds=False)   # restore will not validate
    tp.set_pending_continuation(cont)
    tp.interrupt_active_stage(cont)
    tp.splice_repair_before_successor(
        [stage("suspend", provides_restore=True)], cont
    )
    # successor 'finish' stays pending
    assert tp.state["finish"] == StageState.PENDING
    # advancing off the last repair stage would enter the RESUMED node, which
    # is blocked until restore validates
    with pytest.raises(RestorationBlocked):
        tp.advance()
    assert tp.state["finish"] == StageState.PENDING


def test_restore_failure_blocks_resumption():
    tp = _program()
    cont = continuation(contract_holds=False)
    tp.set_pending_continuation(cont)
    tp.interrupt_active_stage(cont)
    tp.splice_repair_before_successor([stage("resume", provides_restore=True)], cont)
    # restore cannot validate
    assert tp.mark_restore_validated(np.array([0.1, 0.0, 1.0])) is False
    with pytest.raises(RestorationBlocked):
        tp.advance()


def test_restore_blocked_transition_is_atomic():
    """P0-2: a blocked advance() must not mutate any state."""
    tp = _program()
    cont = continuation(contract_holds=False)
    tp.set_pending_continuation(cont)
    tp.interrupt_active_stage(cont)
    tp.splice_repair_before_successor([stage("resume", provides_restore=True)], cont)
    active_before = tp.active_id()
    resumed_id = tp._resumed_id
    assert tp.mark_restore_validated(np.array([9.0, 9.0, 9.0])) is False
    with pytest.raises(RestorationBlocked):
        tp.advance()
    # nothing changed
    assert tp.active_id() == active_before
    assert tp.state[active_before] == StageState.REPAIR_ACTIVE
    assert tp.state[resumed_id] == StageState.PENDING
    assert tp.state["pour"] == StageState.SUSPENDED


def _three_stage_program():
    def nom(sid, mode):
        return StageSpec(sid, mode, kind="nominal",
                         metadata={"behavior": "progress", "exit_kind": "nominal"})
    return TaskProgram([nom("pour", Mode.POUR), nom("transport", Mode.TRANSPORT),
                        nom("finish", Mode.PLACE)])


def test_two_sequential_repairs_keep_graph_acyclic():
    """P0-1: repeated repairs must not reuse node ids or create cycles."""
    tp = _three_stage_program()

    # repair 1 on 'pour'
    c1 = continuation(handoff=(0.1, 0.0), contract_holds=True, ts=2)
    c1 = _with_event(c1, "E0001@t2")
    tp.set_pending_continuation(c1)
    tp.interrupt_active_stage(c1)
    tp.splice_repair_before_successor([stage("resume", provides_restore=True)], c1)
    assert tp.mark_restore_validated(np.array([0.1, 0.0, 1.0]))
    tp.advance()   # enter resumed
    tp.advance()   # complete resumed -> transport ACTIVE
    assert tp.active_id() == "transport"
    assert not tp.in_repair

    # repair 2 on 'transport'
    c2 = continuation(handoff=(0.5, 0.0), contract_holds=True, ts=9)
    c2 = _with_event(c2, "E0002@t9")
    tp.set_pending_continuation(c2)
    tp.interrupt_active_stage(c2)
    tp.splice_repair_before_successor([stage("resume2", provides_restore=True)], c2)

    assert len(tp._order) == len(set(tp._order))     # no duplicate ids
    assert tp.graph.is_acyclic()
    assert tp.order_graph_consistent()


def _with_event(cont, event_id):
    from dataclasses import replace
    return replace(cont, event_id=event_id)


def test_successful_restore_resumes_saved_continuation():
    tp = _program()
    cont = continuation(contract_holds=True, handoff=(0.1, 0.0))
    tp.set_pending_continuation(cont)
    tp.interrupt_active_stage(cont)
    tp.splice_repair_before_successor([stage("resume", provides_restore=True)], cont)
    # at the handoff state the contract holds
    assert tp.mark_restore_validated(np.array([0.1, 0.0, 1.0])) is True
    assert tp.advance() is True                    # enters RESUMED node
    resumed = tp.active_id()
    assert tp.state[resumed] == StageState.RESUMED
    assert tp.is_resumed_node(resumed)
    tp.advance()                                   # completes resumed
    assert tp.state["pour"] == StageState.COMPLETED  # interrupted computation done
