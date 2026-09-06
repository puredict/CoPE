"""Deliverable 5: ablation tables on the randomized paired benchmark.

Each ablation removes exactly one mechanism from the online policy.  Paired
seeds, Wilson CIs, paired-bootstrap differences vs. the full method, exact
McNemar with Holm correction.

Usage:
  python scripts/run_ablations.py --quick     # 8 seeds
  python scripts/run_ablations.py             # 30 seeds
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from collections import defaultdict

import numpy as np

from rekep_repair.benchmark import (
    CONDITIONS, FAMILIES, SEVERITIES, ProportionSummary, episode_grid,
    holm_correction, mcnemar_exact, paired_bootstrap_diff, run_grid,
)
from rekep_repair.policies import OnlineRepairPolicy
from rekep_repair.policies.ablations import ABLATIONS

FULL = "online_repair(full)"
METRICS = ("safe_delivery", "collision_free_recovery", "task_success")
COMPOUND = ("obstacle+slip", "obstacle+relocation", "slip+relocation")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--seeds", type=int, default=None)
    args = ap.parse_args()
    n_seeds = args.seeds if args.seeds else (8 if args.quick else 30)

    conditions = [c for c in CONDITIONS if c != "none"]
    specs = episode_grid(FAMILIES, conditions, SEVERITIES, n_seeds=n_seeds)
    methods = {FULL: OnlineRepairPolicy, **ABLATIONS}
    print(f"Ablations: {len(specs)} paired episodes/method x {len(methods)} methods "
          f"= {len(specs)*len(methods)} episodes\n")

    results = run_grid(specs, methods)

    # --- headline table ---------------------------------------------------
    print("=" * 100)
    print("ABLATIONS (Wilson 95% CI) + extra outcome rates")
    print("=" * 100)
    print(f"{'method':24} {'SD':>21} {'TS':>21} {'collide':>8} {'failsafe':>9} {'handoff_err':>12}")
    for m in methods:
        recs = results[m]
        n = len(recs)
        sd = ProportionSummary(m, sum(r.safe_delivery for r in recs), n).fmt()
        ts = ProportionSummary(m, sum(r.task_success for r in recs), n).fmt()
        col = np.mean([r.collided for r in recs])
        fs = np.mean([r.failed_safe for r in recs])
        ge = np.mean([r.goal_error for r in recs])
        print(f"{m:24} {sd:>21} {ts:>21} {col:8.3f} {fs:9.3f} {ge:12.3f}")

    # --- paired vs full ---------------------------------------------------
    print("\n" + "=" * 100)
    print(f"PAIRED vs {FULL}: (full - ablated) risk difference [95% CI], McNemar Holm-adj")
    print("=" * 100)
    for metric in METRICS:
        base = [getattr(r, metric) for r in results[FULL]]
        raw_p, rows = {}, {}
        for m in ABLATIONS:
            other = [getattr(r, metric) for r in results[m]]
            d, lo, hi = paired_bootstrap_diff([float(x) for x in other],
                                              [float(x) for x in base])
            b01, b10, p = mcnemar_exact(other, base)
            raw_p[m] = p
            rows[m] = (d, lo, hi, b01, b10)
        adj = holm_correction(raw_p)
        print(f"\n-- {metric}")
        print(f"   {'ablation':24} {'full-abl':>10} {'95% CI':>20} {'disc':>11} {'p_holm':>9}")
        for m, (d, lo, hi, b01, b10) in rows.items():
            sig = "*" if adj[m] < 0.05 else " "
            print(f"   {m:24} {d:+10.3f} [{lo:+.3f}, {hi:+.3f}] "
                  f"{b01:5d}/{b10:<5d} {adj[m]:9.4f}{sig}")

    # --- targeted causal checks ------------------------------------------
    print("\n" + "=" * 100)
    print("TARGETED CAUSAL PREDICTIONS")
    print("=" * 100)
    comp_sd = defaultdict(list)
    for m in methods:
        for r in results[m]:
            if r.spec_key.split("|")[1] in COMPOUND:
                comp_sd[m].append(r.safe_delivery)

    def rate(m, key="safe_delivery"):
        return np.mean([getattr(r, key) for r in results[m]])

    checks = [
        ("NoRolloutVerification -> more collisions",
         np.mean([r.collided for r in results["abl_no_rollout"]]),
         np.mean([r.collided for r in results[FULL]]), "higher"),
        ("NoEventComposition -> lower COMPOUND safe delivery",
         np.mean(comp_sd["abl_no_composition"]), np.mean(comp_sd[FULL]), "lower"),
        ("NoSynthesis -> lower COMPOUND safe delivery",
         np.mean(comp_sd["abl_no_synthesis"]), np.mean(comp_sd[FULL]), "lower"),
        ("NoRestoreGate -> higher goal error",
         np.mean([r.goal_error for r in results["abl_no_restore_gate"]]),
         np.mean([r.goal_error for r in results[FULL]]), "higher"),
        ("NoContinuationContract -> higher goal error",
         np.mean([r.goal_error for r in results["abl_no_cont_contract"]]),
         np.mean([r.goal_error for r in results[FULL]]), "higher"),
    ]
    for label, abl, full, direction in checks:
        ok = (abl > full + 1e-9) if direction == "higher" else (abl < full - 1e-9)
        print(f"  [{'CONFIRMED' if ok else 'NOT OBSERVED':13}] {label:52} "
              f"ablated={abl:.3f} full={full:.3f}")

    print("\nA 'NOT OBSERVED' row is reported as-is: the mechanism did not measurably")
    print("change that outcome in this benchmark, which is evidence about the")
    print("benchmark's discriminating power, not a result to be hidden.")


if __name__ == "__main__":
    main()
