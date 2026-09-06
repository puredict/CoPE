"""Audit actual journaled public prompts and event-call budgets, without calls.

Independent method trajectories may have different accepted memories and sensory
values. Equality of their evolving states is not a fairness requirement. This
audit checks the frozen information interfaces, exact templates, public-input
allowlists, matched backbone/settings, and actual one-call journal accounting.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Mapping, Sequence


MEMORY_KEYS = {
    "cope_typed_edit": {"semantic_facts", "protection_options"},
    "generic_persistent_edit": {"semantic_facts", "protection_options"},
    "full_state_regeneration": {"semantic_facts"},
    "full_history_replan": {"public_history", "execution_context"},
    "rag_replan": {"retrieved_public_history", "execution_context"},
    "summary_memory_replan": {"summary", "recent_public_history", "execution_context"},
    "skill_local_replan": {"active_skill", "local_preconditions", "local_postconditions",
        "recent_observation_action_window", "current_subgoal", "public_event_evidence", "current_observations"},
}
FACT_KEYS = {"ledger","execution_context","accepted_planning_fields","public_evidence","relevant_trace"}


def _strict_raw_json(text: str) -> Any:
    # Prompt replay preserves 1.0 versus 1 exactly; the semantic canonical loader
    # intentionally normalizes those and is unsuitable for byte-exact templates.
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:
                raise ValueError("duplicate JSON key in actual prompt")
            result[key]=value
        return result
    return json.loads(text,object_pairs_hook=pairs,
        parse_constant=lambda value:(_ for _ in ()).throw(ValueError("nonfinite actual prompt")))


def audit_prompt_parity(journal_audits: Sequence[Mapping[str, Any]], *, identities: Mapping[str,Any],
                        config: Mapping[str,Any], condition: str) -> dict[str,Any]:
    from .prompts import build_messages, scan_public_input
    from .provider import ReasonerConfig
    errors=[]
    configurations=defaultdict(set)
    checked=0
    actual_calls=0
    for audit in journal_audits:
        if audit.get("status")!="VALID":
            raise ValueError("prompt audit requires valid immutable journal")
        intents=audit["intents"]
        for row in audit["results"]:
            method,k=row["method"],row["event_index"]
            key=(row["protocol"],row["master_episode_id"],method,k)
            expected=int(k>0 and "UNREACHED" not in row["status"] and method in MEMORY_KEYS)
            allowed={0,1} if k>0 and method in MEMORY_KEYS and row["status"]=="METHOD_ADAPTATION_FAILURE" else {expected}
            if row["high_level_calls"] not in allowed or int(key in intents)!=row["high_level_calls"]:
                errors.append(f"{key}: event reasoner call budget differs")
        for key,intent in intents.items():
            actual_calls+=1
            method=key[2]
            if method not in MEMORY_KEYS:
                errors.append(f"{key}: unexpected generative call")
                continue
            try:
                request=intent["request"]
                settings=request["config"]
                ReasonerConfig(**settings)
                if settings["provider"]!=identities["reasoner"]["provider_id"] or settings["model"]!=identities["reasoner"]["model_id"]:
                    raise ValueError("reasoner identity mismatch")
                if settings["setting"]!=condition or settings["max_input_tokens"]!=config["reasoner"]["max_input_tokens_"+condition] or settings["max_output_tokens"]!=config["reasoner"]["max_output_tokens"]:
                    raise ValueError("information condition or token budget mismatch")
                configurations[(key[0],key[1])].add(json.dumps(settings,sort_keys=True))
                messages=request["messages"]
                scan_public_input(messages,generic=method=="generic_persistent_edit")
                if len(messages)!=4:
                    raise ValueError("unexpected message structure")
                common=_strict_raw_json(messages[1]["content"])
                memory=_strict_raw_json(messages[2]["content"])
                if set(common)!={"task","event_evidence"} or set(memory)!=MEMORY_KEYS[method]:
                    raise ValueError("unregistered public-input fields")
                if "semantic_facts" in memory and set(memory["semantic_facts"])!=FACT_KEYS:
                    raise ValueError("persistent semantic information omitted/expanded")
                expected_messages=build_messages(method=method,task=common["task"],
                    evidence=common["event_evidence"],memory=memory)
                if expected_messages!=messages:
                    raise ValueError("actual prompts differ from frozen interface contract")
                checked+=1
            except (ValueError,TypeError,KeyError,IndexError) as exc:
                errors.append(f"{key}: {exc}")
    for key,settings in configurations.items():
        if len(settings)!=1:
            errors.append(f"{key}: method backbone/generation settings differ")
    return {"evidence_parity":not errors,"reasoner_call_parity":not errors,
            "errors":errors,"checked_calls":checked,"actual_calls":actual_calls,
            "scope":"actual public interfaces, leakage scan, backbone and event call budget; evolving state values may differ"}
