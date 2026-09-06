"""Cross-component qualification with diagnostic answers, never model results."""
from cope_benchmark.repeated_v2.canonical import canonical_sha256, to_primitive
from cope_benchmark.repeated_v2.compiler import compile_directive, compile_ledger
from cope_benchmark.repeated_v2.enums import MethodName
from cope_benchmark.repeated_v2.oracle_fixtures import (build_oracle_fixture_chain,
    directive_fixture, initial_fixture)
from cope_benchmark.repeated_v2.parsers import parse_proposal
from cope_benchmark.repeated_v2.patch_contract import SUMMARY_VERSION
from cope_benchmark.repeated_v2.planner_backend import ControlledMechanismBackend


def test_eight_event_fixture_chain_and_every_generative_parser():
    chain = build_oracle_fixture_chain()
    assert len(chain) == 8
    assert canonical_sha256(chain) == canonical_sha256(build_oracle_fixture_chain())
    for cell in chain:
        for method, key in ((MethodName.COPE_TYPED_EDIT, "typed"),
                            (MethodName.GENERIC_PERSISTENT_EDIT, "generic"),
                            (MethodName.FULL_STATE_REGENERATION, "full_state"),
                            (MethodName.FULL_HISTORY_REPLAN, "directive"),
                            (MethodName.RAG_REPLAN, "directive"),
                            (MethodName.SKILL_LOCAL_REPLAN, "directive")):
            assert parse_proposal(method, cell[key]) == cell[key]
        parse_proposal(MethodName.SUMMARY_MEMORY_REPLAN, {"schema_version": SUMMARY_VERSION,
            "summary": "Current requests and preserved progress.", "planning_directive": cell["directive"]})
    before, context = initial_fixture()
    final = chain[-1]["after"]
    old = {slot.occurrence_id: slot for slot in before.slots}["goal:plate:rack@1"]
    assert old in final.slots  # unmentioned completed commitment survives byte-for-byte
    problem = compile_ledger(ledger=final, context=context, source_method=MethodName.COPE_TYPED_EDIT)
    assert "goal:mug:shelf@2" in problem.active_goal_occurrence_ids
    assert "goal:mug:shelf@1" not in problem.active_goal_occurrence_ids
    assert "goal:mug:cabinet@1" not in problem.active_goal_occurrence_ids
    assert problem.forbidden_regressions == ("plate_done",)
    trace = ControlledMechanismBackend().execute(problem=problem, context=context)
    assert trace.result_kind == "controlled_mechanism"
    assert "goal:mug:shelf@1" not in trace.executed_occurrence_ids
    assert "goal:mug:shelf@2" in trace.executed_occurrence_ids


def test_omitted_directive_goal_and_progress_are_not_repaired():
    ledger, context = initial_fixture()
    directive = directive_fixture(ledger, context)
    directive["remaining_goals"] = []
    directive["active_goal_occurrence_ids"] = []
    directive["progress_certificates"] = []
    directive["forbidden_regressions"] = []
    problem = compile_directive(directive=directive, context=context,
        source_method=MethodName.FULL_HISTORY_REPLAN, source_revision=1)
    assert not problem.remaining_goals and not problem.active_goal_occurrence_ids
    assert not problem.progress_certificates and not problem.forbidden_regressions
    trace = ControlledMechanismBackend().execute(problem=problem, context=context)
    assert not trace.executed_occurrence_ids


def test_regeneration_explicit_empty_fields_override_context_defaults():
    ledger, context = initial_fixture()
    problem = compile_ledger(ledger=ledger, context=context,
        source_method=MethodName.FULL_STATE_REGENERATION,
        initial_facts=[], progress_certificates=[], continuation_assumptions={})
    assert not problem.progress_certificates and not problem.forbidden_regressions
    assert not problem.continuation_assumptions


def test_planning_occurrence_error_is_preserved_for_scoring():
    ledger, context = initial_fixture()
    directive = directive_fixture(ledger, context)
    directive["active_goal_occurrence_ids"] = ["wrong@9"]
    directive["remaining_goals"] = [{"occurrence_id": "wrong@9", "predicate": "inside",
        "arguments": ["mug", "shelf"]}]
    problem = compile_directive(directive=directive, context=context,
        source_method=MethodName.FULL_HISTORY_REPLAN, source_revision=1)
    assert problem.remaining_goals[0]["occurrence_id"] == "wrong@9"
    trace = ControlledMechanismBackend().execute(problem=problem, context=context)
    assert "goal:mug:shelf@1" not in trace.executed_occurrence_ids


def test_no_provider_all_nine_adapter_smoke():
    from cope_benchmark.repeated_v2.smoke import run_oracle_fixture_smoke
    result = run_oracle_fixture_smoke()
    assert result["status"] == "PASS"
    assert result["external_provider_calls"] == result["vla_calls"] == 0
    assert result["fixture_reasoner_calls"] == 56
    assert result["accepted_event_cells"] == 72
    assert len(result["exact_prompt_logs"]) == 56
    assert len({(r["method"], r["event_index"]) for r in result["rows"]}) == 72
    assert all(r["execution_status"] == "succeeded" for r in result["rows"])


def test_shipped_output_schemas_validate_oracle_fixtures():
    import json
    from pathlib import Path
    from jsonschema import Draft202012Validator
    from cope_benchmark.repeated_v2.generic_contract import GENERIC_TRANSACTION_SCHEMA
    from cope_benchmark.repeated_v2.patch_contract import (
        COPE_PATCH_SCHEMA, FULL_STATE_SCHEMA, PLANNING_DIRECTIVE_SCHEMA, SUMMARY_SCHEMA,
        schema_document)
    root = Path(__file__).resolve().parents[2] / 'schemas' / 'repeated_v2'
    contracts = [('cope_patch', COPE_PATCH_SCHEMA, 'typed'),
                 ('generic_transaction', GENERIC_TRANSACTION_SCHEMA, 'generic'),
                 ('full_state', FULL_STATE_SCHEMA, 'full_state'),
                 ('planning_directive', PLANNING_DIRECTIVE_SCHEMA, 'directive'),
                 ('summary_memory', SUMMARY_SCHEMA, 'summary')]
    chain = build_oracle_fixture_chain()
    for name, source, key in contracts:
        shipped = json.loads((root / (name + '.schema.json')).read_text())
        assert shipped == schema_document(source)
        Draft202012Validator.check_schema(shipped)
        for row in chain:
            value = row[key] if key != 'summary' else {'schema_version': SUMMARY_VERSION,
                'summary': 'Preserve public requests.', 'planning_directive': row['directive']}
            Draft202012Validator(shipped).validate(value)
