from __future__ import annotations

import copy
import csv
from pathlib import Path
from typing import Any

from cope.native_ntrack import NativeCase, NativeOutputError, build_case


def _noise_commitment(base_case_id: str, variant_index: int, item_index: int) -> dict[str, Any]:
    suffix = f"{base_case_id}:v{variant_index}:n{item_index}"
    return {
        "id": f"deliver:noise:{suffix}",
        "predicate": "deliver",
        "grounding": [f"noise_object:{suffix}", "dock"],
        "lifecycle_status": "satisfied",
        "source": "task_owner",
        "owner": "task_owner",
        "authority": 100,
        "valid_from": f"history:{suffix}",
        "valid_until": "task_end",
        "dependencies": [],
        "support_links": [],
        "override_links": [],
        "supersession_links": [],
    }


def build_fresh_case(
    case_id: str,
    base_case_id: str,
    variant_index: int,
    phase: str,
    family: str,
    source: str,
) -> NativeCase:
    if variant_index not in range(1, 6):
        raise NativeOutputError("fresh variant index must be in 1..5")
    base = build_case(base_case_id, phase, family, source)
    state = copy.deepcopy(base.pre_state)
    event = copy.deepcopy(base.event)
    version = 10 + variant_index
    pre_world_version = 1000 + 10 * variant_index
    state["state_version"] = version
    state["evidence_versions"] = {
        "event_id": f"fresh:genesis:{base_case_id}:v{variant_index}",
        "world_version": pre_world_version,
        "input_state_version": version,
    }
    event["event_id"] = f"fresh:event:{base_case_id}:v{variant_index}"
    event["world_version"] = pre_world_version + 1
    event["input_state_version"] = version - 1 if base_case_id == "stale_version" else version
    state["action_history"] = [
        {
            "action_id": f"history:{base_case_id}:v{variant_index}:a{index}",
            "status": "completed",
            "effect": f"irrelevant_context_{index}",
        }
        for index in range(variant_index)
    ]
    noise_ids = []
    for item_index in range(1, variant_index + 1):
        commitment = _noise_commitment(base_case_id, variant_index, item_index)
        object_id = commitment["grounding"][0]
        commitment_id = commitment["id"]
        noise_ids.append(commitment_id)
        state["entities"].append({"id": object_id, "kind": "object"})
        state["commitments"].append(commitment)
        state["current_goal"]["all"].append(
            {"predicate": "deliver", "arguments": [object_id, "dock"]}
        )
        state["progress_ledger"].append(
            {
                "milestone_id": commitment_id,
                "achieved": True,
                "physically_valid": True,
                "still_goal_relevant": True,
            }
        )
    target = next(row for row in state["commitments"] if row["id"] == "deliver:b")
    target["valid_until"] = f"deadline:{base_case_id}:v{variant_index}"
    if variant_index >= 3:
        target["dependencies"] = [noise_ids[0]]
    return NativeCase(case_id, phase, family, source, state, event)


def load_fresh_manifest(path: Path) -> list[NativeCase]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    required = {"case_id", "base_case_id", "variant_index", "phase", "family", "source"}
    if not rows or set(rows[0]) != required:
        raise NativeOutputError("fresh manifest columns are not exact")
    cases = [
        build_fresh_case(
            row["case_id"], row["base_case_id"], int(row["variant_index"]),
            row["phase"], row["family"], row["source"],
        )
        for row in rows
    ]
    if len(cases) != 60 or len({case.case_id for case in cases}) != 60:
        raise NativeOutputError("fresh manifest must contain 60 unique cases")
    return cases
