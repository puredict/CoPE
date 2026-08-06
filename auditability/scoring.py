from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from auditability import SCHEMA_VERSION
from auditability.common import content_hash, normalize_text, read_jsonl, token_set, write_json


def token_f1(prediction: Any, truth: Any) -> float:
    predicted = Counter(token_set(prediction))
    expected = Counter(token_set(truth))
    if not predicted and not expected:
        return 1.0
    if not predicted or not expected:
        return 0.0
    overlap = sum((predicted & expected).values())
    precision = overlap / sum(predicted.values())
    recall = overlap / sum(expected.values())
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def field_f1(prediction: dict[str, Any], truth: dict[str, Any]) -> float:
    predicted_fields = {f"answer={normalize_text(prediction.get('answer'))}"}
    truth_fields = {f"answer={normalize_text(truth.get('normalized_answer'))}"}
    predicted_fields.update(
        f"support={value}" for value in prediction.get("supporting_ids") or []
    )
    truth_fields.update(f"support={value}" for value in truth.get("supporting_ids") or [])
    predicted_answerability = normalize_text(prediction.get("answerability"))
    if predicted_answerability.startswith("unanswerable"):
        predicted_answerability = "unanswerable"
    predicted_fields.add(f"answerability={predicted_answerability}")
    truth_answerability = (
        "unanswerable"
        if truth.get("answerability") == "unanswerable_from_ground_truth"
        else "answerable"
    )
    truth_fields.add(f"answerability={truth_answerability}")
    if prediction.get("failure_layer"):
        predicted_fields.add(f"failure_layer={prediction['failure_layer']}")
    if truth.get("failure_layer"):
        truth_fields.add(f"failure_layer={truth['failure_layer']}")
    overlap = len(predicted_fields & truth_fields)
    precision = overlap / len(predicted_fields)
    recall = overlap / len(truth_fields)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _parsed_prediction(row: dict[str, Any]) -> dict[str, Any]:
    parsed = row.get("parsed")
    return parsed if isinstance(parsed, dict) else row


def score_qa_item(
    question: dict[str, Any],
    package: dict[str, Any],
    prediction_row: dict[str, Any],
) -> dict[str, Any]:
    prediction = _parsed_prediction(prediction_row)
    truth = question["ground_truth"]
    unanswerable_truth = truth["answerability"] == "unanswerable_from_ground_truth"
    unanswerable_prediction = (
        str(prediction.get("answerability", "")).lower().startswith("unanswerable")
        or normalize_text(prediction.get("answer")) == "unanswerable"
    )
    exact = (
        unanswerable_prediction
        if unanswerable_truth
        else normalize_text(prediction.get("answer"))
        == normalize_text(truth["normalized_answer"])
    )
    predicted_ids = set(prediction.get("supporting_ids") or [])
    truth_ids = set(truth.get("supporting_ids") or [])
    provenance_exact = predicted_ids == truth_ids if not unanswerable_truth else not predicted_ids
    layer_exact = None
    if question["question_kind"] == "earliest_failure_layer":
        layer_exact = prediction.get("failure_layer") == truth.get("failure_layer")
        if prediction.get("failure_layer") is None:
            layer_exact = normalize_text(prediction.get("answer")) == normalize_text(
                truth.get("failure_layer")
            )
    seconds = prediction.get("completion_time_seconds")
    confidence = prediction.get("confidence")
    return {
        "package_id": package["package_id"],
        "item_id": question["item_id"],
        "episode_id": question["episode_id"],
        "condition_label": package["condition_label"],
        "question_kind": question["question_kind"],
        "exact": float(exact),
        "token_f1": token_f1(prediction.get("answer"), truth["normalized_answer"]),
        "field_f1": field_f1(prediction, truth),
        "unanswerable_truth": unanswerable_truth,
        "unanswerable_prediction": unanswerable_prediction,
        "provenance_exact": float(provenance_exact),
        "failure_layer_exact": None if layer_exact is None else float(layer_exact),
        "completion_time_seconds": float(seconds) if seconds not in {None, ""} else None,
        "confidence": float(confidence) if confidence not in {None, ""} else None,
    }


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def clustered_bootstrap_ci(
    rows: list[dict[str, Any]],
    field: str,
    *,
    seed: int,
    iterations: int,
) -> list[float] | None:
    clusters: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = row.get(field)
        if value is not None:
            clusters[row["episode_id"]].append(float(value))
    keys = sorted(clusters)
    if not keys:
        return None
    rng = random.Random(seed)
    samples = []
    for _ in range(iterations):
        selected = [rng.choice(keys) for _ in keys]
        values = [value for key in selected for value in clusters[key]]
        samples.append(statistics.fmean(values))
    samples.sort()
    lower = samples[max(0, int(0.025 * (len(samples) - 1)))]
    upper = samples[min(len(samples) - 1, int(0.975 * (len(samples) - 1)))]
    return [lower, upper]


def paired_bootstrap_ci(
    differences: list[tuple[str, float]],
    *,
    seed: int,
    iterations: int,
) -> list[float] | None:
    by_episode: dict[str, list[float]] = defaultdict(list)
    for episode_id, difference in differences:
        by_episode[episode_id].append(difference)
    episode_ids = sorted(by_episode)
    if not episode_ids:
        return None
    rng = random.Random(seed)
    samples = []
    for _ in range(iterations):
        selected = [rng.choice(episode_ids) for _ in episode_ids]
        values = [value for episode_id in selected for value in by_episode[episode_id]]
        samples.append(statistics.fmean(values))
    samples.sort()
    return [
        samples[max(0, int(0.025 * (len(samples) - 1)))],
        samples[min(len(samples) - 1, int(0.975 * (len(samples) - 1)))],
    ]


def fleiss_kappa(annotations: list[dict[str, Any]]) -> float | None:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in annotations:
        grouped[row["package_id"]].append(normalize_text(row.get("answer")))
    groups = [answers for answers in grouped.values() if len(answers) >= 2]
    if not groups:
        return None
    categories = sorted({answer for answers in groups for answer in answers})
    if len(categories) <= 1:
        return 1.0
    total_ratings = sum(len(answers) for answers in groups)
    proportions = {
        category: sum(answers.count(category) for answers in groups) / total_ratings
        for category in categories
    }
    observed = []
    for answers in groups:
        n = len(answers)
        counts = Counter(answers)
        observed.append(
            sum(count * (count - 1) for count in counts.values()) / (n * (n - 1))
        )
    p_bar = statistics.fmean(observed)
    p_e = sum(value * value for value in proportions.values())
    if math.isclose(1.0, p_e):
        return 1.0
    return (p_bar - p_e) / (1.0 - p_e)


def score_corruptions(
    manifests: list[dict[str, Any]], audits: list[dict[str, Any]]
) -> dict[str, Any]:
    audit_by_id = {row.get("corruption_id"): row for row in audits}
    tp = fp = tn = fn = type_hits = 0
    positives = 0
    missing = []
    for manifest in manifests:
        audit = audit_by_id.get(manifest["corruption_id"])
        if audit is None:
            missing.append(manifest["corruption_id"])
            continue
        expected = not manifest["negative_control"]
        detected = bool(audit.get("detected"))
        if expected:
            positives += 1
            type_hits += manifest["error_type"] in set(audit.get("detected_error_types", []))
        if expected and detected:
            tp += 1
        elif expected:
            fn += 1
        elif detected:
            fp += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0,
        "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0,
        "error_type_recall": type_hits / positives if positives else None,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "missing_audit_count": len(missing),
    }


def score_all(
    questions: list[dict[str, Any]],
    packages: list[dict[str, Any]],
    condition_key: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    *,
    seed: int,
    bootstrap_iterations: int,
    annotations: list[dict[str, Any]] | None = None,
    corruption_manifests: list[dict[str, Any]] | None = None,
    corruption_audits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    question_by_id = {row["item_id"]: row for row in questions}
    package_by_id = {row["package_id"]: row for row in packages}
    key = {
        (row["episode_id"], row["condition_label"]): row["internal_condition"]
        for row in condition_key
    }
    scored = []
    duplicates = set()
    seen = set()
    for prediction in predictions:
        package_id = prediction.get("package_id")
        if package_id in seen:
            duplicates.add(package_id)
            continue
        seen.add(package_id)
        package = package_by_id.get(package_id)
        if package is None:
            continue
        question = question_by_id[package["item_id"]]
        row = score_qa_item(question, package, prediction)
        row["condition"] = key.get((row["episode_id"], row["condition_label"]), "unknown")
        scored.append(row)
    conditions = {}
    for condition in sorted({row["condition"] for row in scored}):
        rows = [row for row in scored if row["condition"] == condition]
        layer_values = [
            row["failure_layer_exact"]
            for row in rows
            if row["failure_layer_exact"] is not None
        ]
        seconds = [
            row["completion_time_seconds"]
            for row in rows
            if row["completion_time_seconds"] is not None
        ]
        confidence = [row["confidence"] for row in rows if row["confidence"] is not None]
        conditions[condition] = {
            "n": len(rows),
            "audit_qa_exact_accuracy": _mean([row["exact"] for row in rows]),
            "audit_qa_exact_accuracy_ci95": clustered_bootstrap_ci(
                rows, "exact", seed=seed, iterations=bootstrap_iterations
            ),
            "token_f1": _mean([row["token_f1"] for row in rows]),
            "field_f1": _mean([row["field_f1"] for row in rows]),
            "unanswerable_rate": _mean(
                [float(row["unanswerable_prediction"]) for row in rows]
            ),
            "ground_truth_unanswerable_rate": _mean(
                [float(row["unanswerable_truth"]) for row in rows]
            ),
            "provenance_link_accuracy": _mean(
                [row["provenance_exact"] for row in rows]
            ),
            "earliest_failure_layer_accuracy": _mean(layer_values),
            "mean_completion_time_seconds": _mean(seconds),
            "mean_confidence": _mean(confidence),
        }
    paired = {}
    by_item_condition = {
        (row["item_id"], row["condition"]): row for row in scored
    }
    item_ids = sorted({row["item_id"] for row in scored})
    for left, right in (("typed_patch", "raw"), ("typed_patch", "regeneration")):
        differences = [
            (
                by_item_condition[(item_id, left)]["episode_id"],
                by_item_condition[(item_id, left)]["exact"]
                - by_item_condition[(item_id, right)]["exact"],
            )
            for item_id in item_ids
            if (item_id, left) in by_item_condition
            and (item_id, right) in by_item_condition
        ]
        time_differences = [
            (
                by_item_condition[(item_id, left)]["episode_id"],
                by_item_condition[(item_id, left)]["completion_time_seconds"]
                - by_item_condition[(item_id, right)]["completion_time_seconds"],
            )
            for item_id in item_ids
            if (item_id, left) in by_item_condition
            and (item_id, right) in by_item_condition
            and by_item_condition[(item_id, left)]["completion_time_seconds"] is not None
            and by_item_condition[(item_id, right)]["completion_time_seconds"] is not None
        ]
        paired[f"{left}_minus_{right}"] = {
            "paired_accuracy_difference": _mean([value for _, value in differences]),
            "paired_accuracy_difference_ci95": paired_bootstrap_ci(
                differences, seed=seed, iterations=bootstrap_iterations
            ),
            "paired_completion_time_difference_seconds": _mean(
                [value for _, value in time_differences]
            ),
            "paired_completion_time_difference_seconds_ci95": paired_bootstrap_ci(
                time_differences, seed=seed, iterations=bootstrap_iterations
            ),
            "paired_item_count": len(differences),
        }
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "prediction_count": len(predictions),
        "scored_count": len(scored),
        "missing_prediction_count": len(packages) - len(seen & set(package_by_id)),
        "duplicate_prediction_count": len(duplicates),
        "conditions": conditions,
        "paired": paired,
    }
    if annotations is not None:
        disagreements = 0
        grouped: dict[str, list[str]] = defaultdict(list)
        for row in annotations:
            grouped[row["package_id"]].append(normalize_text(row.get("answer")))
        disagreements = sum(len(set(values)) > 1 for values in grouped.values())
        human_scored = []
        for annotation in annotations:
            package = package_by_id.get(annotation.get("package_id"))
            if package is None:
                continue
            question = question_by_id[package["item_id"]]
            row = score_qa_item(question, package, annotation)
            row["condition"] = key.get(
                (row["episode_id"], row["condition_label"]), "unknown"
            )
            human_scored.append(row)
        condition_accuracy = {
            condition: _mean(
                [row["exact"] for row in human_scored if row["condition"] == condition]
            )
            for condition in sorted({row["condition"] for row in human_scored})
        }
        result["human_study"] = {
            "annotation_count": len(annotations),
            "scored_annotation_count": len(human_scored),
            "audit_qa_exact_accuracy": _mean([row["exact"] for row in human_scored]),
            "condition_accuracy": condition_accuracy,
            "provenance_link_accuracy": _mean(
                [row["provenance_exact"] for row in human_scored]
            ),
            "fleiss_kappa": fleiss_kappa(annotations),
            "adjudication_rate": disagreements / len(grouped) if grouped else None,
            "mean_completion_time_seconds": _mean(
                [float(row["completion_time_seconds"]) for row in annotations]
            ),
            "mean_confidence": _mean(
                [float(row["confidence"]) for row in annotations]
            ),
        }
    if corruption_manifests is not None and corruption_audits is not None:
        result["corruption_detection"] = score_corruptions(
            corruption_manifests, corruption_audits
        )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score auditability QA and corruptions.")
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--condition-key", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--corruption-manifest", type=Path)
    parser.add_argument("--corruption-audits", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--bootstrap-iterations", type=int, default=2000)
    parser.add_argument("--schema-version", default=SCHEMA_VERSION)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema version: {args.schema_version}")
    if bool(args.corruption_manifest) != bool(args.corruption_audits):
        raise ValueError("corruption manifest and audits must be supplied together")
    config = {
        "questions": str(args.questions.resolve()),
        "packages": str(args.packages.resolve()),
        "condition_key": str(args.condition_key.resolve()),
        "predictions": str(args.predictions.resolve()),
        "annotations": str(args.annotations.resolve()) if args.annotations else None,
        "corruption_manifest": str(args.corruption_manifest.resolve())
        if args.corruption_manifest
        else None,
        "corruption_audits": str(args.corruption_audits.resolve())
        if args.corruption_audits
        else None,
        "seed": args.seed,
        "bootstrap_iterations": args.bootstrap_iterations,
        "schema_version": args.schema_version,
    }
    result = score_all(
        read_jsonl(args.questions),
        read_jsonl(args.packages),
        read_jsonl(args.condition_key),
        read_jsonl(args.predictions),
        seed=args.seed,
        bootstrap_iterations=args.bootstrap_iterations,
        annotations=read_jsonl(args.annotations) if args.annotations else None,
        corruption_manifests=read_jsonl(args.corruption_manifest)
        if args.corruption_manifest
        else None,
        corruption_audits=read_jsonl(args.corruption_audits)
        if args.corruption_audits
        else None,
    )
    result["config_hash"] = content_hash(config)
    if args.dry_run:
        print(json.dumps(result, sort_keys=True))
        return
    write_json(args.output, result, overwrite=args.resume)
    print(json.dumps({"output": str(args.output), **result}, sort_keys=True))


if __name__ == "__main__":
    main()
