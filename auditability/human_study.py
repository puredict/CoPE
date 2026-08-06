from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from auditability import SCHEMA_VERSION
from auditability.common import content_hash, read_jsonl, stable_id, write_json, write_jsonl


EXPORT_FIELDS = (
    "assignment_id",
    "annotator_code",
    "package_id",
    "item_id",
    "episode_id",
    "condition_label",
    "question_kind",
    "question",
    "evidence_json",
    "answer",
    "supporting_ids_json",
    "failure_layer",
    "answerability",
    "confidence_1_to_5",
    "completion_time_seconds",
    "adjudication_note",
)


def _schedule(blocks: list[list[dict[str, Any]]], rng: random.Random) -> list[dict[str, Any]]:
    candidates = list(blocks)
    for _ in range(2000):
        rng.shuffle(candidates)
        valid = all(
            not (
                previous[0]["episode_id"] == current[0]["episode_id"]
                and previous[0]["condition_label"] != current[0]["condition_label"]
            )
            for previous, current in zip(candidates, candidates[1:])
        )
        if valid:
            ordered: list[dict[str, Any]] = []
            for block in candidates:
                rng.shuffle(block)
                ordered.extend(block)
            return ordered
    distinct_episodes = {block[0]["episode_id"] for block in blocks}
    if len(distinct_episodes) > 1:
        raise RuntimeError("could not construct a non-adjacent annotation schedule")
    ordered = []
    for block in candidates:
        rng.shuffle(block)
        ordered.extend(block)
    return ordered


def export_assignments(
    packages: list[dict[str, Any]],
    *,
    episode_count: int,
    annotator_count: int,
    ratings_per_package: int,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if annotator_count < ratings_per_package:
        raise ValueError("annotator_count must be at least ratings_per_package")
    episode_ids = sorted({row["episode_id"] for row in packages})
    rng = random.Random(seed)
    rng.shuffle(episode_ids)
    selected = set(episode_ids[: min(episode_count, len(episode_ids))])
    selected_packages = [row for row in packages if row["episode_id"] in selected]
    annotators = [f"A{index + 1:03d}" for index in range(annotator_count)]
    by_annotator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, package in enumerate(sorted(selected_packages, key=lambda row: row["package_id"])):
        start = index % annotator_count
        for offset in range(ratings_per_package):
            code = annotators[(start + offset) % annotator_count]
            by_annotator[code].append(package)

    rows: list[dict[str, Any]] = []
    for code in annotators:
        blocks_map: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for package in by_annotator[code]:
            blocks_map[(package["episode_id"], package["condition_label"])].append(package)
        schedule = _schedule(list(blocks_map.values()), random.Random(f"{seed}:{code}"))
        for order, package in enumerate(schedule):
            rows.append(
                {
                    "assignment_id": stable_id(
                        "assignment", code, package["package_id"], seed
                    ),
                    "annotator_code": code,
                    "package_id": package["package_id"],
                    "item_id": package["item_id"],
                    "episode_id": package["episode_id"],
                    "condition_label": package["condition_label"],
                    "question_kind": package["question_kind"],
                    "question": package["question"],
                    "evidence_json": json.dumps(
                        package["evidence"], ensure_ascii=False, sort_keys=True
                    ),
                    "answer": "",
                    "supporting_ids_json": "[]",
                    "failure_layer": "",
                    "answerability": "",
                    "confidence_1_to_5": "",
                    "completion_time_seconds": "",
                    "adjudication_note": "",
                    "_order": order,
                }
            )
    rows.sort(key=lambda row: (row["annotator_code"], row["_order"]))
    for row in rows:
        row.pop("_order")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "seed": seed,
        "episode_count": len(selected),
        "package_count": len(selected_packages),
        "assignment_count": len(rows),
        "annotator_count": annotator_count,
        "ratings_per_package": ratings_per_package,
        "completion_time_unit": "seconds",
        "collects_personal_information": False,
        "config_hash": content_hash(
            {
                "seed": seed,
                "episode_count": episode_count,
                "annotator_count": annotator_count,
                "ratings_per_package": ratings_per_package,
            }
        ),
    }
    return rows, manifest


def write_csv(path: Path, rows: list[dict[str, Any]], *, resume: bool = False) -> int:
    existing: set[str] = set()
    if path.exists() and not resume:
        raise FileExistsError(f"refusing to overwrite existing output: {path}")
    if path.exists():
        existing = {row["assignment_id"] for row in read_csv(path)}
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if path.exists() else "w"
    pending = [row for row in rows if row["assignment_id"] not in existing]
    with path.open(mode, encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_FIELDS)
        if mode == "w":
            writer.writeheader()
        writer.writerows(pending)
    return len(pending)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def import_annotations(
    completed: list[dict[str, str]], expected: list[dict[str, str]]
) -> list[dict[str, Any]]:
    expected_ids = {row["assignment_id"] for row in expected}
    observed: dict[str, dict[str, str]] = {}
    duplicates = []
    for row in completed:
        assignment_id = row.get("assignment_id", "")
        if assignment_id in observed:
            duplicates.append(assignment_id)
        observed[assignment_id] = row
    if duplicates:
        raise ValueError(f"duplicate assignment IDs: {sorted(set(duplicates))[:20]}")
    unknown = set(observed) - expected_ids
    missing = expected_ids - set(observed)
    if unknown:
        raise ValueError(f"unknown assignment IDs: {sorted(unknown)[:20]}")
    if missing:
        raise ValueError(f"missing assignment IDs: {sorted(missing)[:20]}")
    normalized = []
    for assignment_id in sorted(expected_ids):
        row = observed[assignment_id]
        if not row.get("answer", "").strip() and row.get("answerability") != "unanswerable":
            raise ValueError(f"{assignment_id}: answer is required")
        try:
            confidence = int(row["confidence_1_to_5"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{assignment_id}: invalid confidence") from exc
        if not 1 <= confidence <= 5:
            raise ValueError(f"{assignment_id}: confidence must be 1..5")
        try:
            seconds = float(row["completion_time_seconds"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{assignment_id}: invalid completion time") from exc
        if seconds < 0:
            raise ValueError(f"{assignment_id}: completion time cannot be negative")
        try:
            supporting_ids = json.loads(row.get("supporting_ids_json") or "[]")
        except json.JSONDecodeError as exc:
            raise ValueError(f"{assignment_id}: invalid supporting_ids_json") from exc
        if not isinstance(supporting_ids, list):
            raise ValueError(f"{assignment_id}: supporting_ids_json must be a list")
        normalized.append(
            {
                "assignment_id": assignment_id,
                "annotator_code": row["annotator_code"],
                "package_id": row["package_id"],
                "item_id": row["item_id"],
                "episode_id": row["episode_id"],
                "condition_label": row["condition_label"],
                "answer": row.get("answer", ""),
                "supporting_ids": supporting_ids,
                "failure_layer": row.get("failure_layer") or None,
                "answerability": row.get("answerability") or "answerable",
                "confidence": confidence,
                "completion_time_seconds": seconds,
                "adjudication_note": row.get("adjudication_note", ""),
            }
        )
    return normalized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export/import blinded human-study packages.")
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--packages", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--episodes", type=int, default=120)
    export.add_argument("--annotators", type=int, default=3)
    export.add_argument("--ratings-per-package", type=int, default=3)
    export.add_argument("--seed", type=int, required=True)
    export.add_argument("--schema-version", default=SCHEMA_VERSION)
    export.add_argument("--dry-run", action="store_true")
    export.add_argument("--resume", action="store_true")
    load = sub.add_parser("import")
    load.add_argument("--input", type=Path, required=True)
    load.add_argument("--assignments", type=Path, required=True)
    load.add_argument("--output", type=Path, required=True)
    load.add_argument("--seed", type=int, required=True)
    load.add_argument("--schema-version", default=SCHEMA_VERSION)
    load.add_argument("--dry-run", action="store_true")
    load.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema version: {args.schema_version}")
    if args.command == "export":
        rows, manifest = export_assignments(
            read_jsonl(args.packages),
            episode_count=args.episodes,
            annotator_count=args.annotators,
            ratings_per_package=args.ratings_per_package,
            seed=args.seed,
        )
        if args.dry_run:
            print(json.dumps(manifest, sort_keys=True))
            return
        written = write_csv(args.output, rows, resume=args.resume)
        write_json(
            args.output.with_suffix(".manifest.json"),
            manifest,
            overwrite=args.resume,
        )
        print(
            json.dumps(
                {**manifest, "assignments_written": written, "output": str(args.output)},
                sort_keys=True,
            )
        )
        return
    completed = read_csv(args.input)
    expected = read_csv(args.assignments)
    normalized = import_annotations(completed, expected)
    config = {
        "input": str(args.input.resolve()),
        "assignments": str(args.assignments.resolve()),
        "seed": args.seed,
        "schema_version": args.schema_version,
    }
    summary = {
        "annotation_count": len(normalized),
        "completion_time_unit": "seconds",
        "config_hash": content_hash(config),
    }
    if args.dry_run:
        print(json.dumps(summary, sort_keys=True))
        return
    written = write_jsonl(
        args.output,
        normalized,
        resume_key="assignment_id" if args.resume else None,
    )
    write_json(
        args.output.with_suffix(".manifest.json"),
        {**summary, "config": config},
        overwrite=args.resume,
    )
    summary["annotations_written"] = written
    print(json.dumps({**summary, "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
