"""Explicit synthetic inputs for unit tests only; forbidden by formal entrypoints."""

from cope_benchmark.repeated_v2.task_calibration import CALIBRATION_SCHEMA_VERSION, calibration_grid
from cope_benchmark.repeated_v2.calibration_v2_1 import CALIBRATION_RECORD_VERSION
from cope_benchmark.repeated_v2.task_catalog import (
    CATALOG_SCHEMA_VERSION, CATALOG_SCHEMA_VERSION_V2_1, EVENT_FAMILIES,
    STRUCTURAL_CHECKS, TaskCatalog,
)


def calibration_records(task_id: int = 0, successes: int = 5) -> list[dict]:
    return [
        {"schema_version": CALIBRATION_SCHEMA_VERSION, **cell,
         "success": index < successes, "status": "completed", "learned_policy": True,
         "privileged_policy_state": False, "clean_episode": True, "policy_id": "synthetic-policy-for-unit-tests",
         "checkpoint_sha256": "a" * 64, "protocol_sha256": "b" * 64,
         "initial_state_sha256": f"{cell['initial_state_id'] + 1:064x}",
         "evidence_ref": f"synthetic-fixture://calibration/{task_id}/{index}",
         "evidence_sha256": f"{100 + task_id * 10 + index:064x}",
         "provenance_kind": "synthetic_test_fixture", "max_policy_steps": 260}
        for index, cell in enumerate(calibration_grid((task_id,)))
    ]


def synthetic_catalog(task_count: int = 10) -> TaskCatalog:
    """All ten enumerated, task_count eligible; the rest have clean rate 1.0."""
    if type(task_count) is not int or not 0 <= task_count <= 10:
        raise ValueError("task_count must be in 0..10")
    tasks = []
    for task_id in range(10):
        goals = [{"family_key": f"goal:{name}:bin", "predicate": "in", "arguments": [name, "bin"],
                  "source_ref": "synthetic-fixture://semantics"} for name in ("cube", "ball")]
        tasks.append({
            "task_id": task_id, "task_name": f"synthetic_task_{task_id}",
            "original_instruction": "Synthetic fixture: put cube and ball in bin",
            "object_aliases": {"cube": "cube", "ball": "ball"}, "receptacle_region_aliases": {"bin": "bin"},
            "initial_achievement_goals": goals,
            "maintenance_invariants": [{"predicate": "preserve", "arguments": ["completed_cube"]}],
            "hard_safety_constraints": [{"predicate": "avoid", "arguments": ["no_go"], "source_ref": "synthetic-fixture://safety"}],
            "soft_preference_templates": [{"predicate": "prefer", "arguments": ["cube_before_ball"], "source_ref": "synthetic-fixture://preference"}],
            "milestone_predicates": [{"milestone_id": f"placed_{name}", "predicate": "in", "arguments": [name, "bin"],
                                      "verifier": "synthetic-verifier", "independent": True, "can_remain_valid": True,
                                      "source_ref": "synthetic-fixture://milestones"} for name in ("cube", "ball")],
            "alternative_valid_goals": [{"family_key": "goal:ball:tray", "predicate": "in", "arguments": ["ball", "tray"], "source_ref": "synthetic-fixture://alternative"}],
            "replaceable_goal_families": [goals[1]["family_key"]],
            "safe_event_injection_poses": {family: {"entity": "ball", "pose": [0.1, 0.2, 0.3],
                                                    "evidence_refs": ["synthetic-fixture://feasibility"]}
                                           for family in EVENT_FAMILIES},
            "supported_event_families": list(EVENT_FAMILIES),
            "semantic_triggers": {family: {"predicate": "verified_cube_placement", "earliest_policy_step": 10,
                                           "latest_policy_step": 250, "min_steps_since_previous_event": 10,
                                           "physical_feasibility_guard": "certified_event_pose"} for family in EVENT_FAMILIES},
            "dynamic_evaluator_predicates": [{"predicate": "in", "arguments": ["cube", "bin"]}],
            "planner_compiler_metadata": {"accepted_state_only": True, "predicate_vocabulary": ["in", "avoid", "prefer"]},
            "initial_state_digests": {str(i): f"{i + 1:064x}" for i in range(5)},
            "structural_checks": {key: {"passed": True, "evidence_refs": ["synthetic-fixture://structure"]} for key in STRUCTURAL_CHECKS},
            "event_feasibility": {family: {"passed": True, "evidence_refs": ["synthetic-fixture://feasibility"],
                                           "covered_state_ids": list(range(5))} for family in EVENT_FAMILIES},
            "calibration_records": calibration_records(task_id, 5 if task_id < task_count else 10),
            "source_refs": [{"uri": "synthetic-fixture://semantics", "sha256": "c" * 64}], "unresolved_fields": [],
        })
    return TaskCatalog.from_dict({"schema_version": CATALOG_SCHEMA_VERSION, "task_suite": "libero_10",
                                  "selection_rule": "all_semantically_eligible", "provenance_kind": "synthetic_test_fixture", "tasks": tasks})


def synthetic_catalog_v2_1(task_count: int = 10) -> TaskCatalog:
    """Complete v2.1 fixture with exactly ``task_count`` eligible tasks."""
    if type(task_count) is not int or not 0 <= task_count <= 10:
        raise ValueError("task_count must be in 0..10")
    raw = synthetic_catalog().to_dict()
    raw["schema_version"] = CATALOG_SCHEMA_VERSION_V2_1
    for task in raw["tasks"]:
        task_id = task["task_id"]
        task["initial_state_digests"] = {
            str(state_id): f"{task_id * 100 + state_id + 1:064x}" for state_id in range(50)
        }
        task["event_feasibility"] = {
            family: {"passed": True, "evidence_refs": ["synthetic-fixture://feasibility-v2.1"],
                     "covered_state_ids": list(range(15, 20))}
            for family in EVENT_FAMILIES
        }
        task["planner_compiler_metadata"]["unsupported_event_families"] = []
        task["planner_compiler_metadata"]["calibration_protocol_projection_sha256"] = "e" * 64
        successes = 5 if task_id < task_count else 10
        records = []
        for state_id in range(10):
            success = state_id < successes
            records.append({
                "schema_version": CALIBRATION_RECORD_VERSION,
                "task_id": task_id,
                "initial_state_id": state_id,
                "policy_seed": 101,
                "learned_policy": True,
                "uses_privileged_state": False,
                "clean_episode": True,
                "all_action_validations_pass": True,
                "manual_intervention": False,
                "provider_id": "openvla_native",
                "policy_model_id": "openvla-7b-finetuned-libero-10",
                "checkpoint_sha256": "d36eaa2a334cd52f4a3a94558cf90d82584743ea772fabf76f9e4372e7076076",
                "collection_ceiling_policy_steps": 520,
                "policy_steps_consumed": 200 + state_id if success else 520,
                "success": success,
                "status": "success" if success else "timeout",
                "completion_policy_steps": 200 + state_id if success else None,
                "protocol_sha256": "f" * 64,
                "initial_state_sha256": task["initial_state_digests"][str(state_id)],
                "evidence_ref": f"synthetic-fixture://calibration-v2.1/{task_id}/{state_id}",
                "evidence_sha256": f"{1000 + task_id * 10 + state_id:064x}",
                "full_trace_sha256": f"{2000 + task_id * 10 + state_id:064x}",
                "raw_policy_action_sequence_sha256": f"{3000 + task_id * 10 + state_id:064x}",
                "environment_policy_action_sequence_sha256": f"{4000 + task_id * 10 + state_id:064x}",
                "action_trajectory_sha256": f"{4000 + task_id * 10 + state_id:064x}",
                "adapter_source_sha256": "1" * 64,
                "runtime_client_sha256": "2" * 64,
                "runtime_inference_sha256": "3" * 64,
                "termination_reason": "task_success" if success else "collection_ceiling_reached",
                "inference_seconds": float(10 + state_id),
                "wall_seconds": float(20 + state_id),
            })
        task["calibration_records"] = records
    return TaskCatalog.from_dict(raw)
