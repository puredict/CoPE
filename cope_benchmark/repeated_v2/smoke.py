"""No-network all-arm oracle-answer qualification for the controlled backend."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .adapters import create_adapter
from .canonical import canonical_sha256, to_primitive
from .enums import EventFamily, MethodName
from .oracle_fixtures import build_oracle_fixture_chain, initial_fixture
from .patch_contract import SUMMARY_VERSION
from .planner_backend import ControlledMechanismBackend
from .provider import FixtureReasoner, ReasonerConfig, ReasonerGateway, assert_same_backbone
from .schema import HiddenCanonicalEffect


def run_oracle_fixture_smoke() -> dict[str, Any]:
    chain = build_oracle_fixture_chain()
    initial, context = initial_fixture()
    goals = [{"predicate": "inside", "arguments": ["mug", "shelf"], "value": True},
             {"predicate": "inside", "arguments": ["plate", "rack"], "value": True}]
    task = {"episode_id": "qualification", "instruction": "Put the mug on the shelf and the plate in the rack.",
            "goals": goals, "current_subgoal": goals[0],
            "skills": [{"name": "place", "preconditions": [], "effects": [goals[0]]},
                       {"name": "place_plate", "preconditions": [], "effects": [goals[1]]}]}
    # The fixture counter conservatively counts UTF-8 bytes, not model tokens.
    # A common byte ceiling keeps this offline audit independent of tokenizers.
    config = ReasonerConfig(provider="offline_fixture", model="oracle_answer_fixture",
                            max_input_tokens=262144, max_output_tokens=262144)
    adapters, gateways = {}, []
    for method in MethodName:
        if method in (MethodName.CLASSICAL_EXECUTION_MONITOR, MethodName.ORACLE_PERSISTENT_UPDATE):
            adapters[method] = create_adapter(method)
        else:
            key = {MethodName.COPE_TYPED_EDIT: "typed", MethodName.GENERIC_PERSISTENT_EDIT: "generic",
                   MethodName.FULL_STATE_REGENERATION: "full_state"}.get(method, "directive")
            responses = [cell[key] for cell in chain]
            if method is MethodName.SUMMARY_MEMORY_REPLAN:
                responses = [{"schema_version": SUMMARY_VERSION,
                              "summary": f"Public requests through event {i}; preserve the verified plate milestone.",
                              "planning_directive": response} for i, response in enumerate(responses, 1)]
            gateway = ReasonerGateway(FixtureReasoner(responses), config)
            gateways.append(gateway)
            adapters[method] = create_adapter(method, gateway=gateway)
        adapters[method].start_episode(task=task, ledger=initial, context=context)
    assert_same_backbone(gateways)
    backend = ControlledMechanismBackend()
    rows, history, parities = [], [], []
    for cell in chain:
        step = cell["step"]
        history.append({"event": step.event.to_dict()})
        for method, adapter in adapters.items():
            kwargs = dict(evidence=step.event, public_history=history, context=context)
            if method is MethodName.ORACLE_PERSISTENT_UPDATE:
                kwargs.update(canonical_ledger=cell["after"], hidden_effect=HiddenCanonicalEffect(
                    event_id=step.event.event_id, true_family=(EventFamily.GOAL_RECEPTACLE_OR_GROUNDING_CHANGED,
                        EventFamily.TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE,
                        EventFamily.USER_ADDS_PERSISTENT_PREFERENCE,
                        EventFamily.TOOL_OR_TARGET_AVAILABLE_AGAIN,
                        EventFamily.USER_REPLACES_ACTIVE_GOAL, EventFamily.USER_CANCELS_ACTIVE_GOAL,
                        EventFamily.USER_REISSUES_RETIRED_GOAL,
                        EventFamily.USER_ADDS_PERSISTENT_PREFERENCE)[step.event.event_index - 1],
                    affected_occurrence_ids=tuple(cell["typed"]["affected_scope"]),
                    canonical_effect={"diagnostic_fixture": True}, simulator_intervention={}))
            else:
                kwargs["evidence_records"] = step.evidence
            outcome = adapter.on_event(**kwargs)
            if not outcome.accepted:
                raise AssertionError(f"Fixture rejected for {method.value} event {step.event.event_index}: {outcome.rejection}")
            problem = adapter.compile_state(context=context)
            trace = backend.execute(problem=problem, context=context)
            if trace.status != "succeeded":
                raise AssertionError(f"Controlled fixture blocked for {method.value}: {trace.diagnostics}")
            # A snapshot roundtrip must preserve the method's own accepted state.
            snapshot = adapter.snapshot()
            adapter.restore(snapshot)
            if canonical_sha256(adapter.compile_state(context=context)) != canonical_sha256(problem):
                raise AssertionError("Method snapshot changed the compiled problem")
            rows.append({"method": method.value, "event_index": step.event.event_index,
                         "accepted": outcome.accepted, "privileged": outcome.privileged,
                         "result_kind": trace.result_kind, "execution_status": trace.status,
                         "planning_problem_sha256": canonical_sha256(problem),
                         "executed_occurrence_ids": list(trace.executed_occurrence_ids),
                         "diagnostics": list(trace.diagnostics)})
        typed_hash = adapters[MethodName.COPE_TYPED_EDIT].last_semantic_information_sha256
        generic_hash = adapters[MethodName.GENERIC_PERSISTENT_EDIT].last_semantic_information_sha256
        if typed_hash != generic_hash:
            raise AssertionError("Persistent input semantic information mismatch")
        parities.append(typed_hash)
    calls = sum(gateway.reasoner.calls for gateway in gateways)
    if calls != 56 or any(len(gateway.logs) != 8 for gateway in gateways):
        raise AssertionError("Every generative arm must consume exactly one fixture call per event")
    logs = [{"method": method.value, **asdict(log)} for method, adapter in adapters.items()
            if hasattr(adapter, "gateway") for log in adapter.gateway.logs]
    return {"status": "PASS", "result_kind": "controlled_mechanism",
            "qualification_only": True, "external_provider_calls": 0, "vla_calls": 0,
            "fixture_reasoner_calls": calls, "methods": len(adapters), "events_per_method": 8,
            "accepted_event_cells": len(rows), "fixture_sha256": canonical_sha256(chain),
            "information_parity_sha256_by_event": parities, "configuration": config.to_dict(),
            "rows": rows, "exact_prompt_logs": logs,
            "claim": "Offline parser, adapter, state and plan qualification only; no model or robot success estimate."}
