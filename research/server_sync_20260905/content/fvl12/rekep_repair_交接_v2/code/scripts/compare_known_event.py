"""Deliverable 6: FAIR known-event comparison.

On an anticipated single-class event, the offline full-coverage baseline has a
precompiled branch and the online system synthesizes an equivalent plan.  Both
should succeed -- this is the control condition establishing that online repair
buys nothing extra when the event is anticipated (and pays synthesis latency).

Run:  python scripts/compare_known_event.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from rekep_repair.events.event import EventType
from rekep_repair.execution.executor import Executor
from rekep_repair.policies import (
    OfflineEnumeratedPolicy,
    OfflineSingleEventCoveragePolicy,
    OnlineRepairPolicy,
    TemplateRepairPolicy,
)
from rekep_repair.synthetic.dynamics import Obstacle, SceneConfig
from rekep_repair.synthetic.env import Synthetic2DEnv


def far():
    return Obstacle(np.array([9.0, 9.0]), np.array([9.0, 9.0]), 0.05, 0, 0)


def run(cfg, pol):
    env = Synthetic2DEnv(cfg, seed=0)
    res = Executor(env).run(pol)
    delivered = bool(env.grasped and np.linalg.norm(env.state[:2] - cfg.p_goal) < cfg.eps_goal)
    return res.report(), delivered


def main() -> None:
    scenes = {
        "obstacle intrusion": SceneConfig(),
        "object slip": SceneConfig(slip_time=8, drop_offset=np.array([0.0, -0.22]),
                                   obstacle=far()),
    }
    print("FAIR known-event comparison: offline_single anticipates ALL single classes")
    print("(a real branch is compiled for each), online synthesizes at runtime.\n")

    for scene, cfg in scenes.items():
        print(f"-- {scene}")
        for name, pol in [("offline_single ", OfflineSingleEventCoveragePolicy()),
                          ("template_repair", TemplateRepairPolicy()),
                          ("online_repair  ", OnlineRepairPolicy())]:
            r, delivered = run(cfg, pol)
            print(f"   {name}: delivered={str(delivered):5} collided={str(r['collided']):5} "
                  f"failed_safe={r['failed_safe']}")
        print()

    # budgeted variant: a coverage gap is a *budget* choice, not a rigged setup
    print("-- object slip, offline_enumerated precompiled ONLY {obstacle_present}")
    r, delivered = run(scenes["object slip"],
                       OfflineEnumeratedPolicy([frozenset({"obstacle_present"})]))
    print(f"   offline_enumerated: delivered={delivered}  failed_safe={r['failed_safe']} "
          f"(no branch for this combination -> safe stop)")
    print("\nReading: with full coverage, offline matches online on anticipated single")
    print("events. The online advantage is NOT on known classes -- it is on novel")
    print("compositions (see compare_novel_composition.py).")


if __name__ == "__main__":
    main()
