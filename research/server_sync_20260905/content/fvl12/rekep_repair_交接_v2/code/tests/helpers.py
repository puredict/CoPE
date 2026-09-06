"""Shared test builders."""

from __future__ import annotations

import numpy as np

from rekep_repair.program.contracts import Contract, ball_contract
from rekep_repair.program.continuation import Continuation
from rekep_repair.program.stage import Mode, StageSpec
from rekep_repair.repair.candidate import RepairCandidate


def stage(sid, behavior="hold", exit_kind="one_step", *, requires_grasp=False,
          establishes_grasp=False, provides_restore=False, terminal=False,
          kind="repair", max_steps=30, mode=Mode.SUSPEND) -> StageSpec:
    return StageSpec(
        stage_id=sid, mode=mode, kind=kind, max_steps=max_steps,
        metadata={
            "behavior": behavior, "exit_kind": exit_kind, "operator": sid,
            "requires_grasp": requires_grasp, "establishes_grasp": establishes_grasp,
            "provides_restore": provides_restore, "terminal": terminal,
            "target_theta": 0.0,
        },
    )


def continuation(state=(0.1, 0.0, 1.0), released=False, handoff=(0.1, 0.0),
                 theta_pour=1.0, contract_holds=True, ts=5) -> Continuation:
    if contract_holds:
        rc = ball_contract("resume", np.array([handoff[0], handoff[1], theta_pour]), 0.15)
    else:
        rc = Contract("never", predicate=lambda x, k=None: False,
                      margin_fn=lambda x, k=None: -1.0)
    return Continuation(
        interrupted_stage_id="pour",
        stage_mode=Mode.POUR,
        state=np.array(state, float),
        ee_pose=np.array(state, float),
        attachment_state={"object": "released" if released else "grasped"},
        nominal_target=np.array([1.0, 0.0]),
        resume_contract=rc,
        handoff_pose=np.array(handoff, float),
        timestamp=ts,
        event_id="E0001@t5",
    )


def candidate(stages, cont, internal_edges=None) -> RepairCandidate:
    return RepairCandidate(template_name="->".join(s.stage_id for s in stages),
                           stages=list(stages), continuation=cont,
                           internal_edges=internal_edges)
