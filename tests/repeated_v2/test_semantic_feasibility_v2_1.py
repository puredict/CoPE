from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = spec_from_file_location(
    "semantic_feasibility_v2_1",
    ROOT / "tools/audit_repeated_v2_1_semantic_feasibility.py",
)
MODULE = module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_reserve_parameter_selection_requires_all_five_states():
    rows = [
        {"state": state, "delta": [0.06, 0.0], "passed": state != 24}
        for state in range(20, 25)
    ] + [
        {"state": state, "delta": [-0.06, 0.0], "passed": True}
        for state in range(20, 25)
    ]
    assert MODULE._select(rows, "delta", MODULE.TARGET_DELTAS) == (-0.06, 0.0)


def test_lifecycle_audit_cancels_and_reissues_without_restoring_old_id():
    result = MODULE._lifecycle_audit(1, 15)
    cancelled = result["USER_CANCELS_ACTIVE_GOAL"]
    reissued = result["USER_REISSUES_RETIRED_GOAL"]
    assert cancelled["cancelled_goal_no_longer_required"]
    assert cancelled["dynamic_evaluator_correct"]
    assert cancelled["pure_compiler"]["passed"]
    assert reissued["fresh_occurrence_id"]
    assert reissued["retired_occurrence_not_restored"]
    assert reissued["new_occurrence_id"].endswith("@2")
    assert reissued["dynamic_evaluator_correct"]


def test_source_grounded_replacement_uses_existing_task_predicate_signature():
    result = MODULE._lifecycle_audit(4, 15)["USER_REPLACES_ACTIVE_GOAL"]
    assert result["replacement_active_occurrence"]
    assert result["replaced_occurrence_retired"]
    assert result["alternative_goal"]["predicate"] == "on"
    assert result["alternative_goal"]["arguments"] == ["red_coffee_mug_1", "plate_1"]
    assert result["pure_compiler"]["passed"]


def test_semantic_trigger_is_reachable_without_fixed_step_fallback():
    result = MODULE._trigger_audit("USER_CANCELS_ACTIVE_GOAL", "cream_cheese_1")
    assert result["semantic_trigger_reached"]
    assert result["inside_registered_window"]
    assert result["semantic_trigger"]["predicate"] == "user_instruction_targets_active_occurrence"

