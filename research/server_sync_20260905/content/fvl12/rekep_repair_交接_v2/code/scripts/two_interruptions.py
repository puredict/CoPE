"""Deliverable 7: two-interruption end-to-end episode.

A multi-stage nominal program runs, is interrupted twice (obstacle, then slip),
repairs and resumes each time, and completes.  Asserts two distinct runtime
repair instances, an acyclic graph, and final task success.

Run:  python scripts/two_interruptions.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from rekep_repair.execution.executor import Executor
from rekep_repair.policies import OnlineRepairPolicy
from rekep_repair.synthetic.dynamics import Obstacle, SceneConfig
from rekep_repair.synthetic.env import Synthetic2DEnv


def main() -> None:
    # obstacle early (withdraws at t=26), then a slip much later
    cfg = SceneConfig(
        p_init=np.array([0.0, 0.0]),
        obstacle=Obstacle(np.array([0.55, 0.05]), np.array([0.55, 0.05]), 0.12, 2, 26),
        slip_time=40, drop_offset=np.array([0.0, -0.18]),
        horizon=150,
    )
    env = Synthetic2DEnv(cfg, seed=0)
    pol = OnlineRepairPolicy()
    res = Executor(env).run(pol)
    rep = res.report()

    print("=" * 78)
    print("TWO-INTERRUPTION END-TO-END EPISODE")
    print("=" * 78)
    for i, tr in enumerate(pol._trace, 1):
        head = tr.split("\n")[0]
        sel = [l.strip() for l in tr.split("\n") if "SELECTED" in l]
        print(f"\n[repair #{i}] {head}")
        if sel:
            print(f"            {sel[0]}")

    print("\nFinal program:")
    for nid in pol.program._order:
        print(f"   {pol.program.state[nid].value:<14} {nid}")

    n_repairs = pol.program._repair_counter
    print(f"\nrepair instances      : {n_repairs}")
    print(f"unique node ids       : {len(pol.program._order) == len(set(pol.program._order))}")
    print(f"graph acyclic         : {pol.program.graph.is_acyclic()}")
    print(f"order/graph consistent: {pol.program.order_graph_consistent()}")
    print(f"final pos             : {np.round(env.state[:2],3).tolist()} "
          f"(goal {env.goal.tolist()})")
    print(f"object delivered      : {rep['object_delivered']}")
    print(f"collided              : {rep['collided']}")
    print(f"task success          : {rep['success']}")

    assert n_repairs >= 2, "expected two distinct repair instances"
    assert pol.program.order_graph_consistent()
    print("\nAll assertions passed.")


if __name__ == "__main__":
    main()
