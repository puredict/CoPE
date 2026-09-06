"""Deliverable 3: targeted counterfactuals for the null mechanisms (B1).

Quantifies, across many paired seeds, WHY each null mechanism is null:

* NoStateDependentScoring -- how often is there more than one surviving
  candidate?  If selection is almost always forced, scoring cannot matter.
* NoEventComposition      -- how often does the reduced goal change the plan?
  And when it does not, is that because the rollout independently rejects the
  incomplete plan (composition redundant given verification)?
* NoRestoreGate           -- how often does the gate actually reject?

Run:  python scripts/mechanism_identification.py [--seeds N]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from collections import Counter

import numpy as np

from rekep_repair.benchmark import CONDITIONS, FAMILIES, SEVERITIES, episode_grid, sample_scene
from rekep_repair.benchmark.mismatch import LEVELS, MismatchedEnv
from rekep_repair.benchmark.probe import instrument
from rekep_repair.execution.executor import Executor
from rekep_repair.policies import OnlineRepairPolicy
from rekep_repair.policies.ablations import (
    NoEventCompositionPolicy, NoRestoreGatePolicy, NoStateDependentScoringPolicy,
)
from rekep_repair.synthetic.env import Synthetic2DEnv

COMPOUND = ("obstacle+slip", "obstacle+relocation", "slip+relocation")


def run(spec, factory, level="none"):
    cfg = sample_scene(spec)
    base = Synthetic2DEnv(cfg, seed=spec.seed)
    env = base if level == "none" else MismatchedEnv(base, LEVELS[level], seed=spec.seed)
    pol = factory()
    pol.reset(env)
    act = instrument(pol)
    rep = Executor(env).run(pol).report()
    return act, rep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=25)
    args = ap.parse_args()

    conds = [c for c in CONDITIONS if c != "none"]
    specs = episode_grid(FAMILIES, conds, SEVERITIES, n_seeds=args.seeds)
    comp_specs = [s for s in specs if s.condition in COMPOUND]

    # ---------- M1: state-dependent scoring -------------------------------
    print("=" * 92)
    print("M1  NoStateDependentScoring -- is selection ever contested?")
    print("=" * 92)
    surv = Counter()
    changed = 0
    n_dec = 0
    for spec in specs:
        full, _ = run(spec, OnlineRepairPolicy)
        abl, _ = run(spec, NoStateDependentScoringPolicy)
        for a in full.activations:
            surv[len(a.survived)] += 1
            n_dec += 1
        if full.selections() != abl.selections():
            changed += 1
    print(f"  repair decisions observed          : {n_dec}")
    print(f"  surviving-candidate count histogram: {dict(sorted(surv.items()))}")
    contested = sum(v for k, v in surv.items() if k > 1)
    print(f"  decisions with >1 candidate        : {contested} "
          f"({contested/max(1,n_dec):.1%})")
    print(f"  episodes where selection changed   : {changed}/{len(specs)}")
    print("  => if selection is almost never contested, scoring cannot matter.")

    # ---------- M2: event composition -------------------------------------
    print("\n" + "=" * 92)
    print("M2  NoEventComposition -- does the reduced goal change anything? (COMPOUND only)")
    print("=" * 92)
    goal_diff = plan_diff = sel_diff = out_diff = 0
    rej_full = rej_abl = 0
    exp_full = exp_abl = 0
    for spec in comp_specs:
        full, frep = run(spec, OnlineRepairPolicy)
        abl, arep = run(spec, NoEventCompositionPolicy)
        goal_diff += full.goals() != abl.goals()
        plan_diff += full.plans() != abl.plans()
        sel_diff += full.selections() != abl.selections()
        out_diff += (frep["safe_delivery"], frep["task_success"]) != \
                    (arep["safe_delivery"], arep["task_success"])
        rej_full += sum(len(a.rejected) for a in full.activations)
        rej_abl += sum(len(a.rejected) for a in abl.activations)
        exp_full += sum(a.explored_states for a in full.activations)
        exp_abl += sum(a.explored_states for a in abl.activations)
    n = len(comp_specs)
    print(f"  compound episodes                  : {n}")
    print(f"  RepairGoal differs                 : {goal_diff}/{n}  <- ablation IS active")
    print(f"  synthesized plans differ           : {plan_diff}/{n}")
    print(f"  selected candidate differs         : {sel_diff}/{n}")
    print(f"  OUTCOME differs                    : {out_diff}/{n}")
    print(f"  candidate rejections  full/ablated : {rej_full} / {rej_abl}")
    print(f"  search expansions     full/ablated : {exp_full} / {exp_abl}")
    print("  => goal changes but outcome does not => composition is a REPRESENTATION/")
    print("     EFFICIENCY mechanism here, not a success-rate mechanism.")

    # ---------- M3: restore gate ------------------------------------------
    print("\n" + "=" * 92)
    print("M3  NoRestoreGate -- does the gate ever reject? (nominal vs severe mismatch)")
    print("=" * 92)
    for level in ("none", "moderate", "severe"):
        rejects = total = 0
        out_diff = 0
        sub = specs[: min(len(specs), 200)]
        for spec in sub:
            full, frep = run(spec, OnlineRepairPolicy, level)
            abl, arep = run(spec, NoRestoreGatePolicy, level)
            rejects += sum(1 for v in full.restore_validations if not v)
            total += len(full.restore_validations)
            out_diff += (frep["safe_delivery"] != arep["safe_delivery"])
        print(f"  {level:9} gate rejections {rejects:4d}/{total:4d} "
              f"({rejects/max(1,total):.1%})   outcome differs {out_diff}/{len(sub)}")
    print("  => if the gate never rejects, Realign already guarantees the handoff and")
    print("     the gate is a SAFETY INVARIANT, not a success-rate mechanism.")


if __name__ == "__main__":
    main()
