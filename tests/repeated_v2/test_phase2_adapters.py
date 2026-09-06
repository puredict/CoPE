import copy
import json

import pytest

from cope_benchmark.repeated_v2.adapters import create_adapter
from cope_benchmark.repeated_v2.enums import MethodName
from cope_benchmark.repeated_v2.history import FrozenRetrieverConfig, PublicHistoryIndex
from cope_benchmark.repeated_v2.oracle_fixtures import build_oracle_fixture_chain, initial_fixture
from cope_benchmark.repeated_v2.prompts import (
    LeakageError, assert_semantic_information_parity, build_messages,
    normalized_semantic_facts, scan_public_input,
)
from cope_benchmark.repeated_v2.provider import (
    FixtureReasoner, ReasonerConfig, ReasonerGateway, ReasonerResponse, assert_same_backbone,
)


def gateway(responses):
    return ReasonerGateway(FixtureReasoner(responses), ReasonerConfig(
        provider="no-provider-fixture", model="fixture", max_input_tokens=200000, max_output_tokens=200000))


def fixture_response(method, step):
    return {MethodName.COPE_TYPED_EDIT: step["typed"], MethodName.GENERIC_PERSISTENT_EDIT: step["generic"],
            MethodName.FULL_STATE_REGENERATION: step["full_state"],
            MethodName.SUMMARY_MEMORY_REPLAN: {"schema_version": "cope-repeated-v2/summary-1",
                "summary": "Keep the public request and progress in memory.", "planning_directive": step["directive"]}
            }.get(method, step["directive"])


GENERATIVE = list(MethodName)[:7]


@pytest.mark.parametrize("method", GENERATIVE)
def test_one_event_call_exact_logs_and_snapshot(method):
    ledger, context = initial_fixture()
    steps = build_oracle_fixture_chain()
    gw = gateway([fixture_response(method, step) for step in steps[:2]])
    adapter = create_adapter(method, gateway=gw)
    adapter.start_episode(task={"episode_id": "qualification", "instruction": "Put the mug on the shelf."},
                          ledger=ledger, context=context)
    history = []
    for step in steps[:2]:
        history.append(step["step"].event.to_dict())
        outcome = adapter.on_event(evidence=step["step"].event, public_history=history, context=context,
                                  evidence_records=step["step"].evidence)
        assert outcome.accepted, outcome.rejection
        assert outcome.fixture and not outcome.privileged
        assert adapter.compile_state(context=context).source_method == method
    assert gw.reasoner.calls == 2
    assert len(gw.logs) == 2
    assert gw.logs[0].response == json.dumps(fixture_response(method, steps[0]), ensure_ascii=False)
    assert gw.logs[0].input_tokens > 0 and gw.logs[0].output_tokens > 0
    assert gw.logs[0].token_count_kind == "fixture_utf8_bytes"
    clone = create_adapter(method, gateway=gateway([]))
    clone.restore(json.loads(json.dumps(adapter.snapshot())))
    assert clone.compile_state(context=context) == adapter.compile_state(context=context)
    assert clone.snapshot() == adapter.snapshot()


def test_persistent_semantic_parity_includes_checks_relations_provenance():
    from cope_benchmark.repeated_v2.generic_engine import apply_generic
    from cope_benchmark.repeated_v2.state_engine import apply_cope
    ledger, context = initial_fixture()
    generic = ledger
    for row in build_oracle_fixture_chain():
        step = row["step"]
        left = normalized_semantic_facts(ledger=ledger, context=context, evidence=step.event, public_history=[])
        right = normalized_semantic_facts(ledger=generic, context=context, evidence=step.event, public_history=[])
        assert_semantic_information_parity(left, right)
        for method, facts in [(MethodName.COPE_TYPED_EDIT, left), (MethodName.GENERIC_PERSISTENT_EDIT, right)]:
            prompt = build_messages(method=method.value, task={"episode_id": "qualification"},
                                    evidence=step.event, memory={"semantic_facts": facts})
            assert "Exact JSON schema:" in prompt[-1]["content"]
            scan_public_input(prompt, generic=method == MethodName.GENERIC_PERSISTENT_EDIT)
        ledger = apply_cope(ledger, row["typed"], context=context, evidence_records=step.evidence,
                            event_id=step.event.event_id, event_timestamp=step.event.timestamp)
        generic = apply_generic(generic, row["generic"], context=context, evidence_records=step.evidence,
                                event_id=step.event.event_id, event_timestamp=step.event.timestamp)
    facts = normalized_semantic_facts(ledger=ledger, context=context, evidence={}, public_history=[])
    assert any(record.get("kind") == "validation" for record in facts["ledger"]["semantic_history"])
    assert facts["ledger"]["slots"][0]["provenance"]


@pytest.mark.parametrize("payload", [
    {"public": {"expected_operations": []}}, {"text": '{"canonical_state":{"x":1}}'},
    {"text": "The method is full_history_replan"}, {"text": "/Users/person/private.json"},
    {"text": "TARGET_OBJECT_DISPLACED"}, {"x": float("nan")}, {"x": float("inf")},
])
def test_recursive_leakage_rejected(payload):
    with pytest.raises(LeakageError):
        scan_public_input(payload)


def test_history_operator_labels_rejected_and_public_only_rag_budget():
    index = PublicHistoryIndex(FrozenRetrieverConfig(token_budget=240))
    records = [{"text": "The mug moved to the side table."}, {"text": "Place the plate in the rack."}]
    index.ingest(records)
    result = index.retrieve({"hypothesis": "mug side table"})
    assert result and result[0]["sequence"] == 0
    assert len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()) <= 240
    with pytest.raises(ValueError):
        index.ingest(records + [{"text": "Use RESTORE now"}])
    with pytest.raises(ValueError):
        index.ingest([{ "text": "rewritten"}])
    assert len(index.chunks) == 2


def test_same_backbone_and_no_semantic_retry_after_malformed_output():
    ledger, context = initial_fixture()
    step = build_oracle_fixture_chain()[0]["step"]
    gw = gateway(["not JSON"])
    adapter = create_adapter(MethodName.COPE_TYPED_EDIT, gateway=gw)
    adapter.start_episode(task={"episode_id": "qualification"}, ledger=ledger, context=context)
    outcome = adapter.on_event(evidence=step.event, public_history=[], context=context)
    assert not outcome.accepted and adapter.ledger == ledger
    with pytest.raises(ValueError, match="already consumed"):
        adapter.on_event(evidence=step.event, public_history=[], context=context)
    assert gw.reasoner.calls == 1
    assert_same_backbone([gw, gateway([])])
    different = ReasonerGateway(FixtureReasoner([]), ReasonerConfig(provider="other", model="fixture"))
    with pytest.raises(ValueError):
        assert_same_backbone([gw, different])


def test_summary_rejection_is_atomic_and_no_ledger_leak_to_local():
    ledger, context = initial_fixture()
    steps = build_oracle_fixture_chain()[:2]
    responses = [fixture_response(MethodName.SUMMARY_MEMORY_REPLAN, row) for row in steps]
    responses[1]["summary"] = "See /Users/person/private.txt"
    adapter = create_adapter(MethodName.SUMMARY_MEMORY_REPLAN, gateway=gateway(responses))
    adapter.start_episode(task={"episode_id": "qualification"}, ledger=ledger, context=context)
    assert adapter.on_event(evidence=steps[0]["step"].event, public_history=[], context=context).accepted
    before = copy.deepcopy(adapter.directive), adapter.summary, adapter.revision
    assert not adapter.on_event(evidence=steps[1]["step"].event, public_history=[], context=context).accepted
    assert (adapter.directive, adapter.summary, adapter.revision) == before
    local = create_adapter(MethodName.SKILL_LOCAL_REPLAN, gateway=gateway([steps[0]["directive"]]))
    local.start_episode(task={"episode_id": "qualification", "current_subgoal": "place mug"},
                        ledger=ledger, context=context)
    assert local.on_event(evidence=steps[0]["step"].event, public_history=[], context=context).accepted
    assert local.ledger is None
    memory = json.loads(local.gateway.logs[0].messages[2]["content"])
    assert "semantic_facts" not in memory and "ledger" not in memory
    assert memory["active_skill"] == context.continuation.active_skill


def test_full_state_omitted_semantics_stay_omitted():
    ledger, context = initial_fixture()
    row = build_oracle_fixture_chain()[0]
    response = copy.deepcopy(row["full_state"])
    response.update(slots=[], relations=[], semantic_history=[], initial_facts=[], progress_certificates=[],
                    continuation_assumptions={})
    adapter = create_adapter(MethodName.FULL_STATE_REGENERATION, gateway=gateway([response]))
    adapter.start_episode(task={"episode_id": "qualification"}, ledger=ledger, context=context)
    assert adapter.on_event(evidence=row["step"].event, public_history=[], context=context).accepted
    problem = adapter.compile_state(context=context)
    assert not problem.remaining_goals and not problem.progress_certificates and not problem.continuation_assumptions
    assert len(adapter.ledger.history_records) == 1


def test_classical_monitor_uses_skills_and_keeps_no_commitment_ledger():
    ledger, context = initial_fixture()
    step = build_oracle_fixture_chain()[0]["step"]
    monitor = create_adapter(MethodName.CLASSICAL_EXECUTION_MONITOR)
    monitor.start_episode(task={"episode_id": "qualification", "goals": [{"predicate": "ready", "arguments": []}],
        "skills": [{"name": "prepare", "preconditions": [], "effects": [{"predicate": "ready", "arguments": []}]}]},
        ledger=ledger, context=context)
    outcome = monitor.on_event(evidence=step.event, public_history=[], context=context)
    assert outcome.accepted
    problem = monitor.compile_state(context=context)
    assert problem.remaining_goals[0]["predicate"] == "ready"
    assert problem.continuation_assumptions["ordered_macro_plan"][0]["skill"] == "prepare"
    assert problem.continuation_assumptions["execution_mode"] == "explicit_skills"
    assert not hasattr(monitor, "ledger")
    snapshot = monitor.snapshot()
    assert "lifecycle" not in json.dumps(snapshot) and "provenance" not in json.dumps(snapshot)


@pytest.mark.parametrize("method", list(MethodName))
def test_all_arms_compile_initial_public_task_without_event_reasoning(method):
    ledger, context = initial_fixture()
    gw = gateway([]) if method in GENERATIVE else None
    adapter = create_adapter(method, gateway=gw)
    adapter.start_episode(task={"episode_id": "qualification", "instruction": "Put the mug on the shelf."},
                          ledger=ledger, context=context)
    problem = adapter.compile_state(context=context)
    assert problem.source_method == method and problem.source_revision == 0
    assert {(goal["predicate"], tuple(goal["arguments"])) for goal in problem.remaining_goals} == {
        ("inside", ("mug", "shelf")), ("inside", ("plate", "rack"))}
    if gw is not None:
        assert gw.reasoner.calls == 0 and not gw.logs
    if method in GENERATIVE[3:]:
        assert adapter.ledger is None


@pytest.mark.parametrize("text", ["evidence_matched", "The setting is token_matched today.",
                                  "A nested TOKEN_MATCHED label"])
def test_condition_labels_do_not_enter_prompt_text(text):
    with pytest.raises(LeakageError):
        scan_public_input({"message": json.dumps({"quoted": text})})


@pytest.mark.parametrize("key", ["RESTORE", "TARGET_OBJECT_DISPLACED"])
def test_rag_rejects_operator_or_event_family_as_mapping_key(key):
    index = PublicHistoryIndex()
    with pytest.raises(LeakageError):
        index.ingest([{"message": {key: "a public looking value"}}])
    assert not index.chunks


def test_persistent_prompts_have_same_semantic_information_across_full_fixture_chain():
    ledger, context = initial_fixture()
    rows = build_oracle_fixture_chain()
    adapters = [create_adapter(method, gateway=gateway([fixture_response(method, row) for row in rows]))
                for method in GENERATIVE[:3]]
    for adapter in adapters:
        adapter.start_episode(task={"episode_id": "qualification"}, ledger=ledger, context=context)
    history = []
    for row in rows:
        step = row["step"]
        history.append(step.event.to_dict())
        for adapter in adapters:
            outcome = adapter.on_event(evidence=step.event, public_history=history, context=context,
                                       evidence_records=step.evidence)
            assert outcome.accepted, outcome.rejection
        facts = [json.loads(adapter.gateway.logs[-1].messages[2]["content"])["semantic_facts"]
                 for adapter in adapters]
        for right in facts[1:]:
            assert_semantic_information_parity(facts[0], right)


def test_full_state_keeps_only_allocation_identity_when_it_omits_semantics_and_resumes():
    from cope_benchmark.repeated_v2.oracle_fixtures import new_slot
    ledger, context = initial_fixture()
    rows = build_oracle_fixture_chain()
    omitted = copy.deepcopy(rows[0]["full_state"])
    omitted.update(slots=[], relations=[], semantic_history=[], initial_facts=[],
                   progress_certificates=[], continuation_assumptions={})
    regenerated = copy.deepcopy(omitted)
    regenerated["base_revision"] = 1
    family = "goal:mug:shelf"
    regenerated["slots"] = [{**new_slot(family, "inside", ("mug", "shelf")),
        "occurrence_id": family + "@2", "created_event_id": "event-2", "retired_event_id": None}]
    adapter = create_adapter(MethodName.FULL_STATE_REGENERATION, gateway=gateway([omitted]))
    adapter.start_episode(task={"episode_id": "qualification"}, ledger=ledger, context=context)
    assert adapter.on_event(evidence=rows[0]["step"].event, public_history=[], context=context).accepted
    clone = create_adapter(MethodName.FULL_STATE_REGENERATION, gateway=gateway([regenerated]))
    clone.restore(json.loads(json.dumps(adapter.snapshot())))
    assert not clone.ledger.slots
    assert clone.identity_registry[family + "@1"] == family
    outcome = clone.on_event(evidence=rows[1]["step"].event, public_history=[], context=context)
    assert outcome.accepted, outcome.rejection
    assert [slot.occurrence_id for slot in clone.ledger.slots] == [family + "@2"]
    memory = json.loads(clone.gateway.logs[-1].messages[2]["content"])
    assert memory["semantic_facts"]["ledger"]["slots"] == []
    assert memory["semantic_facts"]["accepted_planning_fields"] == {
        "initial_facts": [], "progress_certificates": [], "continuation_assumptions": {}}
    assert "identity_registry" not in memory


def test_token_matched_truncation_preserves_semantic_parity_and_actual_prompt_digest():
    from cope_benchmark.repeated_v2.prompts import semantic_information_sha256
    ledger, context = initial_fixture()
    step = build_oracle_fixture_chain()[0]["step"]
    task = {"episode_id": "qualification"}
    history = [{"text": f"public observation {i}: " + "mug " * 240} for i in range(8)]
    # Measure the common contract envelope once; allow two history entries.
    prototypes = [create_adapter(method, gateway=gateway([])) for method in GENERATIVE[:3]]
    sizes = []
    for adapter in prototypes:
        adapter.start_episode(task=task, ledger=ledger, context=context)
        adapter.public_history = copy.deepcopy(history[:2])
        sizes.append(adapter.gateway.reasoner.count_tokens(adapter._messages(step.event, context)))
    config = ReasonerConfig(provider="no-provider-fixture", model="fixture", setting="token_matched",
                            max_input_tokens=max(sizes), max_output_tokens=200000)
    facts = []
    for method in GENERATIVE[:3]:
        adapter = create_adapter(method, gateway=ReasonerGateway(FixtureReasoner([]), config))
        adapter.start_episode(task=task, ledger=ledger, context=context)
        adapter.public_history = copy.deepcopy(history)
        messages = adapter._messages(step.event, context)
        memory = json.loads(messages[2]["content"])
        facts.append(memory["semantic_facts"])
        assert 0 < len(facts[-1]["relevant_trace"]) < len(history)
        assert semantic_information_sha256(facts[-1]) == adapter.last_semantic_information_sha256
        assert adapter.gateway.reasoner.count_tokens(messages) <= config.max_input_tokens
    for right in facts[1:]:
        assert_semantic_information_parity(facts[0], right)


@pytest.mark.parametrize("method", [MethodName.FULL_STATE_REGENERATION, MethodName.FULL_HISTORY_REPLAN])
def test_snapshot_is_detached_from_live_adapter_state(method):
    ledger, context = initial_fixture()
    adapter = create_adapter(method, gateway=gateway([]))
    adapter.start_episode(task={"episode_id": "qualification", "skills": [
        {"name": "place", "preconditions": [], "effects": []}]}, ledger=ledger, context=context)
    original = adapter.snapshot()
    snapshot = adapter.snapshot()
    snapshot["task"]["skills"][0]["name"] = "changed"
    snapshot["identity_registry"]["injected@1"] = "injected"
    snapshot["public_history"].append({"text": "changed"})
    if snapshot["directive"] is not None:
        snapshot["directive"]["remaining_goals"].clear()
    assert adapter.snapshot() == original


@pytest.mark.parametrize("field,bad", [
    ("provider", ""), ("model", "  "), ("seed", True), ("seed", 0.0),
    ("max_input_tokens", True), ("max_input_tokens", 1.5), ("max_output_tokens", float("nan")),
    ("max_output_tokens", 0), ("temperature", False), ("semantic_retries", False),
])
def test_reasoner_config_rejects_ambiguous_accounting(field, bad):
    config = {"provider": "fixture", "model": "fixture", field: bad}
    with pytest.raises(ValueError):
        ReasonerConfig(**config)


@pytest.mark.parametrize("field,bad", [
    ("text", None), ("input_tokens", True), ("input_tokens", 1.5),
    ("output_tokens", float("nan")), ("output_tokens", -1),
])
def test_reasoner_response_rejects_invalid_text_or_usage(field, bad):
    response = {"text": "{}", "input_tokens": 1, "output_tokens": 1, field: bad}
    with pytest.raises(ValueError):
        ReasonerResponse(**response)


@pytest.mark.parametrize("bad", [True, 1.5, float("nan"), -1])
def test_invalid_preflight_token_count_cannot_invoke_provider(bad):
    gw = gateway(["{}"])
    gw.reasoner.count_tokens = lambda messages: bad
    with pytest.raises(ValueError, match="Preflight token count"):
        gw.call(episode_id="qualification", event_index=1, messages=[{"role": "user", "content": "public"}])
    assert gw.reasoner.calls == 0 and gw.logs == []
