#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


METHODS = ("history_augmented_full_regeneration", "cope_patch")
FORBIDDEN_MARKERS = ("fake", "mock", "scripted", "noop", "dry_run", "fixture")


def _load(path: Path) -> list[dict[str, Any]]:
    if path.is_dir():
        records: list[dict[str, Any]] = []
        for child in sorted(path.rglob("*.json")):
            try:
                value = json.loads(child.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "method" in value and "pair_key" in value:
                value["_source_path"] = str(child)
                records.append(value)
        return records
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("episodes"), list):
        return list(value["episodes"])
    return [value]


def validate_formal_records(records: Iterable[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for index, record in enumerate(records):
        grouped[str(record.get("pair_key", ""))].append(record)
        if record.get("evidence_admissibility") != "formal":
            errors.append(f"record {index} is not marked evidence_admissibility=formal")
        provider = str(record.get("provider", "")).lower()
        if not provider or any(marker in provider for marker in FORBIDDEN_MARKERS):
            errors.append(f"record {index} has missing/forbidden provider {provider!r}")
        if record.get("manual_intervention"):
            errors.append(f"record {index} used manual intervention")
        if record.get("timeout") and record.get("success"):
            errors.append(f"record {index} counts timeout as success")
        if record.get("method") not in METHODS:
            errors.append(f"record {index} has unknown method {record.get('method')!r}")
        provenance = record.get("provenance") or {}
        if not provenance.get("runtime_commit") or not provenance.get("checkpoint"):
            errors.append(f"record {index} lacks commit/checkpoint provenance")
    for pair_key, pair in grouped.items():
        if len(pair) != 2 or {item.get("method") for item in pair} != set(METHODS):
            errors.append(f"pair {pair_key!r} is incomplete")
        elif len({item.get("event_schedule_hash") for item in pair}) != 1:
            errors.append(f"pair {pair_key!r} has unequal event schedules")
    return errors


def _count(record: Mapping[str, Any]) -> int:
    return int((record.get("pair_fields") or {}).get("interruption_count", -1))


def _task(record: Mapping[str, Any]) -> str:
    fields = record.get("pair_fields") or {}
    return f"{fields.get('task_suite')}:{fields.get('task_id')}"


def _mean(values: Sequence[float]) -> float:
    return float(sum(values) / len(values)) if values else float("nan")


def _success_curves(records: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    cells: dict[tuple[str, int], list[float]] = defaultdict(list)
    for record in records:
        cells[(str(record["method"]), _count(record))].append(float(bool(record.get("success"))))
    result: dict[str, dict[str, Any]] = {}
    for method in METHODS:
        curve = {
            str(count): {
                "success_rate": _mean(cells[(method, count)]),
                "episodes": len(cells[(method, count)]),
            }
            for count in range(4)
        }
        ys = [curve[str(count)]["success_rate"] for count in range(4)]
        auc = sum((ys[index] + ys[index + 1]) / 2 for index in range(3)) / 3
        slope = _linear_slope(list(range(4)), ys)
        result[method] = {"curve": curve, "auc": auc, "slope_per_interruption": slope}
    return result


def _linear_slope(xs: Sequence[float], ys: Sequence[float]) -> float:
    x_mean, y_mean = _mean(xs), _mean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return float("nan")
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator


def _cluster_bootstrap(
    records: Sequence[Mapping[str, Any]],
    *,
    replicates: int,
    seed: int,
) -> dict[str, Any]:
    by_task: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        by_task[_task(record)].append(record)
    tasks = sorted(by_task)
    rng = random.Random(seed)
    auc_differences: list[float] = []
    slope_differences: list[float] = []
    count_differences: dict[int, list[float]] = defaultdict(list)
    for _ in range(replicates):
        sampled: list[Mapping[str, Any]] = []
        for sampled_task in (rng.choice(tasks) for _ in tasks):
            sampled.extend(by_task[sampled_task])
        curves = _success_curves(sampled)
        auc_differences.append(curves[METHODS[1]]["auc"] - curves[METHODS[0]]["auc"])
        slope_differences.append(
            curves[METHODS[1]]["slope_per_interruption"]
            - curves[METHODS[0]]["slope_per_interruption"]
        )
        for count in range(4):
            count_differences[count].append(
                curves[METHODS[1]]["curve"][str(count)]["success_rate"]
                - curves[METHODS[0]]["curve"][str(count)]["success_rate"]
            )
    return {
        "replicates": replicates,
        "seed": seed,
        "cope_minus_regeneration_auc": _interval(auc_differences),
        "cope_minus_regeneration_slope": _interval(slope_differences),
        "cope_minus_regeneration_success_by_count": {
            str(count): _interval(values) for count, values in sorted(count_differences.items())
        },
    }


def _interval(values: Sequence[float]) -> dict[str, float]:
    ordered = sorted(value for value in values if math.isfinite(value))
    if not ordered:
        return {"estimate": float("nan"), "low_95": float("nan"), "high_95": float("nan")}
    low = ordered[int(0.025 * (len(ordered) - 1))]
    high = ordered[int(0.975 * (len(ordered) - 1))]
    return {"estimate": _mean(ordered), "low_95": low, "high_95": high}


def _exact_paired_success(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, bool]] = defaultdict(dict)
    for record in records:
        grouped[str(record["pair_key"])][str(record["method"])] = bool(record.get("success"))
    regen_only = sum(
        pair.get(METHODS[0], False) and not pair.get(METHODS[1], False) for pair in grouped.values()
    )
    cope_only = sum(
        pair.get(METHODS[1], False) and not pair.get(METHODS[0], False) for pair in grouped.values()
    )
    discordant = regen_only + cope_only
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(math.comb(discordant, k) for k in range(0, min(regen_only, cope_only) + 1))
        p_value = min(1.0, 2.0 * tail / (2**discordant))
    return {
        "test": "exact_two_sided_mcnemar_binomial",
        "regeneration_only_success": regen_only,
        "cope_only_success": cope_only,
        "discordant_pairs": discordant,
        "p_value": p_value,
    }


def _mixed_effects(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    try:
        import pandas as pd
        import statsmodels.api as sm
    except ImportError as exc:
        return {"status": "not_run", "reason": f"optional dependency missing: {exc}"}
    frame = pd.DataFrame(
        {
            "success": [int(bool(record.get("success"))) for record in records],
            "cope": [int(record.get("method") == "cope_patch") for record in records],
            "count": [_count(record) for record in records],
            "interaction": [
                int(record.get("method") == "cope_patch") * _count(record) for record in records
            ],
            "task": [_task(record) for record in records],
        }
    )
    try:
        model = sm.BinomialBayesMixedGLM.from_formula(
            "success ~ cope + count + interaction",
            {"task_random_intercept": "0 + C(task)"},
            frame,
        )
        fitted = model.fit_vb()
        names = list(model.exog_names)
        coefficients = {
            name: {
                "mean": float(fitted.fe_mean[index]),
                "sd": float(fitted.fe_sd[index]),
            }
            for index, name in enumerate(names)
        }
        return {
            "status": "complete",
            "model": "binomial_mixed_effects_variational_bayes_random_task_intercept",
            "fixed_effects_log_odds": coefficients,
            "interaction_term": coefficients.get("interaction"),
        }
    except Exception as exc:
        return {"status": "failed", "reason": repr(exc)}


def _secondary_metric_tests(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    metric_names = (
        "progress_preservation",
        "unaffected_constraint_survival",
        "preference_violation_rate",
        "safety_violation_rate",
        "silent_commitment_loss_rate",
    )
    grouped: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for record in records:
        grouped[str(record["pair_key"])][str(record["method"])] = record
    raw: dict[str, dict[str, Any]] = {}
    for metric in metric_names:
        differences: list[float] = []
        for pair in grouped.values():
            if set(pair) != set(METHODS):
                continue
            left = (pair[METHODS[0]].get("metrics") or {}).get(metric)
            right = (pair[METHODS[1]].get("metrics") or {}).get(metric)
            if left is not None and right is not None:
                differences.append(float(right) - float(left))
        if not differences:
            raw[metric] = {"status": "not_available"}
            continue
        positives = sum(value > 0 for value in differences)
        negatives = sum(value < 0 for value in differences)
        n = positives + negatives
        if n:
            small = min(positives, negatives)
            p_value = min(
                1.0,
                2.0 * sum(math.comb(n, k) for k in range(small + 1)) / (2**n),
            )
        else:
            p_value = 1.0
        raw[metric] = {
            "status": "complete",
            "test": "paired_exact_sign_test",
            "pairs": len(differences),
            "mean_cope_minus_regeneration": _mean(differences),
            "p_value": p_value,
        }
    completed = sorted(
        ((name, value["p_value"]) for name, value in raw.items() if value["status"] == "complete"),
        key=lambda item: item[1],
    )
    running = 0.0
    m = len(completed)
    adjusted: dict[str, float] = {}
    for rank, (name, p_value) in enumerate(completed):
        running = max(running, min(1.0, (m - rank) * p_value))
        adjusted[name] = running
    for name, value in raw.items():
        if name in adjusted:
            value["holm_adjusted_p_value"] = adjusted[name]
    return raw


def analyze(records: Sequence[Mapping[str, Any]], *, bootstrap_replicates: int) -> dict[str, Any]:
    validation_errors = validate_formal_records(records)
    if validation_errors:
        return {
            "status": "rejected",
            "reason": "formal-evidence validation failed",
            "errors": validation_errors,
            "no_statistics_reported": True,
        }
    curves = _success_curves(records)
    return {
        "status": "complete",
        "episodes": len(records),
        "pairs": len(records) // 2,
        "tasks": sorted({_task(record) for record in records}),
        "success_curves": curves,
        "task_clustered_bootstrap": _cluster_bootstrap(
            records,
            replicates=bootstrap_replicates,
            seed=20260724,
        ),
        "paired_success_test": _exact_paired_success(records),
        "mixed_effects_model": _mixed_effects(records),
        "secondary_metrics_with_holm_correction": _secondary_metric_tests(records),
        "interpretation_guards": {
            "positive_negative_or_null_results_all_retained": True,
            "interaction_primary": "cope × interruption_count",
            "cluster_unit": "task",
        },
    }


def _markdown(summary: Mapping[str, Any]) -> str:
    if summary.get("status") != "complete":
        errors = "\n".join(f"- {value}" for value in summary.get("errors", ()))
        return f"# Repeated Interruption Analysis\n\nStatus: rejected.\n\n{errors}\n"
    lines = [
        "# Repeated Interruption Analysis",
        "",
        f"Formal episodes: {summary['episodes']} ({summary['pairs']} paired conditions).",
        "",
        "| Method | n=0 | n=1 | n=2 | n=3 | AUC | slope |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        value = summary["success_curves"][method]
        rates = [value["curve"][str(count)]["success_rate"] for count in range(4)]
        lines.append(
            f"| {method} | "
            + " | ".join(f"{rate:.3f}" for rate in rates)
            + f" | {value['auc']:.3f} | {value['slope_per_interruption']:.3f} |"
        )
    lines.extend(
        [
            "",
            "The JSON companion contains task-clustered bootstrap intervals, paired tests, "
            "the mixed-effects interaction, and Holm-corrected secondary metrics.",
            "",
        ]
    )
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--bootstrap-replicates", type=int, default=5000)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    records = _load(args.input)
    summary = analyze(records, bootstrap_replicates=args.bootstrap_replicates)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_md.write_text(_markdown(summary), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
