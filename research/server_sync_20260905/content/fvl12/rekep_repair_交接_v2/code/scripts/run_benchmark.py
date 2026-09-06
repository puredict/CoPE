"""Deliverables 3 & 4: randomized paired benchmark with confidence intervals.

Every method receives the IDENTICAL sampled episode (paired seeds by
construction).  Reports the three distinct success notions separately, with
Wilson intervals, paired bootstrap differences, exact McNemar tests, and Holm
correction across the family of comparisons.

Usage:
  python scripts/run_benchmark.py            # 50 seeds (full protocol)
  python scripts/run_benchmark.py --quick    # 8 seeds (smoke)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from collections import defaultdict

import numpy as np

from rekep_repair.benchmark import (
    CONDITIONS, FAMILIES, SEVERITIES, episode_grid,
    holm_correction, mcnemar_exact, paired_bootstrap_diff, run_grid,
    ProportionSummary,
)
from rekep_repair.policies import (
    OfflineAtomicOnlyPolicy, OfflineExactPolicy, OnlineRepairPolicy,
    PathOnlyPolicy, SafeStopPolicy, TemplateRepairPolicy,
)

METHODS = {
    "path_only": PathOnlyPolicy,
    "safe_stop": SafeStopPolicy,
    "template_repair": TemplateRepairPolicy,
    "offline_atomic": OfflineAtomicOnlyPolicy,
    "offline_exact": OfflineExactPolicy,
    "online_repair": OnlineRepairPolicy,
}
BASELINE = "online_repair"
METRICS = ("safe_delivery", "collision_free_recovery", "task_success")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--seeds", type=int, default=None)
    args = ap.parse_args()
    n_seeds = args.seeds if args.seeds else (8 if args.quick else 50)

    conditions = [c for c in CONDITIONS if c != "none"]
    specs = episode_grid(FAMILIES, conditions, SEVERITIES, n_seeds=n_seeds)
    n_eps = len(specs)
    print(f"Protocol: {len(FAMILIES)} families x {len(conditions)} conditions x "
          f"{len(SEVERITIES)} severities x {n_seeds} paired seeds = {n_eps} episodes/method")
    print(f"          {len(METHODS)} methods -> {n_eps * len(METHODS)} episodes total\n")

    results = run_grid(specs, METHODS)

    # --- overall proportions with Wilson CIs ------------------------------
    print("=" * 92)
    print("OVERALL (Wilson 95% CI).  SD=safe delivery  CFR=collision-free recovery  TS=task success")
    print("=" * 92)
    print(f"{'method':17} {'SD':>22} {'CFR':>22} {'TS':>22}")
    for m in METHODS:
        recs = results[m]
        cells = []
        for metric in METRICS:
            k = sum(1 for r in recs if getattr(r, metric))
            cells.append(ProportionSummary(m, k, len(recs)).fmt())
        print(f"{m:17} {cells[0]:>22} {cells[1]:>22} {cells[2]:>22}")

    # --- paired comparisons vs online -------------------------------------
    print("\n" + "=" * 92)
    print(f"PAIRED vs {BASELINE}: risk difference [bootstrap 95% CI], exact McNemar (Holm-adjusted)")
    print("=" * 92)
    for metric in METRICS:
        raw_p, rows = {}, {}
        base = [getattr(r, metric) for r in results[BASELINE]]
        for m in METHODS:
            if m == BASELINE:
                continue
            other = [getattr(r, metric) for r in results[m]]
            diff, lo, hi = paired_bootstrap_diff(
                [float(x) for x in other], [float(x) for x in base])
            b01, b10, p = mcnemar_exact(other, base)
            raw_p[m] = p
            rows[m] = (diff, lo, hi, b01, b10)
        adj = holm_correction(raw_p)
        print(f"\n-- {metric}")
        print(f"   {'method':17} {'online-other':>14} {'95% CI':>20} "
              f"{'disc(o+/o-)':>13} {'p_holm':>9}")
        for m, (diff, lo, hi, b01, b10) in rows.items():
            sig = "*" if adj[m] < 0.05 else " "
            print(f"   {m:17} {diff:+14.3f} [{lo:+.3f}, {hi:+.3f}] "
                  f"{b01:6d}/{b10:<6d} {adj[m]:9.4f}{sig}")

    # --- per-condition task success ---------------------------------------
    print("\n" + "=" * 92)
    print("SAFE DELIVERY by condition (rate)")
    print("=" * 92)
    by_cond = defaultdict(lambda: defaultdict(list))
    for m in METHODS:
        for r in results[m]:
            cond = r.spec_key.split("|")[1]
            by_cond[cond][m].append(r.safe_delivery)
    hdr = "".join(f"{m[:13]:>15}" for m in METHODS)
    print(f"{'condition':22}{hdr}")
    for cond in conditions:
        cells = "".join(f"{np.mean(by_cond[cond][m]):>15.3f}" for m in METHODS)
        print(f"{cond:22}{cells}")

    # --- cost / effort metrics --------------------------------------------
    print("\n" + "=" * 92)
    print("COST (means)")
    print("=" * 92)
    print(f"{'method':17} {'latency_ms':>11} {'repairs':>8} {'rep_len':>8} "
          f"{'cand_gen':>9} {'cand_rej':>9} {'expand':>8} {'branches':>9} "
          f"{'graph':>7} {'compile':>8}")
    for m in METHODS:
        recs = results[m]
        f = lambda k: np.mean([getattr(r, k) for r in recs])
        print(f"{m:17} {f('plan_latency_ms'):11.2f} {f('n_repairs'):8.2f} "
              f"{f('repair_len'):8.2f} {f('candidates_generated'):9.2f} "
              f"{f('candidates_rejected'):9.2f} {f('search_expansions'):8.2f} "
              f"{f('branch_count'):9.1f} {f('graph_size'):7.1f} {f('compile_ops'):8.1f}")

    print("\nNOTES")
    print(" * SD, CFR and TS are distinct. TS is the strict end-to-end criterion;")
    print("   SD ignores terminal orientation and the proximity-weighted spill bound.")
    print(" * latency_ms is WHOLE-EPISODE wall time and, for offline methods,")
    print("   INCLUDES the one-off precompilation done in reset(). In deployment")
    print("   that cost is amortized across episodes, so offline runtime selection")
    print("   is cheaper than this column suggests; compare 'compile' separately.")
    print(" * 'expand' (operator-search expansions) is the online-only search cost.")


if __name__ == "__main__":
    main()
