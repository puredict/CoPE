"""Deliverables 5-8: model-mismatch study with verification confusion matrices.

Planning model f-hat (nominal) is separated from execution f (perturbed).  A
candidate ACCEPTED by the verifier that then fails physically is a FALSE ACCEPT
-- the headline verification metric.

Confusion (per episode where a repair was planned):
                      actual success   actual failure
    verifier accept   true accept      FALSE ACCEPT
    verifier reject   FALSE REJECT*    true reject
(*a rejected plan routes to safe fallback; "false reject" counts episodes where
 the fallback fired yet the scene was solvable by the nominal-accepted plan.)

Usage:
  python scripts/run_mismatch.py --quick    # 10 seeds
  python scripts/run_mismatch.py            # 50 seeds
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from collections import defaultdict

import numpy as np

from rekep_repair.benchmark import (
    CONDITIONS, FAMILIES, SEVERITIES, ProportionSummary, episode_grid,
    holm_correction, mcnemar_exact, paired_bootstrap_diff, sample_scene,
)
from rekep_repair.benchmark.mismatch import LEVEL_ORDER, LEVELS, MismatchedEnv
from rekep_repair.execution.executor import Executor
from rekep_repair.policies.verified_repair import VERIFIER_POLICIES
from rekep_repair.synthetic.env import Synthetic2DEnv

VARIANTS = list(VERIFIER_POLICIES)


def run_one(spec, level, factory):
    cfg = sample_scene(spec)
    env = MismatchedEnv(Synthetic2DEnv(cfg, seed=spec.seed), LEVELS[level],
                        seed=spec.seed)
    pol = factory()
    rep = Executor(env).run(pol).report()
    return rep, pol


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--seeds", type=int, default=None)
    args = ap.parse_args()
    n_seeds = args.seeds if args.seeds else (10 if args.quick else 50)

    conditions = [c for c in CONDITIONS if c != "none"]
    specs = episode_grid(FAMILIES, conditions, SEVERITIES, n_seeds=n_seeds)
    print(f"Mismatch study: {len(specs)} paired episodes x {len(LEVEL_ORDER)} levels "
          f"x {len(VARIANTS)} verifiers = {len(specs)*len(LEVEL_ORDER)*len(VARIANTS)} episodes\n")

    # results[level][variant] -> list of (accepted, success)
    results = defaultdict(lambda: defaultdict(list))
    raw = defaultdict(lambda: defaultdict(list))
    for spec in specs:
        for level in LEVEL_ORDER:
            for v in VARIANTS:
                rep, pol = run_one(spec, level, VERIFIER_POLICIES[v])
                accepted = bool(getattr(pol, "accepted_any", False))
                success = bool(rep["safe_delivery"])
                results[level][v].append((accepted, success))
                raw[level][v].append((rep, getattr(pol, "n_replans", 0)))

    # --- confusion matrices ----------------------------------------------
    print("=" * 100)
    print("VERIFICATION CONFUSION BY MISMATCH LEVEL")
    print("  FA = false accept (verifier accepted, execution failed)")
    print("  FR = false reject (verifier rejected -> fallback, but scene was solvable)")
    print("=" * 100)
    print(f"{'level':10} {'verifier':22} {'TA':>6} {'FA':>6} {'FR':>6} {'TR':>6} "
          f"{'FA rate':>9} {'FR rate':>9} {'precision':>10} {'recall':>8} {'SD':>19}")
    fa_curve = defaultdict(dict)
    fr_curve = defaultdict(dict)
    for level in LEVEL_ORDER:
        # solvable-by-nominal reference for the FR definition
        nom = {i: s for i, (a, s) in enumerate(results[level]["online[nominal]"])}
        for v in VARIANTS:
            pairs = results[level][v]
            ta = sum(1 for a, s in pairs if a and s)
            fa = sum(1 for a, s in pairs if a and not s)
            fr = sum(1 for i, (a, s) in enumerate(pairs) if (not a) and nom.get(i, False))
            tr = sum(1 for i, (a, s) in enumerate(pairs) if (not a) and not nom.get(i, False))
            n_acc = ta + fa
            n_rej = fr + tr
            fa_rate = fa / n_acc if n_acc else 0.0
            fr_rate = fr / n_rej if n_rej else 0.0
            precision = ta / n_acc if n_acc else float("nan")
            recall = ta / max(1, sum(1 for a, s in pairs if s))
            sd = ProportionSummary(v, sum(1 for a, s in pairs if s), len(pairs)).fmt()
            fa_curve[v][level] = fa_rate
            fr_curve[v][level] = fr_rate
            print(f"{level:10} {v:22} {ta:6d} {fa:6d} {fr:6d} {tr:6d} "
                  f"{fa_rate:9.3f} {fr_rate:9.3f} {precision:10.3f} {recall:8.3f} {sd:>19}")
        print()

    # --- FA / FR curves ---------------------------------------------------
    print("=" * 100)
    print("FALSE-ACCEPT / FALSE-REJECT CURVES (rate vs mismatch level)")
    print("=" * 100)
    for label, curve in (("FALSE ACCEPT", fa_curve), ("FALSE REJECT", fr_curve)):
        print(f"\n{label}")
        print(f"  {'verifier':22}" + "".join(f"{l:>12}" for l in LEVEL_ORDER))
        for v in VARIANTS:
            print(f"  {v:22}" + "".join(f"{curve[v][l]:>12.3f}" for l in LEVEL_ORDER))

    # --- paired comparison vs nominal at each level -----------------------
    print("\n" + "=" * 100)
    print("PAIRED safe-delivery difference vs online[nominal] (bootstrap 95% CI, McNemar Holm)")
    print("=" * 100)
    for level in LEVEL_ORDER:
        base = [s for a, s in results[level]["online[nominal]"]]
        raw_p, rows = {}, {}
        for v in VARIANTS:
            if v == "online[nominal]":
                continue
            other = [s for a, s in results[level][v]]
            d, lo, hi = paired_bootstrap_diff([float(x) for x in other],
                                              [float(x) for x in base])
            b01, b10, p = mcnemar_exact(other, base)
            raw_p[v] = p
            rows[v] = (d, lo, hi)
        adj = holm_correction(raw_p)
        print(f"\n-- {level}")
        for v, (d, lo, hi) in rows.items():
            sig = "*" if adj[v] < 0.05 else " "
            print(f"   {v:22} nominal-other {d:+7.3f} [{lo:+.3f}, {hi:+.3f}]  "
                  f"p_holm={adj[v]:.4f}{sig}")

    # --- replans / latency ------------------------------------------------
    print("\n" + "=" * 100)
    print("RECEDING-HORIZON COST (mean replans per episode)")
    print("=" * 100)
    for level in LEVEL_ORDER:
        rl = np.mean([n for _r, n in raw[level]["online[receding]"]])
        print(f"  {level:10} replans={rl:.3f}")


if __name__ == "__main__":
    main()
