"""Deliverable 7: novel COMPOUND event (obstacle intrusion + object slip).

Both paradigms share the same atomic operators and event predicates.  The exact
combined recovery sequence exists as NO prewritten template/branch.  The drop
lands near the obstacle, so reacquiring the object REQUIRES clearing the
obstacle first -- a single-class branch cannot do both.

* offline_full (branch per single class) selects one class's branch and cannot
  compose -> it reacquires through the obstacle (collision).
* template_repair instantiates one event-class template -> same failure.
* online_repair SYNTHESIZES the interleaved program at runtime -> safe delivery.

Success = object delivered AND no collision.

Run:  python scripts/compare_novel_composition.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from rekep_repair.synthetic.dynamics import Obstacle, SceneConfig
from rekep_repair.synthetic.env import Synthetic2DEnv
from rekep_repair.execution.executor import Executor
from rekep_repair.policies import (
    OfflineSingleEventCoveragePolicy,
    TemplateRepairPolicy,
    OnlineRepairPolicy,
)


def main() -> None:
    cfg = SceneConfig(
        p_init=np.array([0.2, 0.0]), slip_time=2, drop_offset=np.array([0.18, 0.03]),
        obstacle=Obstacle(np.array([0.5, 0.05]), np.array([0.5, 0.05]), 0.12, 2, 40),
    )
    print("Novel COMPOUND disturbance: obstacle intrusion + object slip at t=2")
    print("(drop lands by the obstacle; reacquiring requires clearing it first)")
    print("No prewritten template/branch encodes this combination.\n")
    print(f"{'method':16} {'delivered':9} {'collided':8} {'safe_success':12} {'note'}")
    print("-" * 78)

    methods = [
        ("offline_single", OfflineSingleEventCoveragePolicy(),
         "picks one class branch; reacquires through obstacle"),
        ("template_repair", TemplateRepairPolicy(),
         "instantiates one class template; cannot compose"),
        ("online_repair", OnlineRepairPolicy(),
         "SYNTHESIZES interleaved plan at runtime"),
    ]
    for name, pol, note in methods:
        env = Synthetic2DEnv(cfg, seed=0)
        res = Executor(env).run(pol)
        r = res.report()
        delivered = bool(env.grasped and np.linalg.norm(env.state[:2] - cfg.p_goal) < cfg.eps_goal)
        safe_success = delivered and not r["collided"]
        print(f"{name:16} {str(delivered):9} {str(r['collided']):8} "
              f"{str(safe_success):12} {note}")

    # show the synthesized program
    env = Synthetic2DEnv(cfg, seed=0)
    pol = OnlineRepairPolicy()
    Executor(env).run(pol)
    if pol._trace:
        sel = [l.strip() for l in pol._trace[-1].split("\n") if "SELECTED" in l]
        if sel:
            print(f"\nOnline synthesized (no such template exists):\n  {sel[0]}")


if __name__ == "__main__":
    main()
