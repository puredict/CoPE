#!/usr/bin/env python3
"""Offline global-trajectory audit for complete or partial R4 free-running runs.

Reconstruct the gold sequence from the registered scenario, never from a
method's possibly corrupted predecessor. No model, GPU, or server is contacted.
An existing output is never overwritten, and episode artifacts remain read-only.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from cope.lineage_benchmark.models import ScenarioSpec, canonical_json  # noqa: E402
from cope.lineage_benchmark.reference import reference_transition  # noqa: E402
from cope.lineage_benchmark.task import build_scenario  # noqa: E402


def fingerprint(document: Any) -> str:
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


def slots_by_id(document: dict[str, Any]) -> dict[str, Any]:
    slots = document.get("slots", [])
    if not isinstance(slots, list) or any(not isinstance(s, dict) for s in slots):
        raise ValueError("snapshot slots must be an array of objects")
    mapping = {slot["slot_id"]: slot for slot in slots}
    if len(mapping) != len(slots):
        raise ValueError("snapshot has duplicate slot IDs")
    return mapping


def comparable(document: dict[str, Any]) -> dict[str, Any]:
    # Slot-array serialization order is not part of commitment semantics.
    return {**document, "slots": slots_by_id(document)}


def field_differences(actual: Any, expected: Any, limit: int = 40) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    count = 0
    missing = object()

    def preview(value: Any) -> Any:
        if value is missing:
            return {"missing": True}
        rendered = canonical_json(value)
        return value if len(rendered) <= 400 else {"truncated_json": rendered[:400], "chars": len(rendered)}

    def visit(left: Any, right: Any, path: str) -> None:
        nonlocal count
        if type(left) is type(right) and isinstance(left, dict):
            for key in sorted(left.keys() | right.keys()):
                visit(left.get(key, missing), right.get(key, missing), path + "/" + str(key).replace("~", "~0").replace("/", "~1"))
        elif type(left) is type(right) and isinstance(left, list):
            for index in range(max(len(left), len(right))):
                visit(left[index] if index < len(left) else missing,
                      right[index] if index < len(right) else missing, f"{path}/{index}")
        elif type(left) is not type(right) or left != right:
            count += 1
            if len(rows) < limit:
                rows.append({"path": path or "/", "actual": preview(left), "expected": preview(right)})

    visit(actual, expected, "")
    return {"count": count, "shown": rows, "truncated": count > len(rows)}


def committed_step_checks(
    actual: dict[str, Any] | None,
    expected: dict[str, Any],
    *,
    event_kind: str,
    critical_logical_id: str,
    root_id: str,
) -> dict[str, Any]:
    """Separate occurrence choice, full plan and downstream continuation.

    Only recorded commits are assessed. At suspended gold steps, an empty
    active-ID set is meaningful but an active plan is not applicable. For this
    registered task, continuation means all actions after the first action.
    """
    def critical_slots(document):
        return {sid: slot for sid, slot in slots_by_id(document).items()
                if slot.get("kind") == "workflow" and slot.get("logical_id") == critical_logical_id}

    committed = actual is not None
    actual_slots = critical_slots(actual) if committed else {}
    expected_slots = critical_slots(expected)
    actual_ids = sorted(sid for sid, slot in actual_slots.items() if slot.get("mode") == "active")
    expected_ids = sorted(sid for sid, slot in expected_slots.items() if slot.get("mode") == "active")
    actual_plan = actual_slots[actual_ids[0]].get("payload", {}).get("plan") if len(actual_ids) == 1 else None
    expected_plan = expected_slots[expected_ids[0]].get("payload", {}).get("plan") if len(expected_ids) == 1 else None
    plan_applicable = committed and len(expected_ids) == 1 and isinstance(expected_plan, list)
    continuation_applicable = plan_applicable and len(expected_plan) >= 1
    actual_continuation = actual_plan[1:] if isinstance(actual_plan, list) and actual_plan else None
    expected_continuation = expected_plan[1:] if isinstance(expected_plan, list) and expected_plan else None
    root_applicable = committed and event_kind == "restore_root"
    return {
        "committed_state_assessed": committed,
        "not_assessed_reason": None if committed else "no_recorded_commit_candidate_semantics_unknown",
        "active_target_selection_applicable": committed,
        "actual_active_critical_workflow_ids": actual_ids if committed else None,
        "reference_active_critical_workflow_ids": expected_ids if committed else None,
        "active_target_selection_correct": actual_ids == expected_ids if committed else None,
        "active_target_selection_definition": "exact set of active critical workflow occurrence IDs, including an empty set",
        "active_plan_applicable": plan_applicable,
        "active_plan_not_applicable_reason": (
            None if plan_applicable else "no_recorded_commit" if not committed else
            "reference_has_no_active_critical_workflow" if not expected_ids else
            "reference_does_not_have_one_active_workflow_with_a_plan"
        ),
        "actual_active_plan": actual_plan if committed else None,
        "reference_active_plan": expected_plan if committed else None,
        "active_plan_correct": actual_plan == expected_plan if plan_applicable else None,
        "continuation_applicable": continuation_applicable,
        "continuation_definition": "active plan[1:], excluding the first primary action",
        "actual_active_continuation": actual_continuation if committed else None,
        "reference_active_continuation": expected_continuation if committed else None,
        "continuation_correct": actual_continuation == expected_continuation if continuation_applicable else None,
        "root_restoration_applicable": root_applicable,
        "root_restoration_correct": (
            actual_ids == [root_id]
            and {sid: slot.get("mode") for sid, slot in actual_slots.items()}
            == {sid: slot.get("mode") for sid, slot in expected_slots.items()}
        ) if root_applicable else None,
        "root_restoration_definition": "registered root is the only active critical occurrence and all critical occurrence modes match global gold",
    }


def resolve_metadata(episode: Path, result: dict[str, Any] | None) -> tuple[ScenarioSpec, dict[str, Any], Path | None]:
    config_path = next((parent / "config_resolved.json" for parent in list(episode.parents)[:5]
                        if (parent / "config_resolved.json").is_file()), None)
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path else {}
    run = config.get("run", {})
    result = result or {}
    mode = result.get("run_mode", run.get("mode"))
    if mode != "free_running":
        raise ValueError(f"global free-running audit requires explicit free_running metadata, got {mode!r}")
    profile = result.get("profile", episode.parent.parent.name)
    seed_match = re.fullmatch(r"seed_(\d+)", episode.name)
    seed = result.get("seed", int(seed_match.group(1)) if seed_match else None)
    if seed is None:
        raise ValueError("cannot resolve episode seed from result or seed_N directory")
    dimensions = result.get("registered_design", config.get("profiles", {}).get(profile, {}))
    budget = config.get("budgets", {}).get(run.get("budget"), {})
    spec = ScenarioSpec(
        seed=int(seed), profile=str(profile),
        initial_slots=int(dimensions["initial_slots"]),
        lineage_depth=int(dimensions["lineage_depth"]),
        max_output_tokens=int(dimensions.get("max_output_tokens", budget.get("max_output_tokens"))),
        model_timeout_s=float(dimensions.get("model_timeout_s", budget.get("timeout_s"))),
    )
    if config:
        if profile not in config.get("profiles", {}):
            raise ValueError("episode profile is absent from registered config")
        registered_seeds = config.get(str(run.get("split")) + "_seeds", [])
        if seed not in registered_seeds:
            raise ValueError("episode seed is absent from its registered split")
    return spec, {
        "run_mode": mode, "profile": profile, "seed": seed,
        "method": result.get("method", episode.parent.name),
        "split": run.get("split"), "budget": run.get("budget"),
        "result_present": bool(result), "generation_retries": run.get("generation_retries"),
        "registered_source_sha256": run.get("source_sha256", {}),
    }, config_path


def audit_episode(episode: str | Path, *, diff_limit: int = 40) -> dict[str, Any]:
    episode = Path(episode).resolve()
    source_hashes: dict[str, str] = {}

    def read(path: Path, jsonl: bool = False):
        content = path.read_bytes()
        source_hashes[str(path)] = hashlib.sha256(content).hexdigest()
        if jsonl:
            return [json.loads(line) for line in content.decode("utf-8").splitlines() if line.strip()]
        return json.loads(content)

    result_path = episode / "result.json"
    result = read(result_path) if result_path.is_file() else None
    spec, metadata, config_path = resolve_metadata(episode, result)
    if config_path:
        source_hashes[str(config_path)] = hashlib.sha256(config_path.read_bytes()).hexdigest()
    snapshots = read(episode / "state_snapshots.jsonl", jsonl=True)
    calls = read(episode / "model_calls.jsonl", jsonl=True)
    if not snapshots or snapshots[0].get("label") != "initial":
        raise ValueError("first state snapshot must be the initial state")
    if any(str(row.get("label", "")).startswith("reference_input_next") for row in snapshots):
        raise ValueError("reference-fed reset snapshots are not free-running evidence")
    ordinals = [call["ordinal"] for call in calls]
    if ordinals != list(range(1, len(calls) + 1)):
        raise ValueError("recorded model calls are not a consecutive event prefix")
    scenario = build_scenario(spec)
    if len(calls) > len(scenario.events):
        raise ValueError("more model calls than registered events")
    gold = [scenario.initial_state]
    for event in scenario.events:
        gold.append(reference_transition(gold[-1], event, scenario.critical_logical_id))

    integrity_errors = []
    by_label = {}
    for snapshot in snapshots:
        label = snapshot["label"]
        if label in by_label:
            raise ValueError(f"duplicate snapshot label {label!r}")
        by_label[label] = snapshot
        if snapshot.get("fingerprint") != fingerprint(snapshot["state"]):
            integrity_errors.append(f"snapshot hash mismatch: {label}")
    actual_initial = snapshots[0]["state"]
    initial_diff = field_differences(comparable(actual_initial), comparable(gold[0].to_dict()), diff_limit)
    steps = []
    last_committed = snapshots[0]
    last_committed_ordinal = 0
    for call, event in zip(calls, scenario.events):
        if call["event_id"] != event.event_id:
            raise ValueError("call event ID differs from the registered schedule")
        committed = call.get("state_committed")
        if not isinstance(committed, bool):
            raise ValueError("R4 state_committed must be recorded explicitly")
        if call.get("state_fingerprint_before") != last_committed.get("fingerprint"):
            integrity_errors.append(f"broken committed-state input chain at {event.event_id}")
        snapshot = by_label.get(f"after_event_{event.ordinal:02d}") if committed else None
        if committed and snapshot is None:
            raise ValueError(f"committed state snapshot missing after {event.event_id}; resync completed writes")
        difference = None
        match = None
        if snapshot is not None:
            if call.get("state_fingerprint_after") != snapshot.get("fingerprint"):
                integrity_errors.append(f"call/snapshot output hash mismatch at {event.event_id}")
            difference = field_differences(comparable(snapshot["state"]), comparable(gold[event.ordinal].to_dict()), diff_limit)
            match = difference["count"] == 0
            last_committed, last_committed_ordinal = snapshot, event.ordinal
        elif call.get("state_fingerprint_after") != last_committed.get("fingerprint"):
            integrity_errors.append(f"rejected call changed state hash at {event.event_id}")
        steps.append({
            "event_id": event.event_id, "ordinal": event.ordinal, "event_kind": event.kind,
            "state_committed": committed,
            "generation_status": call.get("generation", {}).get("status"),
            "adaptation_status": call.get("adaptation_status"),
            "gold_state_fingerprint": gold[event.ordinal].fingerprint(),
            "actual_committed_state_fingerprint": fingerprint(snapshot["state"]) if snapshot else None,
            "committed_state_matches_gold": match, "differences": difference,
            "committed_state_checks": committed_step_checks(
                snapshot["state"] if snapshot else None,
                gold[event.ordinal].to_dict(), event_kind=event.kind,
                critical_logical_id=scenario.critical_logical_id,
                root_id=scenario.task_contract["root_slot_id"],
            ),
        })

    final = slots_by_id(last_committed["state"])
    expected = slots_by_id(gold[-1].to_dict())
    initial_slots = slots_by_id(actual_initial)
    root_id = scenario.task_contract["root_slot_id"]
    actual_root = final.get(root_id, {})
    critical_active = [slot for slot in final.values() if slot["kind"] == "workflow"
                       and slot["logical_id"] == scenario.critical_logical_id and slot["mode"] == "active"]
    actual_plan = critical_active[0].get("payload", {}).get("plan") if len(critical_active) == 1 else None
    expected_plan = [dict(action) for action in scenario.expected_plan]
    changed_untouched = [sid for sid, slot in initial_slots.items()
                         if slot["kind"] in {"order_archive", "safety"} and final.get(sid) != slot]
    workflow_ids = [sid for sid, slot in expected.items() if slot["kind"] == "workflow"]
    wrong_history = [sid for sid, slot in expected.items()
                     if final.get(sid, {}).get("history") != slot["history"]]
    wrong_graph = [sid for sid in workflow_ids
                   if final.get(sid, {}).get("lineage") != expected[sid]["lineage"]]
    wrong_modes = [sid for sid in workflow_ids
                   if final.get(sid, {}).get("mode") != expected[sid]["mode"]]
    committed_steps = [step for step in steps if step["state_committed"]]
    all_committed = len(committed_steps) == len(scenario.events)
    source_matches = {}
    for relative in ("code/cope/lineage_benchmark/task.py", "code/cope/lineage_benchmark/reference.py"):
        registered = metadata["registered_source_sha256"].get(relative)
        current = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        source_matches[relative] = {"registered_sha256": registered, "audit_sha256": current,
                                    "matches_registered": current == registered if registered else None}
        if registered and registered != current:
            integrity_errors.append(f"audit source differs from registered source: {relative}")
    prefix_correct = initial_diff["count"] == 0 and all(step["committed_state_matches_gold"] for step in committed_steps)
    return {
        "schema_version": "cope-r4-global-trajectory-audit-v1",
        "utc": datetime.now(timezone.utc).isoformat(), "episode": str(episode),
        "metadata": metadata,
        "gold_reference": "build_scenario(spec), then independent reference_transition on gold only",
        "stored_semantic_match_flags_used": False,
        "registered_events": len(scenario.events), "observed_calls": len(calls),
        "committed_events": len(committed_steps), "last_committed_ordinal": last_committed_ordinal,
        "all_registered_events_committed": all_committed,
        "initial_state_matches_registered_scenario": initial_diff["count"] == 0,
        "initial_differences": initial_diff,
        "observed_committed_states_match_gold": prefix_correct,
        "complete_global_trajectory_match": bool(all_committed and prefix_correct and not integrity_errors),
        "per_step": steps,
        "final_checks": {
            "comparison_target": "full registered final state, even if this run is partial",
            "final_recorded_state_matches_full_gold": comparable(last_committed["state"]) == comparable(gold[-1].to_dict()),
            "root_slot_id": root_id,
            "root_is_only_active_critical_workflow": len(critical_active) == 1 and critical_active[0]["slot_id"] == root_id,
            "root_payload_matches_registered_root": actual_root.get("payload") == expected[root_id]["payload"],
            "active_continuation_matches_root": actual_plan == expected_plan,
            "actual_active_plan": actual_plan, "expected_root_plan": expected_plan,
            "workflow_modes_match_final": not wrong_modes, "wrong_mode_slot_ids": wrong_modes[:diff_limit],
            "workflow_lineage_matches_final": not wrong_graph, "wrong_lineage_slot_ids": wrong_graph[:diff_limit],
            "all_slot_histories_match_final": not wrong_history, "wrong_history_slot_ids": wrong_history[:diff_limit],
            "all_history_sequences_contiguous": all(
                [entry.get("seq") for entry in slot.get("history", [])] == list(range(1, len(slot.get("history", [])) + 1))
                for slot in final.values()),
            "untouched_archives_and_safety_preserved": not changed_untouched,
            "changed_untouched_slot_ids": changed_untouched[:diff_limit],
            "physical_success_assessed": False,
        },
        "integrity_errors": integrity_errors, "source_artifact_sha256": source_hashes,
        "reference_source_provenance": source_matches,
        "limitations": [
            "This audit scores recorded committed states, not rejected candidate semantics or physical success.",
            "A partial run may have a correct committed prefix; it is not a complete trajectory success.",
            "Field differences are bounded per state; count records the total differing fields.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="New JSON file outside the source episode")
    parser.add_argument("--diff-limit", type=int, default=40)
    args = parser.parse_args()
    if args.diff_limit < 1:
        raise ValueError("diff-limit must be positive")
    episode, output = args.episode.resolve(), args.out.resolve()
    if output == episode or episode in output.parents:
        raise ValueError("write audit outside the source episode to preserve its outputs")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    report = audit_episode(episode, diff_limit=args.diff_limit)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"out": str(output), "observed_calls": report["observed_calls"],
                      "committed_events": report["committed_events"],
                      "complete_global_trajectory_match": report["complete_global_trajectory_match"],
                      "integrity_errors": report["integrity_errors"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
