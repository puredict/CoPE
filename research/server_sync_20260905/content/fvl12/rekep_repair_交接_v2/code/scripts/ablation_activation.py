"""Deliverable 2: internal ACTIVATION traces for every ablation (B1).

For each ablation we compare the internal causal variables against the full
method on the same paired episode:

    active RepairGoal | explored abstract states | synthesized plans |
    candidates surviving legality+rollout | selected candidate |
    restore decisions | concrete trajectory

A class name is not evidence.  This shows WHICH internal variable each ablation
actually moves -- and, crucially, which ones move nothing.

Run:  python scripts/ablation_activation.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from rekep_repair.benchmark import EpisodeSpec, sample_scene
from rekep_repair.benchmark.probe import instrument
from rekep_repair.execution.executor import Executor
from rekep_repair.policies import OnlineRepairPolicy
from rekep_repair.policies.ablations import ABLATIONS
from rekep_repair.synthetic.env import Synthetic2DEnv

SCENES = [
    EpisodeSpec("upright_transport", "obstacle+slip", "high", 3),
    EpisodeSpec("constrained_place", "slip+relocation", "high", 7),
    EpisodeSpec("align_insert", "obstacle+relocation", "medium", 11),
]


def run(spec, factory):
    cfg = sample_scene(spec)
    env = Synthetic2DEnv(cfg, seed=spec.seed)
    pol = factory()
    pol.reset(env)
    act = instrument(pol)
    res = Executor(env).run(pol)
    act.trajectory = res.rollout.positions.copy()
    act.final_state = tuple(np.round(env.state, 5).tolist())
    return act, res.report()


def diff_report(full_act, full_rep, abl_act, abl_rep) -> dict:
    """Which internal variables actually differ?"""
    def traj_delta():
        a, b = full_act.trajectory, abl_act.trajectory
        n = min(len(a), len(b))
        return float(np.abs(a[:n] - b[:n]).max()) if n else 0.0

    return {
        "goal": full_act.goals() != abl_act.goals(),
        "explored": [a.explored_states for a in full_act.activations]
                    != [a.explored_states for a in abl_act.activations],
        "plans": full_act.plans() != abl_act.plans(),
        "generated": [a.generated for a in full_act.activations]
                     != [a.generated for a in abl_act.activations],
        "survived": [a.survived for a in full_act.activations]
                    != [a.survived for a in abl_act.activations],
        "selected": full_act.selections() != abl_act.selections(),
        "handoff": full_act.handoffs() != abl_act.handoffs(),
        "restore_dec": full_act.restore_validations != abl_act.restore_validations,
        "trajectory": traj_delta() > 1e-9,
        "outcome": (full_rep["safe_delivery"], full_rep["task_success"])
                   != (abl_rep["safe_delivery"], abl_rep["task_success"]),
        "traj_maxdiff": traj_delta(),
    }


def main() -> None:
    keys = ["goal", "explored", "plans", "generated", "survived", "selected",
            "handoff", "restore_dec", "trajectory", "outcome"]

    for spec in SCENES:
        print("=" * 104)
        print(f"SCENE {spec.key()}")
        print("=" * 104)
        full_act, full_rep = run(spec, OnlineRepairPolicy)
        print(f"  full: goals={full_act.goals()}")
        print(f"        selected={full_act.selections()}")
        print(f"        restore_decisions={full_act.restore_validations}  "
              f"SD={full_rep['safe_delivery']} TS={full_rep['task_success']}")
        print()
        print(f"  {'ablation':22} " + " ".join(f"{k[:9]:>10}" for k in keys))
        print("  " + "-" * 100)
        for name, P in ABLATIONS.items():
            abl_act, abl_rep = run(spec, P)
            d = diff_report(full_act, full_rep, abl_act, abl_rep)
            cells = " ".join(f"{('DIFF' if d[k] else '.'):>10}" for k in keys)
            print(f"  {name:22} {cells}")
        print()

    print("=" * 104)
    print("READING")
    print("=" * 104)
    print("'DIFF' = that internal variable differs from the full method on this")
    print("episode. An ablation whose row is ALL '.' does not change the causal")
    print("path at all on this scene -- which is a fact about the mechanism (or")
    print("the scene), not something to be papered over by tuning thresholds.")


if __name__ == "__main__":
    main()
