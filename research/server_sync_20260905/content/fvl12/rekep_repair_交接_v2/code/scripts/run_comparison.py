"""All five methods through the SAME harness on the obstacle-intrusion scene.

Every method shares environment, dynamics, control limits, event stream,
horizon, seed, and metric logger; they differ only in recovery policy.

Run:  python scripts/run_comparison.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rekep_repair.synthetic.dynamics import SceneConfig
from rekep_repair.synthetic.env import Synthetic2DEnv
from rekep_repair.execution.executor import Executor
from rekep_repair.policies import ALL_POLICIES


def main() -> None:
    cfg = SceneConfig()
    print("Obstacle-intrusion scene (a temporary hand); all methods, seed=0")
    print(f"{'method':16} {'success':7} {'danger':7} {'goal_err':8} {'min_clr':7} "
          f"{'collide':7} {'cont_prov':9} {'evt_attr':8}")
    print("-" * 76)
    for name, P in ALL_POLICIES.items():
        env = Synthetic2DEnv(cfg, seed=0)
        r = Executor(env).run(P()).report()
        print(f"{name:16} {str(r['success']):7} {r['danger_spill']:<7.3f} "
              f"{r['goal_error']:<8.3f} {r['min_clearance']:<7.3f} "
              f"{str(r['collided']):7} {r['continuation_linked_provenance']:<9} "
              f"{r['event_attribution']:<8}")

    print("\nReading: fixed collides; path-only keeps the pour tilt near the hazard")
    print("(spills); safe-stop / offline_full / template / online all recover a simple")
    print("temporary obstacle. Online is NOT uniquely better here -- this is the honest,")
    print("bounded claim. Its edge shows up on novel compositions (see other scripts).")
    print("Note event_attribution (method-neutral) is high for all recovering methods;")
    print("continuation-linked provenance is lower for offline BY CONSTRUCTION (it has")
    print("no continuation), so it is reported separately, not as a blanket advantage.")


if __name__ == "__main__":
    main()
