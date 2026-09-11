from __future__ import annotations

from dataclasses import replace
import pytest

from cope_benchmark.repeated_v2.config import load_config
from cope_benchmark.repeated_v2.evidence import EventLeakageError
from cope_benchmark.repeated_v2.enums import MethodName
from cope_benchmark.repeated_v2.production_runtime import (
    NominalPlanner, PublicEventEvidenceBuilder, PublicRuntimeVerifier,
    create_runtime_assembly,
)
from cope_benchmark.repeated_v2.pilot import validate_runtime_assembly
from cope_benchmark.repeated_v2.schema import (
    ContinuationState, ExecutionContext, PlanningProblem,
)


def _observation(*, source=(0.0, 0.0, 0.1), target=(0.0, 0.0, 0.0)):
    return {"agent_visible_named_poses": {
        "object": {"position": list(source), "quaternion": [0.0, 0.0, 0.0, 1.0]},
        "basket": {"position": list(target), "quaternion": [0.0, 0.0, 0.0, 1.0]},
    }}


def test_event_builder_rejects_recursively_poisoned_hidden_state():
    builder = PublicEventEvidenceBuilder()
    with pytest.raises(EventLeakageError):
        builder.build(
            event_id="event-1", event_index=1,
            previous_public_observation=_observation(),
            current_public_observation=_observation(source=(0.1, 0.0, 0.1)),
            public_proprioception=[0.0] * 8, public_user_message=None,
            public_task_catalog={"objects": ["object"], "entities": ["basket"]},
            previously_committed_public_evidence=[{"nested": {"canonical_state": "poison"}}],
            observation_ref="obs-1", timestamp=1,
        )


def test_public_verifier_preserves_supplied_binding_and_fails_closed():
    verifier = PublicRuntimeVerifier()
    result = verifier.evaluate_goal(
        observation=_observation(), occurrence_id="wrong-but-accepted@7",
        predicate="in", arguments=("object", "basket_contain_region"),
        evidence_ids=("e1",), timestamp=4, observation_version=4, evidence_timestamp=4,
    )
    assert result.occurrence_id == "wrong-but-accepted@7"
    assert result.status == "satisfied"
    stale = verifier.evaluate_goal(
        observation=_observation(), occurrence_id="goal@1", predicate="in",
        arguments=("object", "basket_contain_region"), evidence_ids=("e1",),
        timestamp=5, observation_version=5, evidence_timestamp=4,
    )
    assert (stale.status, stale.confidence) == ("unknown", 0.0)
    uncertain = verifier.evaluate_goal(
        observation={}, occurrence_id="goal@1", predicate="in",
        arguments=("object", "basket_contain_region"), evidence_ids=("e2",),
        timestamp=6, observation_version=6, evidence_timestamp=6,
    )
    assert uncertain.status == "unknown"


def test_nominal_planner_does_not_reconstruct_omitted_or_wrong_goals():
    planner = NominalPlanner()
    context = ExecutionContext((), (), ContinuationState(None, None, 0, None, (), None, 0))
    omitted = PlanningProblem(
        "problem-omitted", MethodName.FULL_STATE_REGENERATION, 0, (), ("missing@1",),
        (), (), (), (), (), (), (), {},
    )
    assert planner.solve(problem=omitted, context=context).macro_actions == ()
    wrong = PlanningProblem(
        "problem-wrong", MethodName.FULL_STATE_REGENERATION, 0, (), ("wrong@9",),
        ({"occurrence_id": "wrong@9", "predicate": "in",
          "arguments": ("wrong_object", "wrong_target")},),
        (), (), (), (), (), (), {},
    )
    plan = planner.solve(problem=wrong, context=context)
    assert [macro["target_occurrence_id"] for macro in plan.macro_actions] == ["wrong@9"]
    assert "wrong_object" in plan.macro_actions[0]["compiled_instruction"]["instruction"]


def test_runtime_verifier_identity_is_public_and_separate_from_sealed_evaluator():
    identity = PublicRuntimeVerifier.identity
    assert identity["uses_hidden_canonical_state"] is False
    assert identity["uses_privileged_simulator_state"] is False
    assert identity["provider_id"] != "sealed_dynamic_v2.1"


def test_production_runtime_assembly_passes_complete_zero_call_gate():
    config = load_config("configs/repeated_interruptions_v2_1_pilot.yaml")
    assembly = create_runtime_assembly(config)
    declared = assembly.identity["vla"]
    assembly = replace(assembly, vla_asset_preflight=lambda: {
        **{name: declared[name] for name in (
            "provider_id", "version", "uses_hidden_canonical_state",
            "uses_privileged_simulator_state", "input_schema_hash", "output_schema_hash")},
        "checkpoint_sha256": declared["checkpoint_sha256"],
        "learned_policy": True, "uses_privileged_state": False,
        "action_dim": 7, "max_chunk_horizon": 1,
    })
    report = validate_runtime_assembly(assembly)
    assert report["status"] == "PASS"
    assert report["provider_calls"] == report["vla_calls"] == report["simulator_resets"] == 0
    assert report["public_sealed_separation"] is True
    assert report["same_components_across_methods"] is True
