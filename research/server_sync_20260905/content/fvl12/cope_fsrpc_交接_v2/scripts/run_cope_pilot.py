#!/usr/bin/env python3
"""CoPE vs FSR-PC pilot on the basket-sorting benchmark.

Stages (the gate is a precondition, not a result):

  Stage A  nominal reliability gate --- >= 8/10 nominal success or STOP
  Stage B  paired comparison over the interruption conditions I1-I4
  Stage C  ablation: FSR-PC(preserve_ids), which isolates identity re-minting
           from regeneration itself

Everything here runs on CPU with a scripted mock executor. On the GPU host the
same script runs against the real executor; see docs/COPE_GPU_RUNBOOK.md for the
one integration point (the executor class) that has to be supplied there.

    python3 scripts/run_cope_pilot.py --seeds 5 --out results/cope_pilot
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
# In the repository the packages sit at ROOT; in the handoff package they sit
# under ROOT/code. Support both so this script runs unmodified in either.
for _p in (ROOT / "code", ROOT):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from cope.benchmark import BasketTaskSpec, ReliabilityGate, run_episode  # noqa: E402
from cope.benchmark.physical_episode import run_physical_episode  # noqa: E402
from cope.benchmark.backend_episode import run_backend_episode  # noqa: E402
from cope.repair_bridge import assert_complete  # noqa: E402
from rekep_repair.benchmark.statistics import (  # noqa: E402
    holm_correction, mcnemar_exact, paired_bootstrap_diff, wilson_interval,
)

CONDITIONS = ("I1", "I2", "I3", "I4")
PRIMARY = ("CoPE", "FSR-PC")
CONTROL = "no_adaptation"

#: The default is the PHYSICAL stack: legs are executed through the frozen
#: controllers inside Synthetic2DEnv, and every interruption drives the frozen
#: synthesis -> rollout-verification -> splice -> restore -> resume pipeline.
#: `--executor mock` keeps the v1 symbolic executor available for fast
#: semantic-only checks, but it does NOT exercise the repair engine.
RUNNERS = {"physical": run_physical_episode, "mock": run_episode}


def _run(spec, executor: str, **kw):
    fn = RUNNERS[executor]
    if executor == "physical":
        return fn(spec, **{k: v for k, v in kw.items()
                           if k in ("p_disturbance", "verbose")})
    return fn(spec, **{k: v for k, v in kw.items()
                       if k in ("p_success", "verbose")})


def _git_rev() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                       text=True).strip()
    except Exception:
        return "unknown"


# ----------------------------------------------------------------- Stage A
def stage_a(n_seeds: int, p_success: float, executor: str) -> Dict[str, Any]:
    gate = ReliabilityGate(n_seeds=n_seeds)
    per_seed = []
    for s in range(n_seeds):
        r = _run(BasketTaskSpec(seed=s, condition="nominal", method=CONTROL),
                 executor, p_success=p_success)
        per_seed.append({"seed": s,
                         "success": bool(r.metrics.revised_task_success),
                         "steps": r.metrics.completion_steps})
    successes = sum(x["success"] for x in per_seed)
    out = gate.evaluate(successes)
    out["per_seed"] = per_seed
    out["note"] = (
        "Run with the no-adaptation arm on the uninterrupted task, so the "
        "number measures the TASK and the EXECUTOR, not any adaptation method.")
    return out


# ----------------------------------------------------------------- Stage B
def stage_b(n_seeds: int, p_success: float, executor: str) -> Dict[str, Any]:
    episodes: List[Dict[str, Any]] = []
    for cond in CONDITIONS:
        for seed in range(n_seeds):
            for method in PRIMARY + (CONTROL,):
                r = _run(BasketTaskSpec(seed=seed, condition=cond,
                                        method=method),
                         executor, p_success=p_success)
                episodes.append(r.to_dict())
    return {"episodes": episodes,
            "analysis": analyse(episodes)}


def _series(episodes, method, field, cond=None):
    out = []
    for e in episodes:
        if e["method"] != method:
            continue
        if cond is not None and e["condition"] != cond:
            continue
        out.append((e["pairing_key"], e["metrics"][field]))
    return dict(out)


def analyse(episodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Paired analysis. Pairing is by `pairing_key`, which excludes the method."""
    binary = ["revised_task_success", "completed_progress_preserved",
              "remaining_goal_correct", "identity_preserved",
              "lifecycle_transitions_legal", "lineage_correct",
              "history_monotonic"]
    continuous = ["normalized_edit_distance", "slots_touched_per_event",
                  "completion_steps", "invalid_action_count",
                  "adaptation_latency_s", "audit_coverage",
                  # the repair engine actually ran, and ran identically
                  "repairs_invoked", "candidates_generated", "rollouts_run",
                  "splices", "restores_validated", "stages_resumed"]

    res: Dict[str, Any] = {"binary": {}, "continuous": {}, "per_condition": {}}
    pvals: Dict[str, float] = {}

    for f in binary:
        a = _series(episodes, "CoPE", f)
        b = _series(episodes, "FSR-PC", f)
        keys = sorted(set(a) & set(b))
        av = [bool(a[k]) for k in keys if a[k] is not None and b[k] is not None]
        bv = [bool(b[k]) for k in keys if a[k] is not None and b[k] is not None]
        if not av:
            res["binary"][f] = {"n": 0, "note": "not applicable in this pilot"}
            continue
        # helper returns (b01, b10): b01 = CoPE wrong & FSR-PC right,
        # b10 = CoPE right & FSR-PC wrong
        n01, n10, p = mcnemar_exact(av, bv)
        res["binary"][f] = {
            "n": len(av),
            "CoPE": {"k": sum(av), "rate": sum(av) / len(av),
                     "wilson95": wilson_interval(sum(av), len(av))},
            "FSR-PC": {"k": sum(bv), "rate": sum(bv) / len(bv),
                       "wilson95": wilson_interval(sum(bv), len(bv))},
            "discordant_FSRPC_only": n01, "discordant_CoPE_only": n10,
            "mcnemar_exact_p": p}
        pvals[f] = p

    for f in continuous:
        a = _series(episodes, "CoPE", f)
        b = _series(episodes, "FSR-PC", f)
        keys = sorted(k for k in set(a) & set(b)
                      if a[k] is not None and b[k] is not None)
        if not keys:
            res["continuous"][f] = {"n": 0, "note": "not applicable"}
            continue
        av = [float(a[k]) for k in keys]
        bv = [float(b[k]) for k in keys]
        # the helper returns mean(second) - mean(first); pass (FSR-PC, CoPE)
        # so the reported difference reads CoPE - FSR-PC
        diff, lo, hi = paired_bootstrap_diff(bv, av)
        res["continuous"][f] = {
            "n": len(keys),
            "CoPE_mean": sum(av) / len(av), "FSRPC_mean": sum(bv) / len(bv),
            "mean_diff_CoPE_minus_FSRPC": diff,
            "paired_bootstrap_95ci": [lo, hi],
            "excludes_zero": not (lo <= 0.0 <= hi)}

    res["holm_corrected_p"] = holm_correction(pvals) if pvals else {}

    for cond in CONDITIONS:
        row = {}
        for m in PRIMARY + (CONTROL,):
            s = _series(episodes, m, "revised_task_success", cond)
            vals = [bool(v) for v in s.values()]
            row[m] = {"success": sum(vals), "n": len(vals)}
        res["per_condition"][cond] = row
    return res


# ----------------------------------------------------------------- Stage C
def stage_c(n_seeds: int, p_success: float, executor: str) -> Dict[str, Any]:
    """Ablations that isolate the mechanism instead of arguing about it."""
    from cope.policies import METHODS
    from cope.policies.fsrpc_policy import FSRPCPolicy

    class FSRPCPreserveIds(FSRPCPolicy):
        """FSR-PC that also re-uses the previous slot ids.

        Isolates identity re-minting from regeneration itself: if the CoPE
        advantage survives this, it is not merely an id-bookkeeping artefact.
        """
        name = "FSR-PC(preserve_ids)"

        def __init__(self, store, horizon_steps=900, repair_engine=None):
            super().__init__(store, horizon_steps, repair_engine,
                             preserve_ids=True)

    METHODS["FSR-PC(preserve_ids)"] = FSRPCPreserveIds
    out: Dict[str, Any] = {"arms": {}}
    for m in ("CoPE", "FSR-PC", "FSR-PC(preserve_ids)"):
        rows = []
        for cond in CONDITIONS:
            for seed in range(n_seeds):
                r = _run(BasketTaskSpec(seed=seed, condition=cond, method=m),
                         executor, p_success=p_success)
                rows.append(r.to_dict())
        out["arms"][m] = {
            "n": len(rows),
            "success": sum(bool(r["metrics"]["revised_task_success"])
                           for r in rows),
            "identity_preserved": sum(bool(r["metrics"]["identity_preserved"])
                                      for r in rows),
            "mean_NED": sum(r["metrics"]["normalized_edit_distance"] or 0.0
                            for r in rows) / len(rows),
            "mean_audit_coverage": sum(r["metrics"]["audit_coverage"] or 0.0
                                       for r in rows) / len(rows)}
    return out


def _backend_episode_dir(root: Path, stage: str, condition: str,
                         seed: int, method: str) -> Path:
    safe_method = method.replace("/", "_").replace(" ", "_")
    # Real experiment roots are already stage-specific. Keep the required
    # per-episode layout directly below them: method / condition / seed.
    del stage
    return root / safe_method / condition / f"seed_{seed:02d}"


def run_real_backend_experiment(args) -> int:
    """Gated LIBERO run. Exactly 10 nominal + 60 paired pilot episodes."""

    if args.backend_config is None:
        raise SystemExit("--backend-config is required for a real backend")
    if args.out.exists():
        raise SystemExit(
            f"refusing to overwrite existing experiment directory: {args.out}"
        )
    args.out.mkdir(parents=True)
    meta = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "git_rev": _git_rev(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "backend": args.backend,
        "backend_config": str(args.backend_config.resolve()),
        "gate_seeds": args.gate_seeds,
        "pilot_seeds": args.seeds,
        "controller_privilege": "simulator_geometry_oracle",
        "learned_policy_used": False,
        "evidence_stratum": "mechanism",
    }
    _write = lambda path, value: path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    if args.stage == "pilot":
        if args.gate_report is None:
            raise SystemExit("--stage pilot requires --gate-report")
        gate_payload = json.loads(args.gate_report.read_text(encoding="utf-8"))
        gate = gate_payload["gate"]
        if not gate.get("passed"):
            raise SystemExit(f"gate report did not pass: {args.gate_report}")
        meta["gate_report"] = str(args.gate_report.resolve())
    else:
        gate_rows = []
        for seed in range(args.gate_seeds):
            result = run_backend_episode(
                BasketTaskSpec(seed=seed, condition="nominal", method=CONTROL),
                backend_name=args.backend,
                backend_config=args.backend_config,
                episode_dir=_backend_episode_dir(
                    args.out, "stage_a_nominal", "nominal", seed, CONTROL
                ),
                verbose=args.verbose,
            )
            gate_rows.append(result)
            print(
                f"nominal seed={seed}: "
                f"success={result['metrics']['revised_task_success']} "
                f"valid={result['denominators']['valid_episodes']}",
                flush=True,
            )
        gate_valid = [
            row for row in gate_rows if row["denominators"]["valid_episodes"] == 1
        ]
        gate_successes = sum(
            bool(row["metrics"]["revised_task_success"]) for row in gate_valid
        )
        gate = {
            "attempted": len(gate_rows),
            "valid": len(gate_valid),
            "successes": gate_successes,
            "threshold": 8,
            "passed": len(gate_valid) == args.gate_seeds and gate_successes >= 8,
            "per_seed": [
                {
                    "seed": row["seed"],
                    "success": row["metrics"]["revised_task_success"],
                    "valid": row["denominators"]["valid_episodes"],
                    "steps": row["metrics"]["completion_steps"],
                    "episode_dir": str(
                        _backend_episode_dir(
                            args.out,
                            "stage_a_nominal",
                            "nominal",
                            row["seed"],
                            CONTROL,
                        )
                    ),
                }
                for row in gate_rows
            ],
        }
        _write(args.out / "stage_a_nominal_gate.json", {"meta": meta, "gate": gate})
        print(
            f"Stage A real nominal gate: {gate_successes}/{len(gate_valid)} valid "
            f"({len(gate_rows)} attempted) -> {'PASS' if gate['passed'] else 'STOP'}",
            flush=True,
        )
        if not gate["passed"]:
            return 1
        if args.stage == "gate":
            return 0

    pilot_rows: List[Dict[str, Any]] = []
    for condition in CONDITIONS:
        for seed in range(args.seeds):
            for method in PRIMARY + (CONTROL,):
                result = run_backend_episode(
                    BasketTaskSpec(seed=seed, condition=condition, method=method),
                    backend_name=args.backend,
                    backend_config=args.backend_config,
                    episode_dir=_backend_episode_dir(
                        args.out, "stage_b_pilot", condition, seed, method
                    ),
                    verbose=args.verbose,
                )
                pilot_rows.append(result)
                print(
                    f"pilot {condition} seed={seed} method={method}: "
                    f"success={result['metrics']['revised_task_success']} "
                    f"valid={result['denominators']['valid_episodes']}",
                    flush=True,
                )
    valid_rows = [
        row for row in pilot_rows if row["denominators"]["valid_episodes"] == 1
    ]
    summary = {
        "meta": meta,
        "denominators": {
            "attempted_episodes": len(pilot_rows),
            "valid_episodes": len(valid_rows),
            "attempted_candidates": sum(
                row["denominators"]["attempted_candidates"] for row in pilot_rows
            ),
            "evaluated_candidates": sum(
                row["denominators"]["evaluated_candidates"] for row in pilot_rows
            ),
            "valid_candidates": sum(
                row["denominators"]["valid_candidates"] for row in pilot_rows
            ),
            "accepted_candidates": sum(
                row["denominators"]["accepted_candidates"] for row in pilot_rows
            ),
            "rejected_candidates": sum(
                row["denominators"]["rejected_candidates"] for row in pilot_rows
            ),
        },
        "analysis": analyse(valid_rows),
        "episodes": [
            {
                "episode_id": row["episode_id"],
                "pairing_key": row["pairing_key"],
                "condition": row["condition"],
                "seed": row["seed"],
                "method": row["method"],
                "metrics": row["metrics"],
                "task_metrics": row["task_metrics"],
                "denominators": row["denominators"],
            }
            for row in pilot_rows
        ],
    }
    _write(args.out / "stage_b_paired_pilot.json", summary)
    print(
        f"Stage B real pilot: {len(valid_rows)}/{len(pilot_rows)} valid episodes",
        flush=True,
    )
    return 0 if len(valid_rows) == len(pilot_rows) else 1


# ----------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=5,
                    help="paired seeds per condition (Stage B/C)")
    ap.add_argument("--gate-seeds", type=int, default=10)
    ap.add_argument("--p-success", type=float, default=0.97,
                    help="CPU mock per-primitive success probability")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "cope_pilot")
    ap.add_argument("--executor", choices=list(RUNNERS), default="physical",
                    help="physical = frozen execution+repair stack (default); "
                         "mock = v1 symbolic executor, semantic checks only")
    ap.add_argument("--backend", default="synthetic2d",
                    help="synthetic2d or an installed real backend name, e.g. "
                         "libero_mujoco")
    ap.add_argument("--backend-config", type=Path,
                    help="backend configuration YAML; required for real backends")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--stage", choices=("gate", "pilot", "all"), default="all",
                    help="real backend only: stop after gate, run pilot from a "
                         "passed report, or run both")
    ap.add_argument("--gate-report", type=Path,
                    help="passed stage_a_nominal_gate.json for --stage pilot")
    ap.add_argument("--skip-gate", action="store_true",
                    help="run Stage B even if the gate fails (diagnostics only)")
    args = ap.parse_args()

    if args.backend != "synthetic2d":
        return run_real_backend_experiment(args)

    args.out.mkdir(parents=True, exist_ok=True)
    meta = {"utc": datetime.now(timezone.utc).isoformat(),
            "git_rev": _git_rev(), "python": sys.version.split()[0],
            "platform": platform.platform(),
            "executor": args.executor,
            "p_success": args.p_success, "seeds": args.seeds,
            "gate_seeds": args.gate_seeds}

    a = stage_a(args.gate_seeds, args.p_success, args.executor)
    (args.out / "stage_a_reliability.json").write_text(
        json.dumps({"meta": meta, "gate": a}, indent=2))
    print(f"Stage A: {a['successes']}/{a['n_seeds']} -> {a['verdict']}")
    if not a["passed"] and not args.skip_gate:
        print("Gate failed. Not running the method comparison. "
              "Change or simplify the task, do not tune the methods.")
        return 1

    b = stage_b(args.seeds, args.p_success, args.executor)
    (args.out / "stage_b_paired.json").write_text(
        json.dumps({"meta": meta, **b}, indent=2, default=str))
    c = stage_c(args.seeds, args.p_success, args.executor)
    (args.out / "stage_c_ablations.json").write_text(
        json.dumps({"meta": meta, **c}, indent=2, default=str))

    an = b["analysis"]
    print(f"\nStage B: {len(b['episodes'])} episodes "
          f"({args.seeds} seeds x {len(CONDITIONS)} conditions x 3 arms)")
    for f, v in an["binary"].items():
        if v.get("n"):
            print(f"  {f:32s} CoPE {v['CoPE']['k']}/{v['n']}  "
                  f"FSR-PC {v['FSR-PC']['k']}/{v['n']}  "
                  f"p={v['mcnemar_exact_p']:.4f}")
    for f, v in an["continuous"].items():
        if v.get("n"):
            lo, hi = v["paired_bootstrap_95ci"]
            print(f"  {f:32s} CoPE {v['CoPE_mean']:.3f}  "
                  f"FSR-PC {v['FSRPC_mean']:.3f}  "
                  f"diff 95%CI [{lo:.3f}, {hi:.3f}]"
                  f"{'  *' if v['excludes_zero'] else ''}")
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
