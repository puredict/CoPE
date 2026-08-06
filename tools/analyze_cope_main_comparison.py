from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cope.types import DISTURBED_METHODS, METHOD_NAMES
from cope.validation import read_jsonl, validate_run_records


BASELINES = (
    "reactive_disturbed",
    "structured_relocalize_prompt",
    "stage_backtrack_subgoal",
    "history_augmented_full_regeneration",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze the strictly paired CoPE main comparison.")
    parser.add_argument("episodes_jsonl")
    parser.add_argument("--out", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260724)
    parser.add_argument("--phase", choices=("pilot", "formal", "detected"), default="formal")
    parser.add_argument(
        "--oracle-episodes-jsonl",
        default=None,
        help="Matched oracle run used to compute oracle-to-detected sensitivity drop.",
    )
    return parser.parse_args()


def _quantiles(values: list[float]) -> list[float | None]:
    finite = np.asarray([value for value in values if np.isfinite(value)], dtype=float)
    if finite.size == 0:
        return [None, None]
    return [float(np.quantile(finite, 0.025)), float(np.quantile(finite, 0.975))]


def task_cluster_bootstrap(
    rows: list[dict[str, Any]],
    statistic: Callable[[list[dict[str, Any]]], float],
    *,
    samples: int,
    seed: int,
) -> dict[str, Any]:
    by_task: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_task[int(row["task_id"])].append(row)
    tasks = sorted(by_task)
    estimate = float(statistic(rows))
    if not tasks:
        return {"estimate": estimate, "ci95": [None, None], "samples": 0}
    rng = np.random.default_rng(seed)
    values: list[float] = []
    for _ in range(samples):
        selected = rng.choice(tasks, size=len(tasks), replace=True)
        sampled: list[dict[str, Any]] = []
        for draw_index, task_id in enumerate(selected):
            sampled.extend(
                {
                    **row,
                    "_bootstrap_pair_key": f"{draw_index}:{row['pair_key']}",
                }
                for row in by_task[int(task_id)]
            )
        values.append(float(statistic(sampled)))
    return {"estimate": estimate, "ci95": _quantiles(values), "samples": samples}


def _rate(method: str) -> Callable[[list[dict[str, Any]]], float]:
    def statistic(rows: list[dict[str, Any]]) -> float:
        values = [float(bool(row["success"])) for row in rows if row["method"] == method]
        return float(np.mean(values)) if values else float("nan")

    return statistic


def _paired_gain(method_a: str, method_b: str) -> Callable[[list[dict[str, Any]]], float]:
    def statistic(rows: list[dict[str, Any]]) -> float:
        grouped: dict[str, dict[str, bool]] = defaultdict(dict)
        for row in rows:
            grouped[str(row.get("_bootstrap_pair_key", row["pair_key"]))][str(row["method"])] = bool(row["success"])
        differences = [
            float(outcomes[method_a]) - float(outcomes[method_b])
            for outcomes in grouped.values()
            if method_a in outcomes and method_b in outcomes
        ]
        return float(np.mean(differences)) if differences else float("nan")

    return statistic


def exact_mcnemar(rows: list[dict[str, Any]], method_a: str, method_b: str) -> dict[str, Any]:
    grouped: dict[str, dict[str, bool]] = defaultdict(dict)
    for row in rows:
        grouped[str(row["pair_key"])][str(row["method"])] = bool(row["success"])
    b = 0
    c = 0
    complete = 0
    for outcomes in grouped.values():
        if method_a not in outcomes or method_b not in outcomes:
            continue
        complete += 1
        if outcomes[method_a] and not outcomes[method_b]:
            b += 1
        elif outcomes[method_b] and not outcomes[method_a]:
            c += 1
    discordant = b + c
    if discordant == 0:
        p_value = 1.0
    else:
        lower = min(b, c)
        tail = sum(math.comb(discordant, index) for index in range(lower + 1)) / (2**discordant)
        p_value = min(1.0, 2.0 * tail)
    return {
        "method_a": method_a,
        "method_b": method_b,
        "complete_pairs": complete,
        "a_success_b_failure": b,
        "a_failure_b_success": c,
        "exact_two_sided_p": p_value,
    }


def holm_adjust(tests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(enumerate(tests), key=lambda item: item[1]["exact_two_sided_p"])
    adjusted = [0.0] * len(tests)
    running = 0.0
    count = len(tests)
    for rank, (original_index, test) in enumerate(ordered):
        candidate = min(1.0, (count - rank) * float(test["exact_two_sided_p"]))
        running = max(running, candidate)
        adjusted[original_index] = running
    return [{**test, "holm_adjusted_p": adjusted[index]} for index, test in enumerate(tests)]


def mixed_effects_logistic(rows: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        import pandas as pd
        from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
    except Exception as exc:
        return {
            "available": False,
            "fitted": False,
            "error": f"{type(exc).__name__}: {exc}",
            "required_model": "logistic mixed-effects with task and task/state random intercepts",
        }
    try:
        frame = pd.DataFrame(
            {
                "success": [int(bool(row["success"])) for row in rows],
                "method": [str(row["method"]) for row in rows],
                "task_id": [str(row["task_id"]) for row in rows],
                "task_state": [f"{row['task_id']}:{row['initial_state_id']}" for row in rows],
            }
        )
        if frame["success"].nunique() < 2:
            raise ValueError("mixed-effects model requires both success and failure outcomes")
        formula = (
            'success ~ C(method, Treatment(reference="history_augmented_full_regeneration"))'
        )
        model = BinomialBayesMixedGLM.from_formula(
            formula,
            {"task_random_intercept": "0 + C(task_id)", "state_random_intercept": "0 + C(task_state)"},
            frame,
        )
        fit = model.fit_vb()
        names = list(model.exog_names)
        fixed = []
        for index, name in enumerate(names):
            mean = float(fit.fe_mean[index])
            sd = float(fit.fe_sd[index])
            fixed.append(
                {
                    "term": name,
                    "log_odds_mean": mean,
                    "posterior_sd": sd,
                    "odds_ratio": math.exp(mean),
                    "approx_ci95": [math.exp(mean - 1.96 * sd), math.exp(mean + 1.96 * sd)],
                }
            )
        return {
            "available": True,
            "fitted": True,
            "implementation": "statsmodels BinomialBayesMixedGLM variational Bayes",
            "formula": formula,
            "random_intercepts": ["task_id", "task_id:initial_state_id"],
            "fixed_effects": fixed,
        }
    except Exception as exc:
        return {
            "available": True,
            "fitted": False,
            "error": f"{type(exc).__name__}: {exc}",
            "required_model": "logistic mixed-effects with task and task/state random intercepts",
        }


def _conditioned_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean_success = {
        str(row["pair_key"])
        for row in rows
        if row["method"] == "clean" and bool(row["success"])
    }
    return [row for row in rows if str(row["pair_key"]) in clean_success]


def secondary_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for method in METHOD_NAMES:
        method_rows = [row for row in rows if row["method"] == method]
        successful = [row for row in method_rows if row.get("success")]
        termination_counts: dict[str, int] = defaultdict(int)
        for row in method_rows:
            termination_counts[str(row.get("termination_reason"))] += 1
        progress_deltas = [
            float((row.get("task_progress") or {}).get("final_reward", 0.0))
            - float((row.get("task_progress") or {}).get("pre_event_reward", 0.0))
            for row in method_rows
        ]
        result[method] = {
            "episodes": len(method_rows),
            "mean_policy_steps": float(np.mean([row.get("policy_steps", 0) for row in method_rows]))
            if method_rows
            else None,
            "mean_successful_post_event_latency_steps": float(
                np.mean([row.get("steps_after_event", 0) for row in successful])
            )
            if successful
            else None,
            "mean_high_level_calls": float(
                np.mean([row.get("high_level_call_count", 0) for row in method_rows])
            )
            if method_rows
            else None,
            "mean_prompt_tokens": float(np.mean([row.get("prompt_tokens", 0) for row in method_rows]))
            if method_rows
            else None,
            "mean_completion_tokens": float(
                np.mean([row.get("completion_tokens", 0) for row in method_rows])
            )
            if method_rows
            else None,
            "mean_wall_time_seconds": float(
                np.mean([row.get("wall_time_seconds", 0.0) for row in method_rows])
            )
            if method_rows
            else None,
            "safety_violation_rate": float(
                np.mean([bool(row.get("safety_violation")) for row in method_rows])
            )
            if method_rows
            else None,
            "mean_task_progress_delta": float(np.mean(progress_deltas)) if progress_deltas else None,
            "task_progress_non_decrease_rate": float(
                np.mean([delta >= 0.0 for delta in progress_deltas])
            )
            if progress_deltas
            else None,
            "termination_counts": dict(termination_counts),
            "parse_failure_rate": (
                sum(row.get("termination_reason") == "high_level_parse_failure" for row in method_rows)
                / len(method_rows)
                if method_rows
                else None
            ),
            "validation_failure_rate": (
                sum(
                    row.get("termination_reason") == "high_level_validation_failure"
                    for row in method_rows
                )
                / len(method_rows)
                if method_rows
                else None
            ),
        }
    cope_rows = [row for row in rows if row["method"] == "cope_patch"]
    restores = 0
    blind_or_invalid_restores = 0
    for row in cope_rows:
        successful_revalidation: set[str] = set()
        for operation in row.get("patch_operations") or []:
            target_id = operation.get("target_id")
            if operation.get("op") == "Revalidate":
                result_payload = (operation.get("payload") or {}).get("result") or {}
                if result_payload.get("success") is True and target_id:
                    successful_revalidation.add(str(target_id))
            elif operation.get("op") == "Restore":
                restores += 1
                if target_id not in successful_revalidation:
                    blind_or_invalid_restores += 1
    result["cope_patch"]["unaffected_slot_preservation_rate"] = (
        float(
            np.mean(
                [
                    bool((row.get("unaffected_slot_preservation") or {}).get("passed"))
                    for row in cope_rows
                    if row.get("event") is not None
                ]
            )
        )
        if any(row.get("event") is not None for row in cope_rows)
        else None
    )
    result["cope_patch"]["blind_or_invalid_restore_rate"] = (
        blind_or_invalid_restores / restores if restores else 0.0
    )
    result["cope_patch"]["restore_count"] = restores
    return result


def _detector_metrics(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    detected_rows = [row for row in rows if row.get("event_source") == "detected" and row["method"] == "reactive_disturbed"]
    if not detected_rows:
        return None
    tp = fp = fn = 0
    latencies: list[float] = []
    for row in detected_rows:
        summary = row.get("detector") or {}
        counts = summary.get("confusion_counts") or {}
        tp += int(counts.get("tp", 0))
        fp += int(counts.get("fp", 0))
        fn += int(counts.get("fn", 0))
        if summary.get("event_latency_steps") is not None:
            latencies.append(float(summary["event_latency_steps"]))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return {
        "pair_count": len(detected_rows),
        "precision": precision,
        "recall": recall,
        "event_latency_steps_mean": float(np.mean(latencies)) if latencies else None,
        "event_latency_steps_median": float(np.median(latencies)) if latencies else None,
        "counts": {"tp": tp, "fp": fp, "fn": fn},
        "minimum_30_pairs_met": len(detected_rows) >= 30,
    }


def summarize_scope(
    rows: list[dict[str, Any]],
    *,
    samples: int,
    seed: int,
) -> dict[str, Any]:
    rates = {
        method: task_cluster_bootstrap(rows, _rate(method), samples=samples, seed=seed + index)
        for index, method in enumerate(METHOD_NAMES)
    }
    strongest = max(BASELINES, key=lambda method: rates[method]["estimate"])
    gains = {
        baseline: task_cluster_bootstrap(
            rows,
            _paired_gain("cope_patch", baseline),
            samples=samples,
            seed=seed + 100 + index,
        )
        for index, baseline in enumerate(BASELINES)
    }
    tests = holm_adjust([exact_mcnemar(rows, "cope_patch", baseline) for baseline in BASELINES])
    return {
        "pair_count": len({str(row["pair_key"]) for row in rows}),
        "episode_count": len(rows),
        "task_clustered_success": rates,
        "strongest_observed_current_world_baseline": strongest,
        "cope_paired_gains": gains,
        "mcnemar_holm": tests,
        "secondary_metrics": secondary_metrics(rows),
        "mixed_effects_logistic": mixed_effects_logistic(rows),
    }


def oracle_to_detected_sensitivity(
    detected_rows: list[dict[str, Any]],
    oracle_rows: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    if oracle_rows is None:
        return None
    oracle_lookup = {
        (str(row["pair_key"]), str(row["method"])): bool(row["success"])
        for row in oracle_rows
    }
    detected_lookup = {
        (str(row["pair_key"]), str(row["method"])): bool(row["success"])
        for row in detected_rows
    }
    common = set(oracle_lookup) & set(detected_lookup)
    by_method: dict[str, Any] = {}
    for method in METHOD_NAMES:
        keys = sorted(key for key in common if key[1] == method)
        if not keys:
            continue
        oracle_rate = float(np.mean([oracle_lookup[key] for key in keys]))
        detected_rate = float(np.mean([detected_lookup[key] for key in keys]))
        by_method[method] = {
            "matched_pairs": len(keys),
            "oracle_success_rate": oracle_rate,
            "detected_success_rate": detected_rate,
            "detected_minus_oracle": detected_rate - oracle_rate,
        }
    return {
        "methods": by_method,
        "cope_minimum_30_matched_pairs_met": by_method.get("cope_patch", {}).get("matched_pairs", 0) >= 30,
    }


def analyze(
    rows: list[dict[str, Any]],
    *,
    samples: int,
    seed: int,
    phase: str,
    oracle_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    validation = validate_run_records(rows, check_artifacts=False)
    all_pairs = summarize_scope(rows, samples=samples, seed=seed)
    conditioned = _conditioned_rows(rows)
    clean_conditioned = summarize_scope(conditioned, samples=samples, seed=seed + 1000) if conditioned else None
    strongest = all_pairs["strongest_observed_current_world_baseline"]
    gain = all_pairs["cope_paired_gains"][strongest]
    baseline_safety = np.mean(
        [bool(row.get("safety_violation")) for row in rows if row["method"] == strongest]
    )
    cope_safety = np.mean(
        [bool(row.get("safety_violation")) for row in rows if row["method"] == "cope_patch"]
    )
    equal_privileges = all(
        int(row.get("reset_count", 0)) == 0
        and int(row.get("rollback_count", 0)) == 0
        and row.get("manual_intervention") is False
        for row in rows
    )
    lower = gain["ci95"][0]
    threshold: dict[str, Any] = {
        "evaluated": True,
        "strongest_baseline": strongest,
        "cope_gain_at_least_10pp": bool(gain["estimate"] >= 0.10),
        "paired_gain_ci_lower_above_zero": bool(lower is not None and lower > 0.0),
        "no_extra_privileges": equal_privileges,
        "safety_not_higher": bool(cope_safety <= baseline_safety),
    }
    threshold["all_met"] = all(
        value
        for key, value in threshold.items()
        if key not in {"strongest_baseline", "evaluated"}
    )
    mixed_available = all_pairs["mixed_effects_logistic"]["available"]
    test_only = any(
        bool(row.get("test_only"))
        or bool((row.get("provider_metadata") or {}).get("is_fake"))
        or str(row.get("atlas_commit", "")).startswith("fixture")
        for row in rows
    )
    if test_only:
        threshold = {
            "evaluated": False,
            "all_met": None,
            "reason": "test fixture/fake records are not empirical outcomes",
        }
    return {
        "schema_version": "cope-main-analysis-v1",
        "phase": phase,
        "test_only": test_only,
        "paper_evidence_eligible": bool(not test_only and phase in {"formal", "detected"}),
        "validation": validation,
        "all_pairs": None if test_only else all_pairs,
        "clean_success_conditioned": None if test_only else clean_conditioned,
        "synthetic_pipeline_check": all_pairs if test_only else None,
        "preregistered_threshold": threshold,
        "detector_metrics": None if test_only else _detector_metrics(rows),
        "oracle_to_detected_sensitivity": (
            None if test_only else oracle_to_detected_sensitivity(rows, oracle_rows)
        ),
        "analysis_complete": bool(validation["passed"] and (mixed_available or phase != "formal")),
        "notes": [
            "All-pairs is primary; clean-success-conditioned is conditional only.",
            "The strongest observed baseline is reported together with every preregistered CoPE comparison.",
            "No result is promoted from pilot to a paper-level conclusion.",
            "Synthetic/fake records exercise code paths only and are never reported as empirical method results.",
        ],
    }


def main() -> None:
    args = parse_args()
    rows = read_jsonl(args.episodes_jsonl)
    oracle_rows = read_jsonl(args.oracle_episodes_jsonl) if args.oracle_episodes_jsonl else None
    report = analyze(
        rows,
        samples=args.bootstrap_samples,
        seed=args.seed,
        phase=args.phase,
        oracle_rows=oracle_rows,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"analysis": str(out), "complete": report["analysis_complete"]}, indent=2))
    if not report["analysis_complete"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
