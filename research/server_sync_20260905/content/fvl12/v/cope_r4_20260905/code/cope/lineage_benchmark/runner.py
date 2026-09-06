"""One auditable r3 episode from identical exogenous inputs to task completion."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
from typing import Any, Dict, List, Optional

from .adapters import ADAPTERS
from .client import ModelClient
from .models import LineageScenario, ModelPacket
from .prompts import system_prompt, user_prompt
from .state import StateValidationError, active_plan
from .world import make_world
from .reference import reference_transition


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def run_episode(
    scenario: LineageScenario,
    *,
    method: str,
    client: ModelClient,
    episode_dir: str | Path,
    backend: str = "symbolic_basket",
    backend_config: str | Path | None = None,
    model_name: str = "local-oracle",
    diagnostic_reference_inputs: bool = False,
) -> Dict[str, Any]:
    if method not in ADAPTERS:
        raise ValueError(f"unknown method {method!r}; choose {sorted(ADAPTERS)}")
    out_dir = Path(episode_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    raw_dir = out_dir / "raw_outputs"
    raw_dir.mkdir()

    adapter = ADAPTERS[method](client)
    state = scenario.initial_state
    state_rows: List[Dict[str, Any]] = [{
        "label": "initial",
        "revision": state.revision,
        "fingerprint": state.fingerprint(),
        "state": state.to_dict(),
    }]
    event_rows: List[Dict[str, Any]] = []
    call_rows: List[Dict[str, Any]] = []
    event_history: List[Dict[str, Any]] = []
    all_valid = True
    all_semantic_matches = True
    first_failure = ""
    first_failure_event = None
    restore_attempted = False

    for event in scenario.events:
        packet = ModelPacket(
            task_contract=scenario.task_contract,
            current_state=state,
            event=event,
            event_history=tuple(event_history),
            completed_actions=(),
            world_state={
                "available_targets": ["basket_A", "basket_B", "basket_C"],
                "robot_holding": None,
                "physical_execution_deferred_until_final_state": True,
            },
            compute_budget={
                "max_model_calls": 1,
                "max_output_tokens": scenario.spec.max_output_tokens,
                "timeout_s": scenario.spec.model_timeout_s,
            },
        )
        before = state
        system_text = system_prompt(method)
        user_text = user_prompt(packet)
        _write_json(out_dir / "progress.json", {
            "status": "request_started", "event_id": event.event_id,
            "ordinal": event.ordinal, "method": method,
            "utc": datetime.now(timezone.utc).isoformat(),
            "completed_calls": len(call_rows),
        })
        result = adapter.adapt(packet)
        raw_path = raw_dir / f"event_{event.ordinal:02d}.txt"
        raw_path.write_text(result.generation.text, encoding="utf-8")
        call_row = {
            "event_id": event.event_id,
            "ordinal": event.ordinal,
            "method": method,
            "model": model_name,
            "packet_fingerprint": packet.fingerprint(),
            "exogenous_fingerprint": packet.exogenous_fingerprint(),
            "system_prompt_sha256": hashlib.sha256(
                system_text.encode("utf-8")
            ).hexdigest(),
            "user_prompt_sha256": hashlib.sha256(
                user_text.encode("utf-8")
            ).hexdigest(),
            "system_prompt_chars": len(system_text),
            "user_prompt_chars": len(user_text),
            "state_fingerprint_before": before.fingerprint(),
            "generation": result.generation.to_dict(),
            "adaptation_status": result.status,
            "adaptation_valid": result.ok,
            "validation_errors": list(result.validation_errors),
            "semantic_match_to_registered_transition": result.semantic_match,
            "request_completed": result.generation.request_completed,
            "json_parse_success": result.generation.parsed is not None,
            "output_schema_valid": result.generation.telemetry.get("schema_valid"),
            "transition_valid": result.ok,
            "candidate_rejected_by_transition_validator": bool(result.generation.ok and not result.ok),
            "candidate_semantic_correct": result.semantic_match if result.ok else None,
            "state_committed": result.ok and not diagnostic_reference_inputs,
            "committed_state_semantic_correct": (result.semantic_match
                if result.ok and not diagnostic_reference_inputs else None),
            "candidate_state_fingerprint": result.state.fingerprint() if result.ok else None,
            "state_fingerprint_after": result.state.fingerprint(),
            "failure_stage": (
                "generation" if not result.generation.ok else
                "transition_validation" if not result.ok else
                "semantic" if not result.semantic_match else None
            ),
            "raw_output_file": str(raw_path.relative_to(out_dir)),
        }
        call_rows.append(call_row)
        _write_jsonl(out_dir / "model_calls.jsonl", call_rows)
        event_rows.append({
            "event": event.to_dict(),
            "exogenous_fingerprint": packet.exogenous_fingerprint(),
            "adaptation_valid": result.ok,
            "adaptation_status": result.status,
        })
        event_history.append({
            "event_id": event.event_id,
            "ordinal": event.ordinal,
            "kind": event.kind,
            "current_slot_id": event.current_slot_id,
            "user_request": event.user_request,
            "reason": event.reason,
            "new_slot": event.new_slot,
        })
        restore_attempted = restore_attempted or event.kind == "restore_root"
        if (not result.ok or not result.semantic_match) and not first_failure:
            first_failure = result.status if not result.ok else "semantic_mismatch"
            first_failure_event = event.event_id
        if not result.ok:
            all_valid = False
            all_semantic_matches = False
            state_rows.append({
                "label": f"rejected_after_event_{event.ordinal:02d}",
                "revision": state.revision,
                "fingerprint": state.fingerprint(),
                "state": state.to_dict(),
            })
            _write_jsonl(out_dir / "state_snapshots.jsonl", state_rows)
            _write_jsonl(out_dir / "events.jsonl", event_rows)
            if (not diagnostic_reference_inputs
                    or result.generation.telemetry.get("server_drain", {}).get("confirmed_idle") is False):
                break
        state = (reference_transition(before, event, scenario.critical_logical_id)
                 if diagnostic_reference_inputs else result.state)
        all_semantic_matches = all_semantic_matches and result.semantic_match
        state_rows.append({
            "label": ("reference_input_next" if diagnostic_reference_inputs else "after")
            + f"_event_{event.ordinal:02d}",
            "revision": state.revision,
            "fingerprint": state.fingerprint(),
            "state": state.to_dict(),
        })
        _write_jsonl(out_dir / "state_snapshots.jsonl", state_rows)
        _write_jsonl(out_dir / "events.jsonl", event_rows)

    all_events_processed = len(call_rows) == len(scenario.events)
    compiled_plan: List[Dict[str, str]] = []
    plan_error = ""
    if all_valid and all_events_processed and not diagnostic_reference_inputs:
        try:
            compiled_plan = active_plan(state, scenario.critical_logical_id)
        except StateValidationError as exc:
            plan_error = str(exc)
    plan_matches = compiled_plan == [dict(item) for item in scenario.expected_plan]
    root_restored = any(
        slot.slot_id == scenario.task_contract["root_slot_id"]
        and slot.mode == "active"
        for slot in state.slots.values()
    ) if restore_attempted and not diagnostic_reference_inputs else None

    if compiled_plan:
        _write_json(out_dir / "progress.json", {
            "status": "physical_execution_started" if backend == "libero_mujoco" else "symbolic_execution_started",
            "completed_calls": len(call_rows), "backend": backend,
            "utc": datetime.now(timezone.utc).isoformat(),
        })
        physical = make_world(backend).execute(
            compiled_plan,
            scenario.expected_plan,
            seed=scenario.spec.seed,
            episode_dir=out_dir,
            backend_config=(Path(backend_config).resolve() if backend_config else None),
        )
    else:
        physical = {
            "backend": backend,
            "initialized": False,
            "actions": [],
            "expected_assignment": {
                item["object"]: item["target"] for item in scenario.expected_plan
            },
            "observed_assignment": {},
            "exact_assignment": None,
            "physical_success": None,
            "invalid_action_count": 0,
            "controller_error": "",
            "skipped_reason": ("reference_fed_diagnostic" if diagnostic_reference_inputs
                               else first_failure or plan_error or "no_compilable_plan"),
            "video": {"written": False, "skipped": True},
            "finish": {},
        }

    task_completion = bool(
        all_valid
        and all_events_processed
        and plan_matches
        and root_restored
        and physical.get("physical_success", False)
    )
    if diagnostic_reference_inputs:
        task_completion = None
    physical_attempted = bool(compiled_plan) and backend == "libero_mujoco"
    result_row: Dict[str, Any] = {
        "schema_version": "cope-fsrpc-r4-episode-v1",
        "run_mode": "reference_fed_diagnostic" if diagnostic_reference_inputs else "free_running",
        "utc": datetime.now(timezone.utc).isoformat(),
        "episode_id": (
            f"{scenario.spec.profile}|seed={scenario.spec.seed}|method={method}"
        ),
        "pairing_key": f"{scenario.spec.profile}|seed={scenario.spec.seed}",
        "profile": scenario.spec.profile,
        "seed": scenario.spec.seed,
        "method": method,
        "model": model_name,
        "backend": backend,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "registered_design": {
            "initial_slots": scenario.spec.initial_slots,
            "lineage_depth": scenario.spec.lineage_depth,
            "n_events": len(scenario.events),
            "max_output_tokens": scenario.spec.max_output_tokens,
            "model_timeout_s": scenario.spec.model_timeout_s,
            "critical_logical_id": scenario.critical_logical_id,
            "expected_plan": [dict(item) for item in scenario.expected_plan],
        },
        "task_contract": scenario.task_contract,
        "model_request_contract": {
            "model": model_name,
            "calls_per_event": 1,
            "max_output_tokens": scenario.spec.max_output_tokens,
            "timeout_s": scenario.spec.model_timeout_s,
        },
        "metrics": {
            "task_completion": task_completion,
            "end_to_end_success": (None if diagnostic_reference_inputs else
                                   bool(physical_attempted and task_completion and all_semantic_matches)),
            "all_generations_valid": bool(all_valid and all_events_processed),
            "all_registered_transitions_semantically_matched": bool(
                all_semantic_matches and all_events_processed
            ),
            "all_events_processed": all_events_processed,
            "root_lineage_restored": root_restored,
            "compiled_plan_matches_root": plan_matches if compiled_plan else None,
            "physical_attempted": physical_attempted,
            "physical_success": physical.get("physical_success") if physical_attempted else None,
            "symbolic_execution_success": (physical.get("physical_success")
                                           if backend == "symbolic_basket" and compiled_plan else None),
            "n_model_calls": len(call_rows),
            "valid_model_calls": sum(row["adaptation_valid"] for row in call_rows),
            "candidate_transition_rejections": sum(row["candidate_rejected_by_transition_validator"] for row in call_rows),
            "candidate_semantic_errors_after_valid_transition": sum(row["candidate_semantic_correct"] is False for row in call_rows),
            "committed_semantic_errors": sum(row["committed_state_semantic_correct"] is False for row in call_rows),
            "total_prompt_tokens": sum(
                row["generation"]["prompt_tokens"] or 0 for row in call_rows
            ),
            "total_completion_tokens": sum(
                row["generation"]["completion_tokens"] or 0 for row in call_rows
            ),
            "total_model_latency_s": sum(
                row["generation"]["latency_s"] for row in call_rows
            ),
            "first_failure": first_failure,
            "first_failure_event": first_failure_event,
        },
        "compiled_plan": compiled_plan,
        "plan_error": plan_error,
        "physical": physical,
        "events": event_rows,
        "model_calls": call_rows,
        "final_state_fingerprint": state.fingerprint(),
        "artifact_files": {
            "events": "events.jsonl",
            "model_calls": "model_calls.jsonl",
            "states": "state_snapshots.jsonl",
            "actions": "actions.jsonl",
            "raw_outputs": "raw_outputs/",
        },
    }
    _write_jsonl(out_dir / "events.jsonl", event_rows)
    _write_jsonl(out_dir / "model_calls.jsonl", call_rows)
    _write_jsonl(out_dir / "state_snapshots.jsonl", state_rows)
    _write_jsonl(out_dir / "actions.jsonl", list(physical.get("actions", [])))
    _write_json(out_dir / "result.json", result_row)
    _write_json(out_dir / "progress.json", {"status": "finished", "completed_calls": len(call_rows)})
    return result_row
