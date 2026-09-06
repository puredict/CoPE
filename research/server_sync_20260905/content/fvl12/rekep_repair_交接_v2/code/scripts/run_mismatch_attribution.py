"""Track A: per-dimension model-mismatch attribution (CPU-only).

Each mismatch source is enabled ALONE at none/mild/moderate/severe, with paired
randomized episodes, so its individual contribution can be attributed.  The
verifier architecture is unchanged (nominal sequential rollout) -- this study
attributes damage, it does not propose a new verifier.

Metrics per (source, level): verifier false-accept / false-reject rate,
collision rate, event-resolution rate, handoff error, safe delivery, task
success.

Usage:
  python scripts/run_mismatch_attribution.py --quick     # 6 seeds
  python scripts/run_mismatch_attribution.py            # 25 seeds
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import json
from collections import defaultdict

import numpy as np

from rekep_repair.benchmark import (
    CONDITIONS, FAMILIES, SEVERITIES, episode_grid, sample_scene,
)
from rekep_repair.benchmark.mismatch import (
    LEVEL_ORDER, MismatchConfig, MismatchedEnv, SOURCES, single_source,
)
from rekep_repair.execution.executor import Executor
from rekep_repair.policies.verified_repair import VerifiedRepairPolicy
from rekep_repair.synthetic.env import Synthetic2DEnv


def run_one(spec, mm):
    cfg = sample_scene(spec)
    env = MismatchedEnv(Synthetic2DEnv(cfg, seed=spec.seed), mm, seed=spec.seed)
    pol = VerifiedRepairPolicy("nominal")
    rep = Executor(env).run(pol).report()
    accepted = bool(getattr(pol, "accepted_any", False))
    # event resolved == repair completed without routing to safe fallback
    resolved = (not rep["failed_safe"]) and (pol.program._repair_counter > 0)
    return {
        "accepted": accepted,
        "sd": bool(rep["safe_delivery"]),
        "ts": bool(rep["task_success"]),
        "collided": bool(rep["collided"]),
        "failed_safe": bool(rep["failed_safe"]),
        "resolved": bool(resolved) or (pol.program._repair_counter == 0),
        "handoff": float(rep["goal_error"]),
    }


def summarize(rows, baseline_sd):
    n = len(rows)
    acc = [r for r in rows if r["accepted"]]
    rej = [r for r in rows if not r["accepted"]]
    fa = sum(1 for r in acc if not r["sd"])
    fr = sum(1 for i, r in enumerate(rej) if baseline_sd[i])
    return {
        "FA": fa / len(acc) if acc else 0.0,
        "FR": fr / len(rej) if rej else 0.0,
        "collide": np.mean([r["collided"] for r in rows]),
        "resolve": np.mean([r["resolved"] for r in rows]),
        "handoff": np.mean([r["handoff"] for r in rows]),
        "SD": np.mean([r["sd"] for r in rows]),
        "TS": np.mean([r["ts"] for r in rows]),
        "n": n,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--json", type=str, default=None)
    args = ap.parse_args()
    n_seeds = args.seeds if args.seeds else (6 if args.quick else 25)

    conds = [c for c in CONDITIONS if c != "none"]
    specs = episode_grid(FAMILIES, conds, SEVERITIES, n_seeds=n_seeds)
    total = len(specs) * (1 + len(SOURCES) * 3)
    print(f"Per-dimension attribution: {len(specs)} paired episodes x "
          f"({len(SOURCES)} sources x 3 levels + baseline) = ~{total} episodes")
    print("Verifier: nominal sequential rollout (unchanged).\n")

    # baseline (all nominal) -- also the reference for the false-reject metric
    base_rows = [run_one(s, MismatchConfig()) for s in specs]
    base_sd = [r["sd"] for r in base_rows]
    base = summarize(base_rows, base_sd)
    print(f"{'source':22} {'level':9} {'FA':>7} {'FR':>7} {'collide':>8} "
          f"{'resolve':>8} {'handoff':>8} {'SD':>7} {'TS':>7}")
    print("-" * 92)
    print(f"{'(none)':22} {'baseline':9} {base['FA']:7.3f} {base['FR']:7.3f} "
          f"{base['collide']:8.3f} {base['resolve']:8.3f} {base['handoff']:8.3f} "
          f"{base['SD']:7.3f} {base['TS']:7.3f}")

    out = {"baseline": base}
    damage = {}
    for src in SOURCES:
        print()
        for lvl in ("mild", "moderate", "severe"):
            mm = single_source(src, lvl)
            if mm == MismatchConfig():
                continue                      # level is a no-op for this source
            rows = [run_one(s, mm) for s in specs]
            st = summarize(rows, base_sd)
            out[f"{src}|{lvl}"] = st
            print(f"{src:22} {lvl:9} {st['FA']:7.3f} {st['FR']:7.3f} "
                  f"{st['collide']:8.3f} {st['resolve']:8.3f} {st['handoff']:8.3f} "
                  f"{st['SD']:7.3f} {st['TS']:7.3f}")
            if lvl == "severe":
                damage[src] = {
                    "dSD": base["SD"] - st["SD"],
                    "dFA": st["FA"] - base["FA"],
                    "dCol": st["collide"] - base["collide"],
                }

    # --- ranking ----------------------------------------------------------
    print("\n" + "=" * 92)
    print("DAMAGE RANKING at SEVERE (drop in safe delivery vs nominal baseline)")
    print("=" * 92)
    print(f"{'rank':5} {'source':24} {'dSD':>9} {'dFA':>9} {'dCollide':>10}")
    ranked = sorted(damage.items(), key=lambda kv: -kv[1]["dSD"])
    for i, (src, d) in enumerate(ranked, 1):
        print(f"{i:<5} {src:24} {d['dSD']:+9.3f} {d['dFA']:+9.3f} {d['dCol']:+10.3f}")

    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2, default=float))
        print(f"\nwrote {args.json}")

    print("\nNOTE: 'FR' is measured against the all-nominal baseline outcome, so it")
    print("counts episodes the verifier rejected that the nominal run solved.")


if __name__ == "__main__":
    main()
