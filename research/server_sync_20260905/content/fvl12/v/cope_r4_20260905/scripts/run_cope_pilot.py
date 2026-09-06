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
#: Stage D (diagnostic) explores lineage-sensitive and restoration conditions
DIAGNOSTIC_CONDITIONS = ("I3", "I4", "I5")
#: Stage D arms: decompose the audit advantage, and test the verifier mechanism
DIAGNOSTIC_METHODS = ("CoPE", "FSR-PC", "FSR-PC_stable_ids", "FSR-PC_provenance")
VERIFIER_METHODS = ("CoPE_full", "CoPE_no_rollout_verification")
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


REAL_EPISODE_ARTIFACTS = (
    "result.json", "events.jsonl", "interruptions.jsonl",
    "adaptation_trace.jsonl", "repair_trace.jsonl",
    "candidate_rollouts.jsonl", "state_snapshots.json", "simulator.log",
    "video.mp4",
)


def _load_complete_real_result(episode_dir: Path, *, condition: str,
                               seed: int, method: str):
    """Return a strictly matching completed result, otherwise ``None``.

    Long real-simulator pilots may outlive an SSH transport.  Resume is safe
    only when the full evidence bundle is already present and the result's
    registered arm matches the matrix cell being resumed.
    """
    missing = [name for name in REAL_EPISODE_ARTIFACTS
               if not (episode_dir / name).is_file()]
    if missing:
        return None
    try:
        result = json.loads(
            (episode_dir / "result.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    try:
        registered_seed = int(result.get("seed", -1))
    except (TypeError, ValueError):
        return None
    if (result.get("condition") != condition
            or registered_seed != seed
            or result.get("method") != method
            or result.get("denominators", {}).get("completed_episodes") != 1):
        return None
    return result


def _preserve_incomplete_episode(episode_dir: Path) -> Path:
    """Rename, never delete or overwrite, an interrupted episode directory."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archived = episode_dir.with_name(f"{episode_dir.name}.interrupted-{stamp}")
    ordinal = 1
    while archived.exists():
        archived = episode_dir.with_name(
            f"{episode_dir.name}.interrupted-{stamp}-{ordinal}")
        ordinal += 1
    episode_dir.rename(archived)
    return archived


def _real_meta(args, *, conditions=(), methods=()) -> Dict[str, Any]:
    return {
        "utc": datetime.now(timezone.utc).isoformat(),
        "git_rev": _git_rev(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "backend": args.backend,
        "backend_config": str(args.backend_config.resolve()),
        "stage": args.stage,
        "conditions": list(conditions),
        "methods": list(methods),
        "seeds": list(range(args.seeds)),
        "gate_seeds": list(range(args.gate_seeds)),
        "controller_privilege": "simulator_geometry_oracle",
        "learned_policy_used": False,
        "rendering": "CPU OSMesa",
        "gpu_compute_used": False,
        "evidence_stratum": "mechanism",
    }


def _real_denominators(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    keys = (
        "attempted_episodes", "completed_episodes", "valid_episodes",
        "evaluable_episodes", "all_events_delivered_episodes",
        "adaptation_valid_episodes", "controller_valid_episodes",
        "final_task_successes", "attempted_candidates",
        "evaluated_candidates", "valid_candidates", "accepted_candidates",
        "rejected_candidates", "events_scheduled", "events_delivered",
    )
    return {
        key: sum(int(row.get("denominators", {}).get(key, 0)) for row in rows)
        for key in keys
    }


def _paired_fairness(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Recompute fairness evidence for every adaptive pair.

    Every comparison freezes exogenous inputs at every event and the complete
    pre-treatment packet. Later simulator/task histories are downstream of the
    compared task-state update or verifier decision, so equality there is an
    outcome rather than a precondition. Requiring it would erase the causal
    effect the experiment is designed to measure.
    """
    grouped: Dict[tuple, List[Dict[str, Any]]] = {}
    for row in rows:
        if row["method"] == CONTROL:
            continue
        grouped.setdefault((row["condition"], row["seed"]), []).append(row)
    out = []
    for (condition, seed), pair in sorted(grouped.items()):
        def same(field: str) -> bool:
            return len({json.dumps(row.get(field), sort_keys=True, default=str)
                        for row in pair}) == 1

        schedule_fingerprints = {
            row.get("schedule", {}).get("schedule_fingerprint") for row in pair
        }
        record = {
            "condition": condition,
            "seed": seed,
            "methods": sorted(row["method"] for row in pair),
            "same_backend_config": same("backend_config_sha256"),
            "same_initial_simulator_state": same(
                "initial_simulator_state_hash"),
            "same_registered_schedule": len(schedule_fingerprints) == 1,
            "same_fairness_fingerprint": same("fairness_fingerprint"),
        }
        first_inputs = {
            tuple(row.get("adaptation_input_fingerprints", [])[:1])
            for row in pair
        }
        first_requirements = {
            tuple(row.get("requirement_fingerprints", [])[:1])
            for row in pair
        }
        first_candidates = {
            tuple((row.get("repair_outcomes", [{}])[0]
                   if row.get("repair_outcomes") else {})
                  .get("candidate_names", []))
            for row in pair
        }
        budgets = {
            row.get("fairness_payload", {}).get(
                "candidate_horizon_steps") for row in pair
        }
        record.update({
            "same_exogenous_adaptation_inputs": same(
                "exogenous_adaptation_fingerprints"),
            "same_pre_treatment_adaptation_input": (
                len(first_inputs) == 1 and bool(next(iter(first_inputs)))),
            "same_pre_treatment_compiled_repair_goal": (
                len(first_requirements) == 1
                and bool(next(iter(first_requirements)))),
            "same_pre_treatment_candidate_set": (
                len(first_candidates) == 1
                and bool(next(iter(first_candidates)))),
            "same_candidate_budget": len(budgets) == 1 and None not in budgets,
            "post_treatment_adaptation_inputs_equal": same(
                "adaptation_input_fingerprints"),
            "post_treatment_compiled_repair_goals_equal": same(
                "requirement_fingerprints"),
        })
        record["passed"] = all(
            value for key, value in record.items() if key.startswith("same_")
        )
        out.append(record)
    return out


def _run_real_matrix(args, conditions, methods, summary_name: str) -> int:
    args.out.mkdir(parents=True, exist_ok=args.resume)
    rows: List[Dict[str, Any]] = []
    missing_artifacts: List[Dict[str, Any]] = []
    resumed_completed = 0
    preserved_incomplete_episode_dirs: List[str] = []
    for condition in conditions:
        for seed in range(args.seeds):
            for method in methods:
                episode_dir = _backend_episode_dir(
                    args.out, args.stage, condition, seed, method)
                result = None
                if args.resume and episode_dir.exists():
                    result = _load_complete_real_result(
                        episode_dir, condition=condition, seed=seed,
                        method=method)
                    if result is not None:
                        resumed_completed += 1
                        print(
                            f"resume {args.stage} {condition} seed={seed} "
                            f"method={method}: complete artifact bundle reused",
                            flush=True,
                        )
                    else:
                        archived = _preserve_incomplete_episode(episode_dir)
                        preserved_incomplete_episode_dirs.append(str(archived))
                        print(
                            f"resume {args.stage} {condition} seed={seed} "
                            f"method={method}: incomplete bundle preserved at "
                            f"{archived}", flush=True,
                        )
                if result is None:
                    result = run_backend_episode(
                        BasketTaskSpec(seed=seed, condition=condition,
                                       method=method),
                        backend_name=args.backend,
                        backend_config=args.backend_config,
                        episode_dir=episode_dir,
                        verbose=args.verbose,
                    )
                result["episode_dir"] = str(episode_dir)
                rows.append(result)
                missing = [name for name in REAL_EPISODE_ARTIFACTS
                           if not (episode_dir / name).is_file()]
                if missing:
                    missing_artifacts.append({
                        "episode_id": result["episode_id"], "missing": missing})
                print(
                    f"{args.stage} {condition} seed={seed} method={method}: "
                    f"success={result['metrics']['revised_task_success']} "
                    f"layer={result['layers']['failure_layer']} "
                    f"events={result['denominators']['events_delivered']}/"
                    f"{result['denominators']['events_scheduled']}",
                    flush=True,
                )

    expected = len(conditions) * args.seeds * len(methods)
    causal_ablation = set(methods) == set(VERIFIER_METHODS)
    fairness = _paired_fairness(rows)
    adaptive_rows = [row for row in rows if row["method"] != CONTROL]
    acceptance = {
        "attempt_count_exact": len(rows) == expected,
        "all_results_completed": all(
            row["denominators"].get("completed_episodes") == 1 for row in rows),
        "all_required_artifacts_present": not missing_artifacts,
        "all_interruption_events_delivered": all(
            row["denominators"].get("all_events_delivered_episodes") == 1
            for row in rows),
        "failure_layers_present": all(
            bool(row.get("layers", {}).get("failure_layer")) for row in rows),
        "repair_pipelines_complete_or_classified": all(
            all(outcome.get("pipeline_complete", False)
                for outcome in row.get("repair_outcomes", []))
            or row.get("layers", {}).get("failure_layer") != "none"
            for row in adaptive_rows),
        "paired_fairness_passed": all(row["passed"] for row in fairness),
    }
    per_arm: Dict[str, Dict[str, int]] = {}
    for row in rows:
        key = f"{row['method']}|{row['condition']}"
        rec = per_arm.setdefault(key, {
            "attempted": 0, "valid": 0, "all_events_delivered": 0,
            "adaptation_valid": 0, "controller_valid": 0,
            "task_success": 0, "infrastructure_failures": 0,
            "adaptation_failures": 0, "controller_failures": 0})
        rec["attempted"] += 1
        den = row["denominators"]
        rec["valid"] += int(den.get("valid_episodes", 0))
        rec["all_events_delivered"] += int(
            den.get("all_events_delivered_episodes", 0))
        rec["adaptation_valid"] += int(
            den.get("adaptation_valid_episodes", 0))
        rec["controller_valid"] += int(
            den.get("controller_valid_episodes", 0))
        rec["task_success"] += int(den.get("final_task_successes", 0))
        rec["infrastructure_failures"] += int(
            row["layers"].get("infrastructure_failure", False))
        rec["adaptation_failures"] += int(
            row["layers"].get("adaptation_failure", False))
        rec["controller_failures"] += int(
            row["layers"].get("controller_failure", False))

    meta = _real_meta(args, conditions=conditions, methods=methods)
    meta.update({
        "resume_requested": bool(args.resume),
        "resumed_completed_episodes": resumed_completed,
        "preserved_incomplete_episode_dirs":
            preserved_incomplete_episode_dirs,
        "fairness_protocol": (
            "all_event_exogenous_plus_pre_treatment_causal_pairing"),
        "comparison_kind": (
            "verifier_ablation" if causal_ablation else "task_state_update"),
    })
    summary = {
        "meta": meta,
        "denominators": _real_denominators(rows),
        "acceptance": acceptance,
        "paired_fairness": fairness,
        "per_method_condition": per_arm,
        "missing_artifacts": missing_artifacts,
        "analysis_primary": analyse([
            row for row in rows
            if row["method"] in PRIMARY and
            row["denominators"].get("evaluable_episodes") == 1]),
        "episodes": [{
            "episode_id": row["episode_id"],
            "episode_dir": row["episode_dir"],
            "pairing_key": row["pairing_key"],
            "condition": row["condition"], "seed": row["seed"],
            "method": row["method"], "layers": row["layers"],
            "metrics": row["metrics"], "denominators": row["denominators"],
            "fairness_fingerprint": row.get("fairness_fingerprint"),
            "adaptation_input_fingerprints": row.get(
                "adaptation_input_fingerprints", []),
            "exogenous_adaptation_fingerprints": row.get(
                "exogenous_adaptation_fingerprints", []),
            "requirement_fingerprints": row.get(
                "requirement_fingerprints", []),
        } for row in rows],
    }
    (args.out / summary_name).write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8")
    print(f"Wrote {args.out / summary_name}", flush=True)
    for key, value in acceptance.items():
        print(f"  {key}: {value}", flush=True)
    return 0 if all(acceptance.values()) else 1


def _run_real_controller_gate(args) -> int:
    args.out.mkdir(parents=True)
    rows: List[Dict[str, Any]] = []
    missing_artifacts: List[Dict[str, Any]] = []
    per_object = {
        obj: {"attempts": 0, "grasp_successes": 0,
              "placement_attempts": 0, "placement_successes": 0,
              "failure_reasons": {}}
        for obj in ("milk", "yogurt", "butter")
    }
    for seed in range(args.gate_seeds):
        episode_dir = _backend_episode_dir(
            args.out, args.stage, "nominal", seed, CONTROL)
        row = run_backend_episode(
            BasketTaskSpec(seed=seed, condition="nominal", method=CONTROL),
            backend_name=args.backend, backend_config=args.backend_config,
            episode_dir=episode_dir, verbose=args.verbose)
        row["episode_dir"] = str(episode_dir)
        rows.append(row)
        missing = [name for name in REAL_EPISODE_ARTIFACTS
                   if not (episode_dir / name).is_file()]
        if missing:
            missing_artifacts.append({
                "episode_id": row["episode_id"], "missing": missing})
        for leg in row.get("legs", []):
            obj = leg.get("object")
            if obj not in per_object:
                continue
            rec = per_object[obj]
            rec["attempts"] += 1
            pick = leg.get("pick", {}) or {}
            rec["grasp_successes"] += int(bool(pick.get("success")))
            if "placement" in leg:
                rec["placement_attempts"] += 1
                rec["placement_successes"] += int(bool(leg.get("placed")))
            reason = (leg.get("failure_reason")
                      or pick.get("failure_reason")
                      or (leg.get("placement", {}) or {}).get("failure_reason"))
            if reason:
                rec["failure_reasons"][str(reason)] = (
                    rec["failure_reasons"].get(str(reason), 0) + 1)
        print(
            f"nominal seed={seed}: "
            f"success={row['metrics']['revised_task_success']} "
            f"layer={row['layers']['failure_layer']}", flush=True)

    for rec in per_object.values():
        rec["grasp_rate"] = rec["grasp_successes"] / max(1, rec["attempts"])
        rec["placement_rate"] = (
            rec["placement_successes"] / max(1, rec["placement_attempts"]))
    den = _real_denominators(rows)
    weakest_grasp_rate = min(rec["grasp_rate"] for rec in per_object.values())
    passed = (
        len(rows) == args.gate_seeds
        and den["valid_episodes"] == args.gate_seeds
        and den["final_task_successes"] >= 8
        and all(rec["attempts"] == args.gate_seeds for rec in per_object.values())
        and weakest_grasp_rate >= 0.9
        and not missing_artifacts
    )
    report = {
        "meta": _real_meta(args, conditions=("nominal",), methods=(CONTROL,)),
        "denominators": den,
        "threshold": {"episode_successes": 8, "per_object_grasp_rate": 0.9},
        "per_object": per_object,
        "weakest_grasp_rate": weakest_grasp_rate,
        "missing_artifacts": missing_artifacts,
        "passed": passed,
        "per_seed": [{
            "seed": row["seed"], "episode_dir": row["episode_dir"],
            "success": row["metrics"]["revised_task_success"],
            "failure_layer": row["layers"]["failure_layer"],
        } for row in rows],
    }
    path = args.out / "stage_a_controller_gate.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    print(
        f"Controller gate: {den['final_task_successes']}/{args.gate_seeds}; "
        f"weakest grasp={weakest_grasp_rate:.3f} -> "
        f"{'PASS' if passed else 'STOP'}", flush=True)
    return 0 if passed else 1


def _run_real_r2_stage(args) -> int:
    if args.backend_config is None:
        raise SystemExit("--backend-config is required for a real backend")
    if args.out.exists() and not args.resume:
        raise SystemExit(
            f"refusing to overwrite existing experiment directory: {args.out}")
    conditions = tuple(args.conditions.split(",")) if args.conditions else None
    methods = tuple(args.methods.split(",")) if args.methods else None
    if args.stage == "controller_gate":
        if args.resume:
            raise SystemExit("--resume is supported for real matrix stages only")
        return _run_real_controller_gate(args)
    if args.stage == "regression_pilot":
        return _run_real_matrix(
            args, conditions or CONDITIONS,
            methods or (PRIMARY + (CONTROL,)),
            "stage_b_regression_pilot.json")
    if args.stage in ("diagnostic_pilot", "verifier_probe"):
        selected_methods = methods or (
            VERIFIER_METHODS if args.stage == "verifier_probe"
            else DIAGNOSTIC_METHODS)
        is_verifier = set(selected_methods) == set(VERIFIER_METHODS)
        return _run_real_matrix(
            args, conditions or DIAGNOSTIC_CONDITIONS, selected_methods,
            ("stage_d_verifier_ablation.json" if is_verifier
             else "stage_c_diagnostic_pilot.json"))
    raise SystemExit(f"unsupported r2 real stage: {args.stage}")


def run_real_backend_experiment(args) -> int:
    """Gated LIBERO run. Exactly 10 nominal + 60 paired pilot episodes."""

    if args.stage in ("controller_gate", "regression_pilot",
                      "diagnostic_pilot", "verifier_probe"):
        return _run_real_r2_stage(args)

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


# ------------------------------------------------- Stage B: controller gate
def stage_controller_gate(n_seeds: int, executor: str, **kw) -> Dict[str, Any]:
    """Nominal reliability, reported PER LEG as well as per episode.

    The v2 pilot lost 4/20 paired seeds to `grasp_not_acquired` on milk. A gate
    that reports only final task success cannot see that, so this stage reports
    per-object grasp reliability and names any object below threshold.
    """
    per_seed, per_object = [], {}
    for s in range(n_seeds):
        r = _run(BasketTaskSpec(seed=s, condition="nominal",
                                method=CONTROL), executor, **kw)
        legs = getattr(r, "legs", []) or []
        for leg in legs:
            o = leg.get("obj") or leg.get("object")
            rec = per_object.setdefault(o, {"attempts": 0, "grasped": 0,
                                            "placed": 0})
            rec["attempts"] += 1
            rec["grasped"] += int(not str(leg.get("reason", "")).startswith("grasp"))
            rec["placed"] += int(bool(leg.get("placed")))
        per_seed.append({"seed": s,
                         "success": bool(r.metrics.revised_task_success)})
    weakest = sorted(per_object.items(),
                     key=lambda kv: kv[1]["grasped"] / max(1, kv[1]["attempts"]))
    out = {"n_seeds": n_seeds,
           "episode_successes": sum(x["success"] for x in per_seed),
           "per_seed": per_seed, "per_object": per_object,
           "weakest_object": weakest[0][0] if weakest else None,
           "weakest_grasp_rate": (weakest[0][1]["grasped"]
                                  / max(1, weakest[0][1]["attempts"]))
           if weakest else None}
    out["passed"] = (out["episode_successes"] >= 8
                     and (out["weakest_grasp_rate"] or 1.0) >= 0.9)
    out["note"] = ("Fix the asset pose, grasp waypoint or controller before "
                   "comparing methods. Do not use method results to compensate "
                   "for a poor nominal controller.")
    return out


# --------------------------------------- Stage C/D: scheduler-aware pilots
def stage_paired(conditions, methods, n_seeds: int, executor: str,
                 **kw) -> Dict[str, Any]:
    episodes = []
    for cond in conditions:
        for seed in range(n_seeds):
            for method in methods:
                r = _run(BasketTaskSpec(seed=seed, condition=cond,
                                        method=method), executor, **kw)
                episodes.append(r.to_dict())
    # acceptance criteria for the regression pilot
    checks = {
        "every_non_terminated_episode_got_its_events": all(
            e.get("schedule", {}).get("all_delivered", True)
            or any(not ev.get("event_delivered")
                   and "termination" in str(ev.get("delivery_failure_reason"))
                   for ev in e.get("schedule", {}).get("events", []))
            for e in episodes),
        "failure_layers_present": all(e.get("layers", {}).get("failure_layer")
                                      for e in episodes),
        "no_silent_exclusions": len(episodes) == len(conditions) * n_seeds
                                * len(methods),
    }
    return {"episodes": episodes, "acceptance": checks,
            "analysis": analyse(episodes)}


def stage_verifier_probe() -> Dict[str, Any]:
    from cope.benchmark.verifier_probe import (VerifierProbeSpec,
                                               compare_verifier_arms)
    spec = VerifierProbeSpec(obstacle_radius=0.20, obstacle_frac=0.40)
    return compare_verifier_arms(spec)


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
    ap.add_argument(
        "--resume", action="store_true",
        help="real matrix only: reuse strictly complete matching episodes; "
             "preserve and rerun incomplete episode directories")
    ap.add_argument("--conditions", default=None,
                    help="comma-separated, e.g. I1,I2,I3,I4 or I3,I4,I5. "
                         "Defaults to I1-I4 for the regression pilot and "
                         "I3,I4,I5 for the diagnostic pilot.")
    ap.add_argument("--methods", default=None,
                    help="comma-separated arm list. Stage D uses the FSR-PC "
                         "variants and/or the verifier ablation.")
    ap.add_argument("--stage",
                    choices=("gate", "pilot", "all", "controller_gate",
                             "regression_pilot", "diagnostic_pilot",
                             "verifier_probe"),
                    default="all",
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

    conds = tuple(args.conditions.split(",")) if args.conditions else None
    meths = tuple(args.methods.split(",")) if args.methods else None

    if args.stage == "controller_gate":
        rep = stage_controller_gate(args.gate_seeds, args.executor,
                                    p_success=args.p_success)
        (args.out / "stage_b_controller_gate.json").write_text(
            json.dumps({"meta": meta, "gate": rep}, indent=2, default=str))
        print(f"Controller gate: {rep['episode_successes']}/{rep['n_seeds']} "
              f"episodes; weakest object {rep['weakest_object']} at "
              f"{rep['weakest_grasp_rate']:.2f} grasp rate -> "
              f"{'PASS' if rep['passed'] else 'FAIL'}")
        for o, r in sorted(rep["per_object"].items()):
            print(f"   {o:8s} grasp {r['grasped']}/{r['attempts']}  "
                  f"placed {r['placed']}/{r['attempts']}")
        return 0 if rep["passed"] else 1

    if args.stage == "verifier_probe":
        rep = stage_verifier_probe()
        (args.out / "stage_d_verifier_probe.json").write_text(
            json.dumps({"meta": meta, "probe": rep}, indent=2, default=str))
        print(f"Verifier probe: rejected(full)={rep['n_rejected_full']} "
              f"rejected(ablated)={rep['n_rejected_ablated']} "
              f"changed_decision={rep['verifier_changed_the_decision']}")
        return 0 if rep["verifier_changed_the_decision"] else 1

    if args.stage in ("regression_pilot", "diagnostic_pilot"):
        if args.stage == "regression_pilot":
            c = conds or CONDITIONS
            m = meths or (PRIMARY + (CONTROL,))
            name = "stage_c_regression_pilot.json"
        else:
            c = conds or DIAGNOSTIC_CONDITIONS
            m = meths or DIAGNOSTIC_METHODS
            name = "stage_d_diagnostic_pilot.json"
        rep = stage_paired(c, m, args.seeds, args.executor,
                           p_success=args.p_success)
        (args.out / name).write_text(
            json.dumps({"meta": meta, **rep}, indent=2, default=str))
        print(f"{args.stage}: {len(rep['episodes'])} episodes "
              f"({len(c)} conditions x {args.seeds} seeds x {len(m)} arms)")
        for k, v in rep["acceptance"].items():
            print(f"  {k}: {v}")
        print(f"Wrote {args.out / name}")
        return 0 if all(rep["acceptance"].values()) else 1

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
