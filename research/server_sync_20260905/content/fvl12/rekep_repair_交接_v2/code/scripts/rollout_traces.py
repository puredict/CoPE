"""Deliverable 6: sequential feasibility traces for ACCEPTED and REJECTED
candidates.

The compound scene produces two abstract plans of equal symbolic cost.  Only a
sequential rollout -- propagating state operator-by-operator through the real
geometry -- can tell them apart: one reacquires the object while the obstacle is
still present (collision), the other clears first.

Run:  python scripts/rollout_traces.py
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
    cfg = SceneConfig(
        p_init=np.array([0.2, 0.0]), slip_time=2, drop_offset=np.array([0.18, 0.03]),
        obstacle=Obstacle(np.array([0.5, 0.05]), np.array([0.5, 0.05]), 0.12, 2, 40),
    )
    print("=" * 78)
    print("SEQUENTIAL CANDIDATE VERIFICATION (compound: obstacle + slip)")
    print("=" * 78)
    print("Drop lands beside the obstacle, so reacquiring before clearing collides.\n")

    env = Synthetic2DEnv(cfg, seed=0)
    pol = OnlineRepairPolicy()
    Executor(env).run(pol)

    if not pol._trace:
        print("no repair planned")
        return
    for ln in pol._trace[0].split("\n"):
        print("  " + ln)

    print("\nEach 'rollout' line is a full operator-by-operator simulation:")
    print("predicted duration, min clearance, handoff error, collision, and the")
    print("residual of the ACTIVE EVENT REQUIREMENTS re-verified independently of")
    print("the planner's symbolic model. A non-empty residual or a collision is a")
    print("HARD REJECT, never a soft penalty.")


if __name__ == "__main__":
    main()
