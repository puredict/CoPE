from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from auditability import SCHEMA_VERSION
from auditability.common import FAILURE_LAYERS, numeric_step, stable_id, write_json
from auditability.schema_adapter import load_episode


QUESTION_KINDS = (
    "behavior_change_reason",
    "constraint_override",
    "preference_persistence",
    "restore_revalidation",
    "alignment_freshness",
    "earliest_failure_layer",
)


def _event_name(record: dict[str, Any]) -> str:
    return str(record.get("event") or record.get("type") or record.get("name") or "").lower()


def _payload_value(record: dict[str, Any], *keys: str) -> Any:
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    for key in keys:
        if record.get(key) is not None:
            return record[key]
        if payload.get(key) is not None:
            return payload[key]
    return None


def _answer(
    episode: dict[str, Any],
    kind: str,
    normalized_answer: str | None,
    supporting: list[dict[str, Any]],
    *,
    failure_layer: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for support in supporting:
        support_id = support.get("id")
        if not isinstance(support_id, str) or support_id in seen:
            continue
        seen.add(support_id)
        unique.append(
            {
                "id": support_id,
                "policy_step": numeric_step(support),
                "record_type": support_id.split(":", 1)[0],
            }
        )
    answerable = normalized_answer is not None and bool(unique)
    metadata = episode["metadata"]
    return {
        "question_kind": kind,
        "normalized_answer": normalized_answer if answerable else "unanswerable",
        "supporting_ids": [item["id"] for item in unique],
        "supporting_locations": unique,
        "failure_layer": failure_layer,
        "answerability": "answerable" if answerable else "unanswerable_from_ground_truth",
        "provenance": {
            "extractor": "auditability.ground_truth.v1",
            "episode_id": episode["episode_id"],
            "input_commit": metadata.get("input_commit", "unknown"),
            "input_config_hash": metadata.get("input_config_hash", "unknown"),
            "input_schema_version": metadata.get("input_schema_version", "unknown"),
            "synthetic": bool(metadata.get("synthetic")),
            "rule_id": f"gt:{kind}",
            "note": note,
        },
    }


def _behavior_change(episode: dict[str, Any]) -> dict[str, Any]:
    candidates = []
    tokens = ("pause", "stop", "change", "switch", "disturbance", "override", "expire")
    for event in episode["raw"]["events"]:
        if any(token in _event_name(event) for token in tokens):
            candidates.append(event)
    candidates.sort(key=lambda row: (numeric_step(row), str(row["id"])))
    for event in candidates:
        reason = _payload_value(
            event,
            "reason",
            "termination_reason",
            "change_reason",
            "trigger",
            "cause",
        )
        cause_id = _payload_value(event, "caused_by", "source_event_id", "event_id")
        supporting = [event]
        for candidate in episode["raw"]["events"]:
            if candidate["id"] == cause_id:
                supporting.append(candidate)
                break
        if reason is not None:
            return _answer(
                episode,
                "behavior_change_reason",
                str(reason).strip().lower(),
                supporting,
            )
    return _answer(episode, "behavior_change_reason", None, candidates[:1])


def _constraint_override(episode: dict[str, Any]) -> dict[str, Any]:
    patches = sorted(
        episode["cope"]["patches"], key=lambda row: (numeric_step(row), str(row["id"]))
    )
    for patch in patches:
        op = str(patch.get("op") or patch.get("operation") or "").lower()
        if op not in {"override", "suspend", "expire"}:
            continue
        target = patch.get("target_slot_id") or patch.get("slot_id")
        actor = (
            patch.get("by_slot_id")
            or patch.get("source_event_id")
            or patch.get("constraint_id")
        )
        if target and actor:
            support = [patch]
            for slot in episode["cope"]["slots"]:
                if slot["id"] in {target, actor}:
                    support.append(slot)
            for event in episode["raw"]["events"]:
                if event["id"] == actor:
                    support.append(event)
            return _answer(
                episode,
                "constraint_override",
                f"{target} {op} by {actor}",
                support,
            )
    return _answer(episode, "constraint_override", None, [])


def _preference_persistence(episode: dict[str, Any]) -> dict[str, Any]:
    preferences = [
        slot
        for slot in episode["cope"]["slots"]
        if str(slot.get("kind") or slot.get("type") or "").lower()
        in {"user_preference", "preference"}
        or str(slot.get("source") or "").lower() == "user"
    ]
    preferences.sort(key=lambda row: (numeric_step(row), str(row["id"])))
    if not preferences:
        return _answer(episode, "preference_persistence", None, [])
    preference = preferences[0]
    status = str(preference.get("status") or preference.get("mode") or "unknown").lower()
    value = preference.get("value")
    if status in {"active", "restored", "persistent", "valid"}:
        result = "yes"
    elif status in {"expired", "suspended", "inactive", "deleted"}:
        result = "no"
    else:
        return _answer(episode, "preference_persistence", None, [preference])
    rendered = f"{result}: {preference['id']}"
    if value is not None:
        rendered += f"={str(value).strip().lower()}"
    return _answer(episode, "preference_persistence", rendered, [preference])


def _restore_revalidation(episode: dict[str, Any]) -> dict[str, Any]:
    patches = sorted(
        episode["cope"]["patches"], key=lambda row: (numeric_step(row), str(row["id"]))
    )
    validators = {item["id"]: item for item in episode["cope"]["validator_outputs"]}
    for patch in patches:
        if str(patch.get("op") or patch.get("operation") or "").lower() != "restore":
            continue
        reference = patch.get("revalidation_id") or patch.get("validation_id")
        validation = validators.get(reference)
        valid = (
            validation is not None
            and bool(validation.get("success", validation.get("valid", False)))
            and numeric_step(validation) <= numeric_step(patch)
        )
        support = [patch] + ([validation] if validation else [])
        return _answer(
            episode,
            "restore_revalidation",
            f"{'yes' if valid else 'no'}: {patch['id']}",
            support,
            failure_layer=None if valid else "validation",
        )
    return _answer(episode, "restore_revalidation", None, [])


def _alignment_freshness(episode: dict[str, Any]) -> dict[str, Any]:
    disturbance_events = [
        event for event in episode["raw"]["events"] if "disturb" in _event_name(event) or "move" in _event_name(event)
    ]
    if not disturbance_events:
        return _answer(episode, "alignment_freshness", None, [])
    disturbance = sorted(
        disturbance_events, key=lambda row: (numeric_step(row), str(row["id"]))
    )[0]
    alignments = [
        slot
        for slot in episode["cope"]["slots"]
        if "alignment" in str(slot.get("kind") or slot.get("type") or slot.get("name") or "").lower()
    ]
    alignments.sort(key=lambda row: (numeric_step(row), str(row["id"])))
    post = [slot for slot in alignments if numeric_step(slot) >= numeric_step(disturbance)]
    if not post:
        return _answer(episode, "alignment_freshness", "old alignment", [disturbance], failure_layer="perception")
    selected = post[-1]
    evidence = selected.get("evidence_refs", [])
    is_new = disturbance["id"] in evidence or bool(selected.get("fresh_after_event"))
    return _answer(
        episode,
        "alignment_freshness",
        f"{'new' if is_new else 'old'} alignment: {selected['id']}",
        [disturbance, selected],
        failure_layer=None if is_new else "perception",
    )


def _earliest_failure(episode: dict[str, Any]) -> dict[str, Any]:
    candidates: list[tuple[int, int, dict[str, Any], str]] = []
    precedence = {layer: index for index, layer in enumerate(FAILURE_LAYERS)}
    records = (
        episode["raw"]["events"]
        + episode["regeneration"]["snapshots"]
        + episode["cope"]["patches"]
        + episode["cope"]["validator_outputs"]
    )
    for record in records:
        layer = record.get("failure_layer")
        status = str(record.get("status") or record.get("result") or "").lower()
        failed = bool(record.get("failed")) or record.get("success") is False or status in {
            "failure",
            "failed",
            "error",
            "invalid",
        }
        if layer in precedence and failed:
            candidates.append((numeric_step(record), precedence[layer], record, str(layer)))
    controller = episode.get("controller_status")
    if isinstance(controller, dict):
        layer = controller.get("failure_layer")
        if layer in precedence:
            pseudo = dict(controller)
            pseudo.setdefault("id", stable_id("controller", episode["episode_id"], controller))
            candidates.append(
                (numeric_step(pseudo), precedence[str(layer)], pseudo, str(layer))
            )
    if not candidates:
        layer = episode["metadata"].get("failure_layer")
        if layer in precedence:
            pseudo = {
                "id": stable_id("metadata", episode["episode_id"], layer),
                "policy_step": 0,
            }
            candidates.append((0, precedence[str(layer)], pseudo, str(layer)))
    if not candidates:
        return _answer(episode, "earliest_failure_layer", None, [])
    _, _, record, layer = min(candidates, key=lambda item: (item[0], item[1], item[2]["id"]))
    return _answer(
        episode,
        "earliest_failure_layer",
        layer,
        [record],
        failure_layer=layer,
    )


EXTRACTORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "behavior_change_reason": _behavior_change,
    "constraint_override": _constraint_override,
    "preference_persistence": _preference_persistence,
    "restore_revalidation": _restore_revalidation,
    "alignment_freshness": _alignment_freshness,
    "earliest_failure_layer": _earliest_failure,
}


def extract_ground_truth(episode: dict[str, Any]) -> list[dict[str, Any]]:
    results = [EXTRACTORS[kind](episode) for kind in QUESTION_KINDS]
    for result in results:
        result["ground_truth_id"] = stable_id(
            "groundtruth", episode["episode_id"], result["question_kind"]
        )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract deterministic audit ground truth.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--schema-version", default=SCHEMA_VERSION)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema version: {args.schema_version}")
    episode = load_episode(args.input)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode["episode_id"],
        "ground_truth": extract_ground_truth(episode),
    }
    if args.dry_run:
        print(json.dumps({"episode_id": episode["episode_id"], "items": 6}, sort_keys=True))
        return
    write_json(args.output, payload)
    print(json.dumps({"output": str(args.output), "items": 6}, sort_keys=True))


if __name__ == "__main__":
    main()
