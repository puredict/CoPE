from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Iterable

from auditability import SCHEMA_VERSION
from auditability.common import (
    content_hash,
    is_parseable_id,
    read_json,
    read_jsonl,
    stable_id,
    write_json,
)


def _record_id(namespace: str, record: dict[str, Any], episode_id: str, index: int) -> str:
    for key in ("id", f"{namespace}_id"):
        value = record.get(key)
        if is_parseable_id(value):
            return str(value)
    return stable_id(namespace, episode_id, index, record)


def _normalize_records(
    records: Iterable[dict[str, Any]], namespace: str, episode_id: str
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, source in enumerate(records):
        record = copy.deepcopy(source)
        record["id"] = _record_id(namespace, record, episode_id, index)
        if "policy_step" not in record:
            if isinstance(record.get("step"), (int, float)):
                record["policy_step"] = int(record["step"])
            elif isinstance(record.get("environment_step"), (int, float)):
                record["policy_step"] = int(record["environment_step"])
            else:
                record["policy_step"] = index
        normalized.append(record)
    return normalized


def _infer_episode_id(source: dict[str, Any], origin: str) -> str:
    nested_metadata = (
        source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    )
    value = (
        source.get("episode_id")
        or source.get("run_id")
        or nested_metadata.get("episode_id")
        or nested_metadata.get("run_id")
    )
    if is_parseable_id(value):
        return str(value)
    pair_key = source.get("pair_key") or {
        "task": source.get("task_id"),
        "initial_state": source.get("initial_state_id", source.get("trial_id")),
        "seed": source.get("seed"),
        "mode": source.get("mode", source.get("condition")),
    }
    return stable_id("episode", origin, pair_key)


def _metadata(source: dict[str, Any], episode_id: str, origin: str) -> dict[str, Any]:
    method = source.get("method", source.get("mode", source.get("condition", "unknown")))
    success = source.get("success")
    status = source.get("status") or source.get("termination_reason")
    if success is None and isinstance(source.get("episode_status"), dict):
        success = source["episode_status"].get("success")
        status = status or source["episode_status"].get("status")
    interruption_count = source.get("interruption_count")
    if interruption_count is None:
        interruption_count = int(bool(source.get("disturbance")))
    return {
        "episode_id": episode_id,
        "method": str(method),
        "task": str(
            source.get("task_description")
            or source.get("task")
            or source.get("task_id")
            or "unknown"
        ),
        "task_id": source.get("task_id"),
        "success": bool(success) if success is not None else None,
        "status": status,
        "event_type": source.get("event_type", "disturbance" if interruption_count else "none"),
        "interruption_kind": "repeated" if int(interruption_count or 0) > 1 else "single",
        "interruption_count": int(interruption_count or 0),
        "failure_layer": source.get("failure_layer"),
        "input_origin": origin,
        "input_commit": source.get("input_commit")
        or source.get("git_commit")
        or source.get("commit")
        or "unknown",
        "input_config_hash": source.get("input_config_hash")
        or source.get("config_hash")
        or "unknown",
        "input_schema_version": source.get("schema_version", "legacy.unspecified"),
        "synthetic": bool(source.get("synthetic", False)),
    }


def adapt_episode(source: dict[str, Any], *, origin: str = "<memory>") -> dict[str, Any]:
    """Normalize a formal v1 record or a legacy episode summary.

    Unknown upstream fields are preserved under ``extensions``.  That is the
    explicit forward-compatibility mechanism for the state-semantics branch.
    """

    if not isinstance(source, dict):
        raise TypeError("episode source must be a JSON object")
    if (
        source.get("schema_version") == SCHEMA_VERSION
        and isinstance(source.get("metadata"), dict)
        and isinstance(source.get("raw"), dict)
        and isinstance(source.get("cope"), dict)
    ):
        normalized = copy.deepcopy(source)
        if not is_parseable_id(normalized.get("episode_id")):
            raise ValueError("auditability.v1 episode requires a parseable episode_id")
        normalized["adapter_hash"] = content_hash(
            {
                key: value
                for key, value in normalized.items()
                if key != "adapter_hash"
            }
        )
        return normalized
    episode_id = _infer_episode_id(source, origin)
    metadata_source = copy.deepcopy(
        source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    )
    metadata_source.update(
        {key: value for key, value in source.items() if value is not None}
    )
    raw = source.get("raw") if isinstance(source.get("raw"), dict) else {}
    cope = source.get("cope") if isinstance(source.get("cope"), dict) else {}
    regeneration = (
        source.get("regeneration") if isinstance(source.get("regeneration"), dict) else {}
    )

    events = raw.get("events", source.get("events", []))
    actions = raw.get("actions", source.get("actions", []))
    if not isinstance(events, list) or not isinstance(actions, list):
        raise ValueError("events and actions must be lists")

    slots = cope.get("slots", source.get("slots", []))
    states = cope.get("states", source.get("states", []))
    patches = cope.get("patches", source.get("patches", []))
    validators = cope.get(
        "validator_outputs", source.get("validator_outputs", source.get("validations", []))
    )
    plans = regeneration.get(
        "snapshots",
        source.get("regeneration_snapshots", source.get("full_regeneration_outputs", [])),
    )

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "metadata": _metadata(metadata_source, episode_id, origin),
        "raw": {
            "events": _normalize_records(events, "event", episode_id),
            "actions": _normalize_records(actions, "action", episode_id),
            "observation_summaries": copy.deepcopy(
                raw.get("observation_summaries", source.get("observation_summaries", []))
            ),
        },
        "regeneration": {
            "snapshots": _normalize_records(
                plans if isinstance(plans, list) else [], "regen", episode_id
            )
        },
        "cope": {
            "slots": _normalize_records(
                slots if isinstance(slots, list) else [], "slot", episode_id
            ),
            "states": _normalize_records(
                states if isinstance(states, list) else [], "state", episode_id
            ),
            "patches": _normalize_records(
                patches if isinstance(patches, list) else [], "patch", episode_id
            ),
            "validator_outputs": _normalize_records(
                validators if isinstance(validators, list) else [], "validation", episode_id
            ),
        },
        "controller_status": copy.deepcopy(
            source.get("controller_status", source.get("episode_status", {}))
        ),
        "task_progress": copy.deepcopy(source.get("task_progress", [])),
        "extensions": copy.deepcopy(source.get("extensions", {})),
    }
    normalized["adapter_hash"] = content_hash(
        {key: value for key, value in normalized.items() if key != "adapter_hash"}
    )
    return normalized


def load_episode(path: Path) -> dict[str, Any]:
    if path.is_dir():
        summary_path = path / "episode_summary.json"
        if not summary_path.exists():
            raise FileNotFoundError(f"episode directory lacks episode_summary.json: {path}")
        source = read_json(summary_path)
        for field, filename in (("events", "events.jsonl"), ("actions", "actions.jsonl")):
            data_path = path / filename
            if data_path.exists():
                source[field] = read_jsonl(data_path)
        return adapt_episode(source, origin=str(path.resolve()))
    source = read_json(path)
    return adapt_episode(source, origin=str(path.resolve()))


def iter_episode_sources(path: Path) -> list[dict[str, Any]]:
    if path.is_file() and path.suffix == ".jsonl":
        return [
            adapt_episode(row, origin=f"{path.resolve()}#{index}")
            for index, row in enumerate(read_jsonl(path), start=1)
        ]
    if path.is_file():
        return [load_episode(path)]
    if (path / "episode_summary.json").exists():
        return [load_episode(path)]
    episodes: list[dict[str, Any]] = []
    for candidate in sorted(path.rglob("episode_summary.json")):
        episodes.append(load_episode(candidate.parent))
    for candidate in sorted(path.glob("*.json")):
        episodes.append(load_episode(candidate))
    return episodes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Adapt one trace into auditability.v1.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--schema-version", default=SCHEMA_VERSION)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported output schema: {args.schema_version}")
    episode = load_episode(args.input)
    summary = {
        "episode_id": episode["episode_id"],
        "schema_version": SCHEMA_VERSION,
        "adapter_hash": episode["adapter_hash"],
    }
    if args.dry_run:
        print(json.dumps(summary, sort_keys=True))
        return
    write_json(args.output, episode)
    print(json.dumps({**summary, "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
