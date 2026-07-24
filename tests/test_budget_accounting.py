from __future__ import annotations

from copy import deepcopy

from cope.types import METHOD_NAMES
from cope.validation import validate_episode_record, validate_pair_records


def minimal_record(method: str) -> dict:
    calls = 1 if method in {"history_augmented_full_regeneration", "cope_patch"} else 0
    record = {
        "schema_version": "cope-main-episode-v1",
        "run_id": "run",
        "pair_key": "pair",
        "task_id": 0,
        "initial_state_id": 0,
        "seed": 7,
        "method": method,
        "event_source": "oracle",
        "information_budget": {
            "max_high_level_calls": 1,
            "max_prompt_tokens": 100,
            "max_completion_tokens": 100,
        },
        "event": None if method == "clean" else {"event_type": "move"},
        "policy_step_budget": 220,
        "post_event_policy_step_budget": 150,
        "steps_before_event": 1,
        "steps_after_event": 1,
        "policy_steps": 2,
        "high_level_call_count": calls,
        "prompt_tokens": calls,
        "completion_tokens": calls,
        "constraint_state_before": None,
        "constraint_state_after": None,
        "patch_operations": [],
        "revalidation_result": [],
        "task_progress": {},
        "success": False,
        "termination_reason": "timeout",
        "safety_violation": False,
        "manual_intervention": False,
        "git_commit": "abc",
        "config_hash": "cfg",
        "checkpoint_id": "ckpt",
        "test_only": False,
        "checkpoint_sha256": "sha",
        "artifact_paths": {},
        "artifact_alignment": {
            "action_records": 2,
            "video_frames": 2,
            "aligned": True,
        },
        "initial_state_hash": "initial",
        "pre_event_action_digest": "pre",
        "provider_fairness_fingerprint": "provider",
        "provider_metadata": {"model": "same"},
        "prompt_template_hash": "template",
        "downstream_controller": {"name": "same"},
        "success_definition": "same",
        "termination_definition": "same",
        "disturbance_step": 70,
        "fresh_observation_hash": None if method == "clean" else "fresh",
        "recovery_input_hash": None if method == "clean" else "recovery",
        "provider_calls": [{}] * calls,
        "regenerated_state": {"constraints": []} if method == "history_augmented_full_regeneration" else None,
        "unaffected_slot_preservation": {"passed": True} if method == "cope_patch" else None,
        "reset_count": 0,
        "rollback_count": 0,
        "actions": [
            {"policy_step": 0, "video_frame_index": 0},
            {"policy_step": 1, "video_frame_index": 1},
        ],
    }
    if method == "cope_patch":
        record["constraint_state_before"] = {"constraints": []}
        record["constraint_state_after"] = {"constraints": []}
    return record


def test_budget_and_privilege_accounting_accepts_equal_pair() -> None:
    records = [minimal_record(method) for method in METHOD_NAMES]
    result = validate_pair_records(records)
    assert result["passed"], result


def test_timeout_success_hidden_reset_and_budget_mismatch_are_rejected() -> None:
    record = minimal_record("reactive_disturbed")
    record["success"] = True
    record["reset_count"] = 1
    record["steps_after_event"] = 2
    errors = validate_episode_record(record)
    assert any("timeout cannot count as success" in error for error in errors)
    assert any("reset or rollback" in error for error in errors)
    assert any("do not sum" in error for error in errors)


def test_pair_validator_detects_unfair_post_event_budget() -> None:
    records = [minimal_record(method) for method in METHOD_NAMES]
    records[-1]["post_event_policy_step_budget"] = 151
    result = validate_pair_records(records)
    assert not result["passed"]
    assert any("post_event_policy_step_budget mismatch" in error for error in result["errors"])


def test_detected_event_miss_is_logged_without_inventing_high_level_calls() -> None:
    records = [minimal_record(method) for method in METHOD_NAMES]
    detector = {
        "confusion_counts": {"tp": 0, "fp": 0, "fn": 1},
        "event_latency_steps": None,
    }
    for record in records:
        record["event_source"] = "detected"
        if record["method"] != "clean":
            record["event"] = None
            record["fresh_observation_hash"] = None
            record["recovery_input_hash"] = None
            record["detector"] = detector
        if record["method"] in {"history_augmented_full_regeneration", "cope_patch"}:
            record["high_level_call_count"] = 0
            record["prompt_tokens"] = 0
            record["completion_tokens"] = 0
            record["provider_calls"] = []
            record["regenerated_state"] = None
            record["constraint_state_before"] = None
            record["constraint_state_after"] = None
            record["unaffected_slot_preservation"] = None
    result = validate_pair_records(records)
    assert result["passed"], result
