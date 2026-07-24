from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from auditability import SCHEMA_VERSION
from auditability.common import content_hash, numeric_step, read_json, stable_id, write_json, write_jsonl
from auditability.schema_adapter import adapt_episode, load_episode
from auditability.trace_state import canonical_slots, replay_patch, state_hash


def _finding(
    episode: dict[str, Any],
    error_type: str,
    location: str,
    evidence_ids: list[str],
    message: str,
) -> dict[str, Any]:
    return {
        "finding_id": stable_id(
            "finding", episode["episode_id"], error_type, location, evidence_ids
        ),
        "episode_id": episode["episode_id"],
        "error_type": error_type,
        "location": location,
        "evidence_ids": evidence_ids,
        "message": message,
    }


def _restore_findings(episode: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    validators = {row["id"]: row for row in episode["cope"]["validator_outputs"]}
    for index, patch in enumerate(episode["cope"]["patches"]):
        if str(patch.get("op") or patch.get("operation") or "").lower() != "restore":
            continue
        validation_id = patch.get("revalidation_id") or patch.get("validation_id")
        validation = validators.get(validation_id)
        location = f"/cope/patches/{index}"
        evidence = [patch["id"]]
        if validation is None:
            findings.append(
                _finding(
                    episode,
                    "missing_revalidate",
                    location,
                    evidence,
                    "Restore does not reference an existing Revalidate.",
                )
            )
        elif not bool(validation.get("success", validation.get("valid", False))):
            findings.append(
                _finding(
                    episode,
                    "failed_revalidate",
                    location,
                    evidence + [validation["id"]],
                    "Restore references an unsuccessful Revalidate.",
                )
            )
        elif numeric_step(validation) > numeric_step(patch):
            findings.append(
                _finding(
                    episode,
                    "late_revalidate",
                    location,
                    evidence + [validation["id"]],
                    "Revalidate occurs after Restore.",
                )
            )
        if not patch.get("source_event_id") and not patch.get("evidence_refs"):
            findings.append(
                _finding(
                    episode,
                    "unexplained_restore",
                    location,
                    evidence,
                    "Restore has no event or evidence provenance.",
                )
            )
        if str((patch.get("changes") or {}).get("status", "")).lower() == "expired":
            findings.append(
                _finding(
                    episode,
                    "expire_to_restore",
                    location,
                    evidence,
                    "Restore operation retains an expired after-status.",
                )
            )
    return findings


def _slot_findings(episode: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    slots = episode["cope"]["slots"]
    slot_ids = {slot["id"] for slot in slots}
    for index, patch in enumerate(episode["cope"]["patches"]):
        op = str(patch.get("op") or patch.get("operation") or "").lower()
        if op == "add":
            continue
        target = patch.get("target_slot_id") or patch.get("slot_id")
        if target and target not in slot_ids:
            findings.append(
                _finding(
                    episode,
                    "slot_id_replaced",
                    f"/cope/patches/{index}/target_slot_id",
                    [patch["id"]],
                    f"Patch target does not exist: {target}",
                )
            )
    parents: dict[str, list[str]] = {}
    for index, slot in enumerate(slots):
        raw_parents = slot.get("parent_slot_ids", slot.get("lineage", []))
        if isinstance(raw_parents, str):
            raw_parents = [raw_parents]
        parent = slot.get("parent_slot_id")
        if parent:
            raw_parents = list(raw_parents or []) + [parent]
        parents[slot["id"]] = [str(item) for item in raw_parents or []]
        for parent_id in parents[slot["id"]]:
            if parent_id not in slot_ids:
                findings.append(
                    _finding(
                        episode,
                        "dangling_lineage",
                        f"/cope/slots/{index}",
                        [slot["id"]],
                        f"Lineage parent does not exist: {parent_id}",
                    )
                )
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(slot_id: str, path: list[str]) -> None:
        if slot_id in visiting:
            cycle = path[path.index(slot_id) :] + [slot_id]
            findings.append(
                _finding(
                    episode,
                    "lineage_cycle",
                    "/cope/slots",
                    cycle,
                    "Slot lineage contains a cycle.",
                )
            )
            return
        if slot_id in visited:
            return
        visiting.add(slot_id)
        for parent_id in parents.get(slot_id, []):
            if parent_id in parents:
                walk(parent_id, path + [parent_id])
        visiting.remove(slot_id)
        visited.add(slot_id)

    for slot_id in sorted(parents):
        walk(slot_id, [slot_id])

    grouped: dict[tuple[Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for slot in slots:
        if str(slot.get("status", "active")).lower() == "active":
            grouped[(slot.get("key", slot.get("name", slot.get("kind"))), slot.get("priority"))].append(slot)
    for (key, priority), group in grouped.items():
        values = {json.dumps(slot.get("value"), sort_keys=True) for slot in group}
        if key is not None and priority is not None and len(group) > 1 and len(values) > 1:
            findings.append(
                _finding(
                    episode,
                    "priority_conflict",
                    "/cope/slots",
                    [slot["id"] for slot in group],
                    f"Active slots conflict at key={key!r}, priority={priority!r}.",
                )
            )
    return findings


def _provenance_findings(episode: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    event_ids = {event["id"] for event in episode["raw"]["events"]}
    for index, patch in enumerate(episode["cope"]["patches"]):
        source_id = patch.get("source_event_id")
        evidence = patch.get("evidence_refs", [])
        if not source_id and not evidence:
            findings.append(
                _finding(
                    episode,
                    "missing_event_provenance",
                    f"/cope/patches/{index}",
                    [patch["id"]],
                    "Patch has no source event or evidence references.",
                )
            )
        elif source_id and source_id not in event_ids:
            findings.append(
                _finding(
                    episode,
                    "dangling_event_provenance",
                    f"/cope/patches/{index}/source_event_id",
                    [patch["id"]],
                    f"Patch source event does not exist: {source_id}",
                )
            )
    return findings


def _state_findings(episode: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    states = episode["cope"]["states"]
    state_by_id = {state["id"]: state for state in states}
    for index, state in enumerate(states):
        recorded = state.get("state_hash")
        if recorded is not None:
            actual = state_hash(state)
            if recorded != actual:
                findings.append(
                    _finding(
                        episode,
                        "state_hash_mismatch",
                        f"/cope/states/{index}/state_hash",
                        [state["id"]],
                        f"Recorded state hash {recorded} does not match {actual}.",
                    )
                )
    patches = episode["cope"]["patches"]
    sequences = [patch.get("sequence") for patch in patches]
    if sequences and all(isinstance(value, int) for value in sequences):
        if sequences != sorted(sequences):
            findings.append(
                _finding(
                    episode,
                    "patch_order_shuffled",
                    "/cope/patches",
                    [patch["id"] for patch in patches],
                    "Patch sequence is not monotonically ordered.",
                )
            )
    for index, patch in enumerate(patches):
        before = state_by_id.get(patch.get("before_state_id"))
        after = state_by_id.get(patch.get("after_state_id"))
        if before is None or after is None:
            continue
        try:
            replayed = replay_patch(before.get("slots", []), patch)
        except (KeyError, ValueError) as exc:
            findings.append(
                _finding(
                    episode,
                    "patch_replay_error",
                    f"/cope/patches/{index}",
                    [patch["id"]],
                    str(exc),
                )
            )
            continue
        if canonical_slots(replayed) != canonical_slots(after.get("slots", [])):
            findings.append(
                _finding(
                    episode,
                    "patch_replay_mismatch",
                    f"/cope/patches/{index}",
                    [patch["id"], before["id"], after["id"]],
                    "Replaying the patch does not produce the recorded after-state.",
                )
            )
    if len(states) >= 2:
        first_slots = {
            slot.get("id"): slot
            for slot in states[0].get("slots", [])
            if slot.get("id") and slot.get("source")
        }
        last_ids = {slot.get("id") for slot in states[-1].get("slots", [])}
        disappeared = set(first_slots) - last_ids
        explained = {
            patch.get("target_slot_id")
            for patch in patches
            if str(patch.get("op", "")).lower() in {"expire", "delete", "remove"}
        }
        for slot_id in sorted(disappeared - explained):
            is_user = str(first_slots[slot_id].get("source", "")).lower() == "user"
            findings.append(
                _finding(
                    episode,
                    "missing_user_preference"
                    if is_user
                    else "source_silent_disappearance",
                    "/cope/states",
                    [str(slot_id)],
                    "Sourced slot disappears without an explicit Expire/Delete patch.",
                )
            )
    return findings


def audit_episode(episode: dict[str, Any]) -> dict[str, Any]:
    findings = (
        _restore_findings(episode)
        + _slot_findings(episode)
        + _provenance_findings(episode)
        + _state_findings(episode)
    )
    unique = {finding["finding_id"]: finding for finding in findings}
    ordered = sorted(
        unique.values(), key=lambda row: (row["error_type"], row["location"], row["finding_id"])
    )
    return {
        "audit_id": stable_id("audit", episode["episode_id"], content_hash(episode)),
        "episode_id": episode["episode_id"],
        "corruption_id": episode.get("corruption_id"),
        "detected": bool(ordered),
        "detected_error_types": sorted({row["error_type"] for row in ordered}),
        "findings": ordered,
    }


def _load(path: Path) -> list[dict[str, Any]]:
    if path.is_dir():
        return [
            read_json(candidate)
            for candidate in sorted(path.rglob("*.json"))
            if candidate.name != "manifest.json"
        ]
    if path.suffix == ".jsonl":
        from auditability.common import read_jsonl

        return [
            row if row.get("schema_version") == SCHEMA_VERSION else adapt_episode(row, origin=str(path))
            for row in read_jsonl(path)
        ]
    source = read_json(path)
    if source.get("schema_version") == SCHEMA_VERSION:
        return [source]
    return [load_episode(path)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic trace validators.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--schema-version", default=SCHEMA_VERSION)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema version: {args.schema_version}")
    audits = [audit_episode(episode) for episode in _load(args.input)]
    config = {
        "input": str(args.input.resolve()),
        "seed": args.seed,
        "schema_version": args.schema_version,
        "validators": ["restore", "slot", "lineage", "priority", "provenance", "hash", "replay"],
    }
    summary = {
        "config_hash": content_hash(config),
        "trace_count": len(audits),
        "detected_count": sum(row["detected"] for row in audits),
        "finding_count": sum(len(row["findings"]) for row in audits),
    }
    if args.dry_run:
        print(json.dumps(summary, sort_keys=True))
        return
    write_jsonl(
        args.output,
        audits,
        resume_key="audit_id" if args.resume else None,
    )
    write_json(
        args.output.with_suffix(".manifest.json"),
        {**summary, "config": config},
        overwrite=args.resume,
    )
    print(json.dumps({**summary, "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
