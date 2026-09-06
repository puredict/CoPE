"""Actual phase-2 public prompts from offline fixtures, never formal evidence."""
import copy
import json

import pytest

from cope_benchmark.repeated_v2.adapters import create_adapter
from cope_benchmark.repeated_v2.enums import MethodName
from cope_benchmark.repeated_v2.oracle_fixtures import build_oracle_fixture_chain, initial_fixture
from cope_benchmark.repeated_v2.parity_analysis import audit_prompt_parity
from cope_benchmark.repeated_v2.provider import FixtureReasoner, ReasonerConfig, ReasonerGateway
from tests.repeated_v2.test_phase2_adapters import fixture_response


def data():
    row=build_oracle_fixture_chain()[0]
    records,intents=[],{}
    for method in list(MethodName)[:7]:
        ledger,context=initial_fixture()
        gateway=ReasonerGateway(FixtureReasoner([fixture_response(method,row)]),
            ReasonerConfig(provider="unit-fixture",model="unit-model",max_input_tokens=200000,max_output_tokens=200000))
        adapter=create_adapter(method,gateway=gateway)
        adapter.start_episode(task={"episode_id":"unit","instruction":"Put the mug on the shelf."},ledger=ledger,context=context)
        adapter.on_event(evidence=row["step"].event,public_history=[],context=context,evidence_records=row["step"].evidence)
        for k in (0,1):
            records.append({"protocol":"controlled","master_episode_id":"unit","method":method.value,
                "event_index":k,"status":"COMPLETED","high_level_calls":k})
        log=gateway.logs[0]
        intents[("controlled","unit",method.value,1)]={"request":{
            "messages":log.messages,"config":json.loads(log.config_json)}}
    return [{"status":"VALID","results":records,"intents":intents}]


def audit(values):
    return audit_prompt_parity(values,identities={"reasoner":{"provider_id":"unit-fixture","model_id":"unit-model"}},
        config={"reasoner":{"max_input_tokens_evidence_matched":200000,"max_output_tokens":200000}},
        condition="evidence_matched")


def test_real_phase2_templates_and_information_scopes_pass():
    values=data()
    original=copy.deepcopy(values)
    result=audit(values)
    assert result["evidence_parity"] and result["reasoner_call_parity"]
    assert result["checked_calls"]==7
    assert values==original


@pytest.mark.parametrize("mutation",["extra_call","hidden","missing_fact","contract","model","seed","condition","missing_call"])
def test_actual_input_or_budget_drift_rejected(mutation):
    values=data()
    request=next(iter(values[0]["intents"].values()))["request"]
    if mutation=="extra_call": values[0]["results"][1]["high_level_calls"]=2
    if mutation=="missing_call": values[0]["intents"].pop(next(iter(values[0]["intents"])))
    if mutation=="hidden":
        common=json.loads(request["messages"][1]["content"])
        common["hidden_canonical_state"]={"correct_goal":"secret"}
        request["messages"][1]["content"]=json.dumps(common)
    if mutation=="missing_fact":
        memory=json.loads(request["messages"][2]["content"])
        memory["semantic_facts"].pop("relevant_trace")
        request["messages"][2]["content"]=json.dumps(memory)
    if mutation=="contract": request["messages"][-1]["content"]+=" Additional unregistered instruction."
    if mutation=="model": request["config"]["model"]="different-model"
    if mutation=="seed": request["config"]["seed"]=999
    if mutation=="condition": request["config"]["setting"]="token_matched"
    result=audit(values)
    assert not result["evidence_parity"] and result["errors"]


def test_precall_adaptation_failure_retains_zero_calls():
    values=data()
    values[0]["intents"].pop(next(iter(values[0]["intents"])))
    values[0]["results"][1].update(status="METHOD_ADAPTATION_FAILURE",high_level_calls=0)
    assert audit(values)["reasoner_call_parity"]
