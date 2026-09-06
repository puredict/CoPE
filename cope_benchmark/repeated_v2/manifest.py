"""Method-independent master sessions, continuous trajectories, exact cell keys."""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .canonical import canonical_json, canonical_sha256, strict_loads, to_primitive
from .config import validate_config
from .scheduler import build_balanced_master_schedules
from .task_catalog import select_eligible_tasks

MANIFEST_VERSION = "cope-repeated-v2/master-manifest-1"


def information_conditions(config: Mapping[str, Any]) -> tuple[str, ...]:
    return (config["evidence"]["primary_condition"], config["evidence"]["secondary_condition"])


def expected_counts(task_count: int, config: Mapping[str, Any]) -> dict[str, Any]:
    """Counts are denominators, never observed outcomes or evidence of readiness."""
    if type(task_count) is not int or not 0 <= task_count <= 10:
        raise ValueError("task count must be an integer in [0,10]")
    errors = validate_config(config)
    if errors:
        raise ValueError("; ".join(errors))
    selection = config["task_selection"]
    masters = task_count * len(selection["formal_state_ids"]) * len(selection["formal_policy_seeds"])
    n_nonoracle = len(config["methods"]["non_oracle"])
    n_methods = n_nonoracle + len(config["methods"]["oracle"])
    protocols = {}
    for protocol, spec in config["protocols"].items():
        protocols[protocol] = {
            "master_sessions": masters,
            "method_trajectories": masters * n_methods,
            "non_oracle_trajectories": masters * n_nonoracle,
            "oracle_trajectories": masters * (n_methods - n_nonoracle),
            "event_cells": masters * n_methods * spec["event_count"],
            "non_oracle_event_cells": masters * n_nonoracle * spec["event_count"],
            "checkpoint_records": masters * n_methods * len(spec["checkpoints"]),
        }
    summed = {key: sum(p[key] for p in protocols.values()) for key in next(iter(protocols.values()))}
    # Both protocols refer to the SAME master specification; only trajectories double.
    summed["master_sessions"] = masters
    return {
        "task_count": task_count,
        "unique_master_sessions": masters,
        "information_conditions": list(information_conditions(config)),
        "per_condition": {"by_protocol": protocols, "total": summed},
        "all_conditions": {
            key: value if key == "master_sessions" else value * len(information_conditions(config))
            for key, value in summed.items()
        },
        "checkpoint_semantics": "prefixes_of_one_continuous_trajectory_per_protocol_condition_method",
    }


def build_manifest(config: Mapping[str, Any], catalog: Any, *, source_commit: str,
                   allow_synthetic: bool = False) -> list[dict[str, Any]]:
    errors = validate_config(config)
    if errors:
        raise ValueError("INVALID_PROTOCOL_CONFIG: " + "; ".join(errors))
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("source_commit must be a full git SHA")
    tasks = select_eligible_tasks(catalog, allow_synthetic=allow_synthetic)
    catalog_data = to_primitive(catalog.to_dict())
    catalog_hash = canonical_sha256(catalog_data)
    config_hash = canonical_sha256(config)
    specs, fields = [], []
    for task in sorted(tasks, key=lambda t: t.task_id):
        record = task.to_dict()
        for state_id in config["task_selection"]["formal_state_ids"]:
            digest = record["initial_state_digests"].get(str(state_id))
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(f"BLOCKED_TASK_CATALOG_GAPS: task {task.task_id} state {state_id} digest")
            for policy_seed in config["task_selection"]["formal_policy_seeds"]:
                pair = {"task_suite": "libero_10", "task_id": task.task_id,
                        "initial_state_id": state_id, "initial_state_sha256": digest,
                        "policy_seed": policy_seed, "master_seed": config["events"]["master_seed"]}
                episode_id = "rv2-" + canonical_sha256(pair)[:24]
                specs.append({"master_episode_id": episode_id,
                              "semantic_triggers": record["semantic_triggers"],
                              "supported_event_families": record["supported_event_families"]})
                fields.append(pair)
    schedules = build_balanced_master_schedules(specs, seed=config["events"]["master_seed"])
    rows = []
    schedule_by_id = {s.master_episode_id: s for s in schedules}
    for spec, pair in zip(specs, fields, strict=True):
        schedule = schedule_by_id[spec["master_episode_id"]]
        serialized = schedule.to_dict()
        row = {
            "schema_version": MANIFEST_VERSION,
            "master_episode_id": spec["master_episode_id"],
            "pair_fields": pair,
            "source_commit": source_commit,
            "config_sha256": config_hash,
            "task_catalog_sha256": catalog_hash,
            "provenance_kind": catalog_data["provenance_kind"],
            "master_schedule": serialized,
            "master_schedule_sha256": canonical_sha256(serialized),
            "protocol_prefixes": {p: {"event_count": s["event_count"], "checkpoints": s["checkpoints"]}
                                  for p, s in config["protocols"].items()},
            "methods": config["methods"],
            "information_conditions": list(information_conditions(config)),
        }
        row["row_sha256"] = canonical_sha256(row)
        rows.append(to_primitive(row))
    return rows


def validate_manifest(rows: Iterable[Mapping[str, Any]], config: Mapping[str, Any], catalog: Any,
                      *, source_commit: str, allow_synthetic: bool = False) -> dict[str, Any]:
    actual = list(rows)
    expected = build_manifest(config, catalog, source_commit=source_commit, allow_synthetic=allow_synthetic)
    errors = []
    ids = [r.get("master_episode_id") for r in actual]
    expected_ids = [r["master_episode_id"] for r in expected]
    duplicate = sorted(str(k) for k, v in Counter(ids).items() if v > 1)
    missing = sorted(set(expected_ids) - set(ids))
    unexpected = sorted(str(k) for k in set(ids) - set(expected_ids))
    if duplicate or missing or unexpected:
        errors.append("missing, duplicate, or unexpected master sessions")
    if canonical_json(actual) != canonical_json(expected):
        errors.append("manifest differs from deterministic catalog/config-derived manifest")
    return {"passed": not errors, "errors": errors, "master_sessions": len(actual),
            "missing": missing, "duplicate": duplicate, "unexpected": unexpected,
            "manifest_sha256": canonical_sha256(actual)}


def event_cell_keys(rows: Iterable[Mapping[str, Any]]) -> Iterable[str]:
    """Condition is a separate run namespace; K never enters an episode key."""
    for row in rows:
        for condition in row["information_conditions"]:
            for protocol, spec in row["protocol_prefixes"].items():
                for method in row["methods"]["non_oracle"] + row["methods"]["oracle"]:
                    for index in range(1, spec["event_count"] + 1):
                        yield f"{condition}/{protocol}/{row['master_episode_id']}/{method}/{index}"


def read_manifest(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines(keepends=True):
        if not line.endswith("\n") or not line.strip():
            raise ValueError("manifest has a torn or blank line")
        row = strict_loads(line)
        if not isinstance(row, dict):
            raise ValueError("manifest row is not an object")
        rows.append(row)
    return rows


def write_manifest(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> str:
    """Exclusive output creation: never overwrite an experiment artifact."""
    data = "".join(canonical_json(row) + "\n" for row in rows).encode("utf-8")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)
    return hashlib.sha256(data).hexdigest()
