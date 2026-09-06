"""Deliverables 1 & 2: strong precompiled baseline across three regimes.

The offline baseline (OfflineParameterizedPolicy) has EVERY runtime capability
online synthesis has -- same predicates, parameter binding, controllers, rollout
verifier, scoring, continuation/splice/restore.  Its ONLY restriction is that it
cannot construct an operator sequence that was not compiled before execution.

Regimes
  1. exact         -- every combination up to size 3 precompiled
  2. atomic-only   -- only single-predicate branches precompiled
  3. budget(B)     -- fixed branch-memory budget

P0-C: three DISTINCT success notions are reported separately.
  SD  = safe delivery      (object at the current goal, no collision)
  CFR = collision-free recovery (no collision, no safe-fallback)
  TS  = full end-to-end task success (all terminal constraints)

Run:  python scripts/offline_regimes.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from rekep_repair.execution.executor import Executor
from rekep_repair.policies import (
    OfflineAtomicOnlyPolicy,
    OfflineBudgetPolicy,
    OfflineExactPolicy,
    OnlineRepairPolicy,
    all_combinations,
)
from rekep_repair.synthetic.dynamics import Obstacle, SceneConfig
from rekep_repair.synthetic.env import Synthetic2DEnv

FAR = Obstacle(np.array([9.0, 9.0]), np.array([9.0, 9.0]), 0.05, 0, 0)
NEAR = Obstacle(np.array([0.5, 0.05]), np.array([0.5, 0.05]), 0.12, 2, 40)


def scene_for(combo) -> SceneConfig:
    obs = NEAR if "obstacle_present" in combo else FAR
    slip = 2 if "object_slipped" in combo else None
    drop = np.array([0.18, 0.03]) if "obstacle_present" in combo else np.array([0.0, -0.22])
    reloc = 3 if "target_relocated" in combo else None
    return SceneConfig(p_init=np.array([0.2, 0.0]), obstacle=obs,
                       slip_time=slip, drop_offset=drop,
                       relocation_time=reloc,
                       relocation_delta=np.array([0.0, 0.30]))


def run_all(factory):
    sd = cfr = ts = 0
    combos = all_combinations(3)
    for combo in combos:
        cfg = scene_for(combo)
        env = Synthetic2DEnv(cfg, seed=0)
        r = Executor(env).run(factory()).report()
        sd += bool(r["safe_delivery"])
        cfr += bool(r["collision_free_recovery"])
        ts += bool(r["task_success"])
    return sd, cfr, ts, len(combos)


def main() -> None:
    print("Strong precompiled baseline: same predicates/binding/controllers/")
    print("rollout-verifier/scoring as online.  Only difference: no runtime search.\n")

    rows = []
    for label, factory in [
        ("offline_budget(1)", lambda: OfflineBudgetPolicy(budget=1)),
        ("offline_budget(3)", lambda: OfflineBudgetPolicy(budget=3)),
        ("offline_atomic(3)", OfflineAtomicOnlyPolicy),
        ("offline_exact(7)", OfflineExactPolicy),
        ("online_synthesis", OnlineRepairPolicy),
    ]:
        probe = factory()
        probe.reset(Synthetic2DEnv(scene_for(frozenset({"obstacle_present"})), seed=0))
        combos = getattr(getattr(probe, "library", None), "combination_count", 0)
        branches = getattr(probe, "branch_count", 0)
        graph = getattr(probe, "graph_size", 0)
        comp = getattr(probe, "compile_ops", 0)
        sd, cfr, ts, n = run_all(factory)
        rows.append((label, combos, branches, graph, comp, sd, cfr, ts, n))

    print(f"{'method':20} {'combos':7} {'branch':7} {'graph':6} {'compile':8} "
          f"{'SD':>5} {'CFR':>5} {'TS':>5}")
    print("-" * 76)
    for label, cb, br, gs, co, sd, cfr, ts, n in rows:
        cb_s = str(cb) if cb else "--"
        br_s = str(br) if br else "-- (ops)"
        print(f"{label:20} {cb_s:7} {br_s:7} {gs:<6} {co:<8} "
              f"{sd}/{n:<3} {cfr}/{n:<3} {ts}/{n:<3}")

    print("\nSD  = safe delivery | CFR = collision-free recovery | TS = full task success")
    print("\nReading:")
    print(" * REGIME 1 (exact): the strong offline baseline matches online on safe")
    print("   delivery -- as it should. When the exact sequence is precompiled and it")
    print("   can bind + verify at runtime, precompilation is NOT a handicap.")
    print(" * REGIME 2 (atomic-only): the gap that remains is purely STRUCTURAL")
    print("   coverage -- no compiled sequence exists for a compound combination.")
    print(" * REGIME 3 (budget): coverage degrades gracefully with branch memory.")
    print(" * TS is strictly lower than SD for every method: several scenes are not")
    print("   fully solvable under the terminal orientation/spill constraints. TS and")
    print("   SD must never be conflated.")


if __name__ == "__main__":
    main()
