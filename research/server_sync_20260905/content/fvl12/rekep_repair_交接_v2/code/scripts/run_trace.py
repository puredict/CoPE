"""Deliverable 5: a complete runtime trace of online program SYNTHESIS + repair.

Shows: event detection -> continuation capture -> abstract-state induction ->
operator SEARCH (explored abstract states) -> candidate legality/feasibility/
scoring -> selected synthesized program -> graph rewrite -> restore validation
-> resumed execution.  CPU-only.

Run:  python scripts/run_trace.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from rekep_repair.synthetic.dynamics import SceneConfig
from rekep_repair.synthetic.env import Synthetic2DEnv
from rekep_repair.policies.online_repair import OnlineRepairPolicy
from rekep_repair.policies.common import build_params, resume_contract
from rekep_repair.events.event import Event, EventType
from rekep_repair.program.continuation import Continuation
from rekep_repair.program.stage import Mode
from rekep_repair.repair.abstract_state import initial_state
from rekep_repair.repair.feasibility_filter import ControlLimits
from rekep_repair.repair.repair_manager import RepairManager
from rekep_repair.repair.synthesis_generator import SynthesisGenerator


def line(c=""):
    print(c)


def main() -> None:
    cfg = SceneConfig()
    env = Synthetic2DEnv(cfg, seed=0)
    pol = OnlineRepairPolicy()
    pol.reset(env)
    ctx = env.observe()

    line("=" * 78)
    line("ONLINE OPERATOR SYNTHESIS + CONTINUATION-CARRYING REPAIR -- RUNTIME TRACE")
    line("=" * 78)
    line(f"nominal program : {[s.stage_id for s in pol.program.stages()]}")
    line()

    prev = (pol.program.active_id(), pol.program.active_state().value)
    spliced = False
    restore_announced = False

    for t in range(cfg.horizon):
        was_in_repair = pol.program.in_repair
        order_before = list(pol.program._order)
        a, rec = pol.act(ctx)

        if not was_in_repair and pol.program.in_repair and not spliced:
            spliced = True
            cont = pol.continuation
            plan = pol._last_plan
            init = pol._last_init
            line(f"[t={t:02d}] EVENT DETECTED  id={cont.event_id}  "
                 f"interrupted={cont.interrupted_stage_id}")
            line(f"[t={t:02d}] CONTINUATION kappa_t  state={np.round(cont.state,3).tolist()} "
                 f"handoff={np.round(cont.handoff_pose,3).tolist()} attach={cont.attachment_state}")
            line(f"[t={t:02d}] ABSTRACT STATE induced from world:")
            line(f"        true flags = {init.true_flags()}")
            line(f"[t={t:02d}] OPERATOR SEARCH  (goal: restore_valid & not obstacle_present)")
            line(f"        expanded {plan.n_expanded} abstract states")
            for flags, applic in plan.explored[:8]:
                line(f"          state{list(flags)}  applicable={list(applic)}")
            if len(plan.explored) > 8:
                line(f"          ... (+{len(plan.explored)-8} more)")
            line(f"        SYNTHESIZED plans (best first):")
            for ops, c in plan.plans:
                line(f"          cost={c:.1f}  {' -> '.join(ops)}")
            line(f"[t={t:02d}] SELECT after legality+feasibility+scoring:")
            for ln in pol._trace[-1].split("\n"):
                if "SELECTED" in ln or "rejected" in ln:
                    line("        " + ln.strip())
            line(f"[t={t:02d}] GRAPH REWRITE  {order_before} -> {pol.program._order}")
            line(f"        (interrupted stage SUSPENDED, not COMPLETED)")
            line()

        cur = (pol.program.active_id(), pol.program.active_state().value)
        if cur != prev:
            tag = "  <-- RESUMED continuation" if pol.program.is_resumed_node(cur[0]) else ""
            line(f"[t={t:02d}] -> '{cur[0]}' [{cur[1]}]{tag}")
            prev = cur
        if pol.program.restore_validated() and not restore_announced:
            restore_announced = True
            line(f"[t={t:02d}] RESTORE CONTRACT VALIDATED")

        ctx = env.step(a)
        if pol.finished():
            break

    line()
    line(f"OUTCOME  final_pos={np.round(env.state[:2],3).tolist()} "
         f"theta={round(float(env.state[2]),3)} failed_safe={pol.failed_safe}")
    line(f"         final program = {pol.program._order}")

    demonstrate_screening(cfg)


def demonstrate_screening(cfg: SceneConfig) -> None:
    """Show legality/feasibility rejecting SYNTHESIZED candidates: same event,
    normal vs. under-actuated robot."""
    line()
    line("=" * 78)
    line("APPENDIX: SYNTHESIZED-CANDIDATE SCREENING (rejection reasons)")
    line("=" * 78)
    handoff = np.array([0.12, 0.0])
    cont = Continuation(
        interrupted_stage_id="pour", stage_mode=Mode.POUR,
        state=np.array([0.12, 0.0, 1.0]), ee_pose=np.array([0.12, 0.0, 1.0]),
        attachment_state={"object": "grasped"}, nominal_target=cfg.p_goal,
        resume_contract=resume_contract(handoff, cfg.theta_pour),
        handoff_pose=handoff, timestamp=2, event_id="E-demo",
    )
    event = Event(EventType.OBSTACLE_INTRUSION, 0.6, ("obstacle",), t=2, event_id="E-demo")
    params = build_params(cfg, handoff_pose=handoff)
    init = initial_state(obstacle_present=True, safe_clearance=False, object_grasped=True)

    for label, w_max in [("normal robot (w_max=0.30)", 0.30),
                         ("under-actuated robot (w_max=0.02)", 0.02)]:
        limits = ControlLimits(v_max=cfg.v_max, w_max=w_max, ws_lo=cfg.ws_lo, ws_hi=cfg.ws_hi)
        mgr = RepairManager(params, limits, anchor_id="pour", successor_id="__succ__",
                            generator=SynthesisGenerator(params))
        res = mgr.plan(event, cont, init)
        line(f"\n-- {label}")
        for ln in res.summary().split("\n"):
            line("   " + ln)


if __name__ == "__main__":
    main()
