from __future__ import annotations

import copy
import random
import re
from typing import Any

from auditability.common import stable_id


INTERNAL_CONDITIONS = ("raw", "regeneration", "typed_patch")
PATH_KEYS = {
    "path",
    "file",
    "filename",
    "episode_dir",
    "artifact_paths",
    "input_origin",
}
METHOD_KEYS = {"method", "condition", "recovery_mode"}


def _redact_text(value: str, forbidden_values: set[str]) -> str:
    text = re.sub(r"\bcope\b", "[system]", value, flags=re.IGNORECASE)
    for forbidden in sorted(forbidden_values, key=len, reverse=True):
        if not forbidden:
            continue
        text = re.sub(re.escape(forbidden), "[method]", text, flags=re.IGNORECASE)
    return text


def _scrub(value: Any, forbidden_values: set[str]) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, child in value.items():
            lowered = key.lower()
            if lowered in PATH_KEYS or lowered in METHOD_KEYS:
                continue
            clean[key] = _scrub(child, forbidden_values)
        return clean
    if isinstance(value, list):
        return [_scrub(child, forbidden_values) for child in value]
    if isinstance(value, str):
        return _redact_text(value, forbidden_values)
    return copy.deepcopy(value)


def condition_codes(episode_id: str, seed: int) -> dict[str, str]:
    labels = ["C00", "C01", "C02"]
    rng = random.Random(f"{seed}:{episode_id}")
    rng.shuffle(labels)
    return dict(zip(INTERNAL_CONDITIONS, labels))


def build_evidence(episode: dict[str, Any], internal_condition: str) -> dict[str, Any]:
    if internal_condition not in INTERNAL_CONDITIONS:
        raise ValueError(f"unknown evidence condition: {internal_condition}")
    method = str(episode["metadata"].get("method") or "")
    forbidden = {method, "typed_patch", "raw_trace", "full_regeneration"}
    evidence: dict[str, Any] = {
        "task": episode["metadata"].get("task"),
        "records": {
            "events": episode["raw"]["events"],
            "actions": episode["raw"]["actions"],
            "observation_summaries": episode["raw"].get("observation_summaries", []),
        },
    }
    if internal_condition == "regeneration":
        evidence["structured_records"] = {
            "snapshots": episode["regeneration"]["snapshots"],
        }
    elif internal_condition == "typed_patch":
        evidence["structured_records"] = {
            "states": episode["cope"]["states"],
            "patches": episode["cope"]["patches"],
            "slots": episode["cope"]["slots"],
            "validator_outputs": episode["cope"]["validator_outputs"],
        }
    return _scrub(evidence, forbidden)


def make_packages(
    episode: dict[str, Any],
    questions: list[dict[str, Any]],
    *,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    codes = condition_codes(episode["episode_id"], seed)
    packages: list[dict[str, Any]] = []
    key_rows: list[dict[str, Any]] = []
    for internal_condition, label in codes.items():
        evidence = build_evidence(episode, internal_condition)
        key_rows.append(
            {
                "key_id": stable_id(
                    "conditionkey", episode["episode_id"], label, seed
                ),
                "episode_id": episode["episode_id"],
                "condition_label": label,
                "internal_condition": internal_condition,
            }
        )
        for question in questions:
            package_id = stable_id(
                "package", question["item_id"], internal_condition, seed
            )
            packages.append(
                {
                    "schema_version": episode["schema_version"],
                    "package_id": package_id,
                    "item_id": question["item_id"],
                    "episode_id": episode["episode_id"],
                    "condition_label": label,
                    "question_kind": question["question_kind"],
                    "question": question["question"],
                    "evidence": evidence,
                }
            )
    return packages, key_rows


def find_blinding_leaks(package: dict[str, Any]) -> list[str]:
    text = str(package).lower()
    leaks = []
    for token in ("cope", "typed_patch", "full_regeneration", "raw_trace"):
        if re.search(rf"\b{re.escape(token)}\b", text):
            leaks.append(token)
    evidence = package.get("evidence", {})
    if isinstance(evidence, dict):
        records = evidence.get("records", {})
        for record_type in ("events", "actions"):
            for record in records.get(record_type, []) if isinstance(records, dict) else []:
                if any(key in record for key in METHOD_KEYS):
                    leaks.append(f"field:{record_type}.method")
    return sorted(set(leaks))
