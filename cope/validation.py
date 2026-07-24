from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from cope.types import DISTURBED_METHODS, METHOD_NAMES, PATCH_OPERATION_TYPES, stable_hash


REQUIRED_EPISODE_FIELDS: tuple[str, ...] = (
    "schema_version",
    "run_id",
    "pair_key",
    "task_id",
    "initial_state_id",
    "seed",
    "method",
    "event_source",
    "information_budget",
    "event",
    "policy_step_budget",
    "steps_before_event",
    "steps_after_event",
    "high_level_call_count",
    "prompt_tokens",
    "completion_tokens",
    "constraint_state_before",
    "constraint_state_after",
    "patch_operations",
    "revalidation_result",
    "task_progress",
    "success",
    "termination_reason",
    "safety_violation",
    "manual_intervention",
    "git_commit",
    "config_hash",
    "checkpoint_id",
    "test_only",
    "artifact_paths",
    "artifact_alignment",
    "initial_state_hash",
    "pre_event_action_digest",
    "provider_fairness_fingerprint",
    "prompt_template_hash",
)


def _same(records: list[dict[str, Any]], field: str, errors: list[str]) -> None:
    values = [record.get(field) for record in records]
    fingerprints = [stable_hash(value) for value in values]
    if len(set(fingerprints)) != 1:
        errors.append(f"{field} mismatch across methods")


def validate_episode_record(record: dict[str, Any], *, check_artifacts: bool = False) -> list[str]:
    errors: list[str] = []
    missing = [field for field in REQUIRED_EPISODE_FIELDS if field not in record]
    if missing:
        errors.append(f"missing required episode fields: {missing}")
    method = record.get("method")
    if method not in METHOD_NAMES:
        errors.append(f"unknown method {method!r}")
    if record.get("manual_intervention") is not False:
        errors.append("manual interaction is forbidden from autonomous records")
    if record.get("success") and record.get("termination_reason") == "timeout":
        errors.append("timeout cannot count as success")
    if int(record.get("reset_count", 0)) != 0 or int(record.get("rollback_count", 0)) != 0:
        errors.append("ranked methods cannot use reset or rollback")
    if int(record.get("high_level_call_count", 0)) > int(
        (record.get("information_budget") or {}).get("max_high_level_calls", -1)
    ):
        errors.append("high-level call ceiling exceeded")
    if int(record.get("prompt_tokens", 0)) > int(
        (record.get("information_budget") or {}).get("max_prompt_tokens", -1)
    ):
        errors.append("prompt token ceiling exceeded")
    if int(record.get("completion_tokens", 0)) > int(
        (record.get("information_budget") or {}).get("max_completion_tokens", -1)
    ):
        errors.append("completion token ceiling exceeded")
    if int(record.get("steps_before_event", 0)) + int(record.get("steps_after_event", 0)) != int(
        record.get("policy_steps", -1)
    ):
        errors.append("pre/post-event steps do not sum to policy_steps")
    actions = record.get("actions")
    if not isinstance(actions, list):
        errors.append("actions must be a list")
    else:
        if len(actions) != int(record.get("policy_steps", -1)):
            errors.append("action record count does not match policy_steps")
        steps = [action.get("policy_step") for action in actions if isinstance(action, dict)]
        if steps != list(range(len(actions))):
            errors.append("action policy_step indices are not contiguous")
        frames = [action.get("video_frame_index") for action in actions if isinstance(action, dict)]
        if frames != list(range(len(actions))):
            errors.append("video/action step alignment is invalid")
    alignment = record.get("artifact_alignment") or {}
    if (
        alignment.get("aligned") is not True
        or int(alignment.get("action_records", -1)) != int(record.get("policy_steps", -2))
        or int(alignment.get("video_frames", -1)) != int(record.get("policy_steps", -2))
    ):
        errors.append("declared JSONL/video/action alignment is invalid")
    if method in {"history_augmented_full_regeneration", "cope_patch"}:
        detected_miss = record.get("event_source") == "detected" and record.get("event") is None
        expected_calls = 0 if detected_miss else 1
        if int(record.get("high_level_call_count", 0)) != expected_calls:
            errors.append(f"{method} must make exactly {expected_calls} high-level call(s)")
        calls = record.get("provider_calls")
        if not isinstance(calls, list) or len(calls) != expected_calls:
            errors.append(f"{method} must retain exactly {expected_calls} raw provider call(s)")
        if not detected_miss and not record.get("recovery_input_hash"):
            errors.append(f"{method} is missing recovery_input_hash")
    else:
        if int(record.get("high_level_call_count", 0)) != 0:
            errors.append(f"{method} must not make a high-level call")
    if (
        method == "history_augmented_full_regeneration"
        and not (record.get("event_source") == "detected" and record.get("event") is None)
        and not record.get("regenerated_state")
    ):
        errors.append("full regeneration must retain parsed regenerated state")
    if method == "cope_patch" and not (
        record.get("event_source") == "detected" and record.get("event") is None
    ):
        if record.get("constraint_state_before") is None or record.get("constraint_state_after") is None:
            errors.append("CoPE must retain before/after constraint state")
        preservation = record.get("unaffected_slot_preservation") or {}
        if preservation.get("passed") is not True:
            errors.append("CoPE did not prove unaffected-slot preservation")
        successful: set[str] = set()
        for operation in record.get("patch_operations") or []:
            if operation.get("op") not in PATCH_OPERATION_TYPES:
                errors.append(f"unknown patch operation {operation.get('op')!r}")
            target_id = operation.get("target_id")
            if operation.get("op") == "Revalidate":
                result = (operation.get("payload") or {}).get("result") or {}
                if result.get("success") is True and target_id:
                    successful.add(str(target_id))
            if operation.get("op") == "Restore" and target_id not in successful:
                errors.append(f"blind restore found for {target_id!r}")
    if check_artifacts:
        artifact_paths = record.get("artifact_paths") or {}
        for name in ("actions", "events", "raw_video", "episode"):
            path = artifact_paths.get(name)
            if not path or not Path(path).exists():
                errors.append(f"missing artifact {name}: {path!r}")
        actions_path = artifact_paths.get("actions")
        if actions_path and Path(actions_path).exists():
            line_count = sum(1 for line in Path(actions_path).read_text(encoding="utf-8").splitlines() if line)
            if line_count != int(record.get("policy_steps", -1)):
                errors.append("actions.jsonl line count does not match policy_steps")
        raw_video = artifact_paths.get("raw_video")
        if raw_video and Path(raw_video).exists() and not record.get("test_only"):
            try:
                import imageio.v2 as imageio

                reader = imageio.get_reader(raw_video)
                try:
                    video_frames = int(reader.count_frames())
                finally:
                    reader.close()
                if video_frames != int(record.get("policy_steps", -1)):
                    errors.append("raw video frame count does not match policy_steps")
            except Exception as exc:
                errors.append(f"could not verify raw video frame count: {type(exc).__name__}: {exc}")
    return errors


def validate_pair_records(
    records: Iterable[dict[str, Any]],
    *,
    check_artifacts: bool = False,
) -> dict[str, Any]:
    rows = list(records)
    errors: list[str] = []
    warnings: list[str] = []
    methods = [row.get("method") for row in rows]
    if methods != list(METHOD_NAMES):
        errors.append(f"expected exact method order {list(METHOD_NAMES)}, got {methods}")
    if len(rows) != len(METHOD_NAMES):
        return {"passed": False, "errors": errors, "warnings": warnings}
    for row in rows:
        errors.extend(f"{row.get('method')}: {error}" for error in validate_episode_record(row, check_artifacts=check_artifacts))

    for field in (
        "pair_key",
        "task_id",
        "initial_state_id",
        "seed",
        "checkpoint_id",
        "checkpoint_sha256",
        "config_hash",
        "git_commit",
        "initial_state_hash",
        "pre_event_action_digest",
        "policy_step_budget",
        "post_event_policy_step_budget",
        "information_budget",
        "provider_fairness_fingerprint",
        "prompt_template_hash",
        "downstream_controller",
        "success_definition",
        "termination_definition",
    ):
        _same(rows, field, errors)

    disturbed = [row for row in rows if row.get("method") in DISTURBED_METHODS]
    for field in ("event_source", "event", "disturbance_step", "fresh_observation_hash"):
        _same(disturbed, field, errors)
    if all(row.get("event_source") == "detected" for row in disturbed):
        _same(disturbed, "detector", errors)
    recovery_hashes = [row.get("recovery_input_hash") for row in disturbed]
    detected_miss = (
        all(row.get("event_source") == "detected" for row in disturbed)
        and all(row.get("event") is None for row in disturbed)
    )
    if len(set(recovery_hashes)) != 1 or (not recovery_hashes[0] and not detected_miss):
        errors.append("all disturbed methods must record the exact same common recovery input hash")

    provider_rows = [
        row for row in rows if row.get("method") in {"history_augmented_full_regeneration", "cope_patch"}
    ]
    _same(provider_rows, "provider_metadata", errors)
    if any(row.get("event_source") == "oracle" and (row.get("event") or {}).get("simulator_truth") for row in disturbed):
        errors.append("oracle event packet exceeds the preregistered event information budget")

    return {"passed": not errors, "errors": errors, "warnings": warnings}


def validate_run_records(
    records: Iterable[dict[str, Any]],
    *,
    check_artifacts: bool = False,
) -> dict[str, Any]:
    rows = list(records)
    grouped: dict[str, list[dict[str, Any]]] = {}
    duplicates: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row.get("pair_key")), str(row.get("method")))
        if key in seen:
            duplicates.append(key)
        seen.add(key)
        grouped.setdefault(key[0], []).append(row)
    errors = [f"duplicate episode key {key}" for key in duplicates]
    pair_results: dict[str, Any] = {}
    for pair_key, pair_rows in grouped.items():
        ordered = sorted(pair_rows, key=lambda row: METHOD_NAMES.index(row["method"]) if row.get("method") in METHOD_NAMES else 999)
        result = validate_pair_records(ordered, check_artifacts=check_artifacts)
        pair_results[pair_key] = result
        errors.extend(f"{pair_key}: {error}" for error in result["errors"])
    method_counts = Counter(str(row.get("method")) for row in rows)
    return {
        "passed": not errors,
        "errors": errors,
        "pair_results": pair_results,
        "pair_count": len(grouped),
        "episode_count": len(rows),
        "method_counts": dict(method_counts),
    }


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected object")
            rows.append(value)
    return rows
