from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from auditability import SCHEMA_VERSION
from auditability.blinding import find_blinding_leaks, make_packages
from auditability.common import content_hash, write_json, write_jsonl
from auditability.question_generator import generate_questions
from auditability.schema_adapter import iter_episode_sources


def _episode_stratum(episode: dict[str, Any]) -> tuple[Any, ...]:
    metadata = episode["metadata"]
    ops = {str(patch.get("op", "")).lower() for patch in episode["cope"]["patches"]}
    return (
        metadata.get("method"),
        metadata.get("success"),
        metadata.get("task_id", metadata.get("task")),
        metadata.get("event_type"),
        metadata.get("interruption_kind"),
        metadata.get("failure_layer"),
        "restore" in ops,
        "override" in ops,
        "expire" in ops,
    )


def stratified_sample(
    episodes: list[dict[str, Any]], target_episodes: int
) -> list[dict[str, Any]]:
    if target_episodes <= 0:
        raise ValueError("target_episodes must be positive")
    unique: dict[str, dict[str, Any]] = {}
    for episode in episodes:
        unique.setdefault(episode["episode_id"], episode)
    buckets: dict[tuple[Any, ...], deque[dict[str, Any]]] = defaultdict(deque)
    for episode in sorted(unique.values(), key=lambda row: row["episode_id"]):
        buckets[_episode_stratum(episode)].append(episode)
    selected: list[dict[str, Any]] = []
    keys = sorted(buckets, key=lambda value: repr(value))
    while keys and len(selected) < min(target_episodes, len(unique)):
        next_keys = []
        for key in keys:
            if len(selected) >= target_episodes:
                break
            if buckets[key]:
                selected.append(buckets[key].popleft())
            if buckets[key]:
                next_keys.append(key)
        keys = next_keys
    return selected


def validate_input_provenance(
    episodes: list[dict[str, Any]], *, data_kind: str
) -> None:
    if not episodes:
        raise ValueError("no episodes found")
    synthetic = {bool(row["metadata"].get("synthetic")) for row in episodes}
    expected = {data_kind == "synthetic"}
    if synthetic != expected:
        raise ValueError(
            f"{data_kind} corpus cannot mix or mislabel synthetic inputs: observed {synthetic}"
        )
    if data_kind == "formal":
        missing = []
        for episode in episodes:
            metadata = episode["metadata"]
            for field in ("input_commit", "input_config_hash", "input_schema_version"):
                if metadata.get(field) in {None, "", "unknown", "legacy.unspecified"}:
                    missing.append(f"{episode['episode_id']}:{field}")
        if missing:
            raise ValueError(
                "formal inputs require commit/config/schema provenance; missing "
                + ", ".join(missing[:20])
            )


def build_corpus(
    inputs: list[Path],
    *,
    target_episodes: int,
    seed: int,
    schema_version: str,
    data_kind: str,
    allow_incomplete: bool = False,
) -> dict[str, Any]:
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema version: {schema_version}")
    episodes: list[dict[str, Any]] = []
    for path in inputs:
        episodes.extend(iter_episode_sources(path))
    validate_input_provenance(episodes, data_kind=data_kind)
    unique_episode_count = len({row["episode_id"] for row in episodes})
    if (
        data_kind == "formal"
        and unique_episode_count < target_episodes
        and not allow_incomplete
    ):
        raise ValueError(
            f"formal corpus requires {target_episodes} episodes but only "
            f"{unique_episode_count} are available; use --allow-incomplete only "
            "for a clearly labeled pilot"
        )
    selected = stratified_sample(episodes, target_episodes)
    questions: list[dict[str, Any]] = []
    packages: list[dict[str, Any]] = []
    key_rows: list[dict[str, Any]] = []
    for episode in selected:
        episode_questions = generate_questions(episode)
        episode_packages, episode_keys = make_packages(
            episode, episode_questions, seed=seed
        )
        questions.extend(episode_questions)
        packages.extend(episode_packages)
        key_rows.extend(episode_keys)
    leaks = {
        package["package_id"]: find_blinding_leaks(package)
        for package in packages
        if find_blinding_leaks(package)
    }
    if leaks:
        first_id = sorted(leaks)[0]
        raise ValueError(f"blinding leak in {first_id}: {leaks[first_id]}")
    config = {
        "inputs": [str(path.resolve()) for path in inputs],
        "target_episodes": target_episodes,
        "seed": seed,
        "schema_version": schema_version,
        "data_kind": data_kind,
        "allow_incomplete": allow_incomplete,
    }
    input_provenance = sorted(
        {
            (
                row["metadata"].get("input_commit"),
                row["metadata"].get("input_config_hash"),
                row["metadata"].get("input_schema_version"),
            )
            for row in selected
        },
        key=repr,
    )
    return {
        "episodes": selected,
        "questions": questions,
        "packages": packages,
        "condition_key": key_rows,
        "manifest": {
            "schema_version": schema_version,
            "data_kind": data_kind,
            "formal_evaluation_status": (
                "pending"
                if data_kind == "synthetic"
                else "pilot_incomplete"
                if len(selected) < target_episodes
                else "ready"
            ),
            "config": config,
            "config_hash": content_hash(config),
            "available_episode_count": unique_episode_count,
            "selected_episode_count": len(selected),
            "qa_item_count": len(questions),
            "evidence_package_count": len(packages),
            "condition_count": 3,
            "synthetic_episode_count": sum(
                bool(row["metadata"].get("synthetic")) for row in selected
            ),
            "real_episode_count": sum(
                not bool(row["metadata"].get("synthetic")) for row in selected
            ),
            "input_provenance": [
                {
                    "input_commit": commit,
                    "input_config_hash": config_hash,
                    "input_schema_version": input_schema,
                }
                for commit, config_hash, input_schema in input_provenance
            ],
        },
    }


def write_corpus(
    result: dict[str, Any],
    output_dir: Path,
    *,
    resume: bool,
) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {
        "episodes_written": write_jsonl(
            output_dir / "episodes.jsonl",
            result["episodes"],
            resume_key="episode_id" if resume else None,
        ),
        "questions_written": write_jsonl(
            output_dir / "questions.jsonl",
            result["questions"],
            resume_key="item_id" if resume else None,
        ),
        "packages_written": write_jsonl(
            output_dir / "packages.jsonl",
            result["packages"],
            resume_key="package_id" if resume else None,
        ),
        "condition_keys_written": write_jsonl(
            output_dir / "condition_key.private.jsonl",
            result["condition_key"],
            resume_key="key_id" if resume else None,
        ),
    }
    write_json(output_dir / "manifest.json", result["manifest"], overwrite=resume)
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the blinded auditability corpus.")
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target-episodes", type=int, default=300)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--schema-version", default=SCHEMA_VERSION)
    parser.add_argument("--data-kind", choices=("formal", "synthetic"), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_corpus(
        args.input,
        target_episodes=args.target_episodes,
        seed=args.seed,
        schema_version=args.schema_version,
        data_kind=args.data_kind,
        allow_incomplete=args.allow_incomplete,
    )
    if args.dry_run:
        print(json.dumps(result["manifest"], sort_keys=True))
        return
    counts = write_corpus(result, args.output_dir, resume=args.resume)
    print(
        json.dumps(
            {**result["manifest"], **counts, "output_dir": str(args.output_dir)},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
