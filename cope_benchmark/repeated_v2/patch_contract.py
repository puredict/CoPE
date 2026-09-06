"""Public JSON contracts for the typed local transaction interface.

Occurrence IDs and retirement timestamps are owned by the deterministic kernel.
Checks record evidence; only the six mutation operators change commitment slots.
"""

from copy import deepcopy

PATCH_VERSION = "cope-repeated-v2/patch-1"
FULL_STATE_VERSION = "cope-repeated-v2/full-state-1"
DIRECTIVE_VERSION = "cope-repeated-v2/directive-1"
SUMMARY_VERSION = "cope-repeated-v2/summary-1"
OPERATORS = ("INSERT", "SUSPEND", "OVERRIDE", "SET_PRIORITY", "EXPIRE", "RESTORE")


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties if required is None else required),
            "additionalProperties": False}


STRING = {"type": "string", "minLength": 1}
STRINGS = {"type": "array", "items": STRING, "uniqueItems": True}
NONNEGATIVE = {"type": "integer", "minimum": 0}
CONFIDENCE = {"type": "number", "minimum": 0, "maximum": 1}
MAPPING = {"type": "object"}
MAPPINGS = {"type": "array", "items": MAPPING}
LIFECYCLE = {"enum": ["active", "suspended", "overridden", "expired"]}
GROUNDING = {"enum": ["valid", "degraded", "unknown", "invalid"]}
ROLE = {"enum": ["achievement_goal", "maintenance_invariant", "safety_requirement",
                 "user_preference", "grounding_binding"]}
AUTHORITIES = {"enum": ["planner", "perception", "task", "user", "safety", "system"]}
SLOT_PROPERTIES = {
    "family_key": STRING, "role": ROLE, "predicate": STRING,
    "arguments": {"type": "array", "items": STRING}, "lifecycle": LIFECYCLE,
    "grounding_validity": GROUNDING, "priority": {"type": "number", "minimum": 0},
    "hardness": {"enum": ["hard", "soft"]}, "source": AUTHORITIES, "authority": AUTHORITIES,
    "restore_guard": MAPPING, "dependency_ids": STRINGS, "provenance": MAPPING,
    "evidence_ids": STRINGS,
}
NEW_SLOT_SCHEMA = obj({**SLOT_PROPERTIES, "lifecycle": {"const": "active"}})
SLOT_SCHEMA = obj({**SLOT_PROPERTIES, "occurrence_id": STRING,
                   "created_event_id": {"type": ["string", "null"]},
                   "retired_event_id": {"type": ["string", "null"]}})
RELATION_SCHEMA = obj({"source_id": STRING, "relation": {"enum": [
    "depends_on", "precedes", "overrides", "conflicts_with", "same_family", "derived_from"
]}, "target_id": STRING})
RELATIONS = {"type": "array", "items": RELATION_SCHEMA, "uniqueItems": True}
CHECK_PROPERTIES = {"kind": {"const": "REVALIDATE"}, "check_id": STRING,
                    "occurrence_id": STRING, "evidence_ids": STRINGS,
                    "guard": MAPPING, "result": {"type": "boolean"}}
CHECK_SCHEMA = obj(CHECK_PROPERTIES)
BASE_PROPERTIES = {
    "schema_version": {"const": PATCH_VERSION}, "episode_id": STRING,
    "event_index": {"type": "integer", "minimum": 1}, "base_revision": NONNEGATIVE,
    "affected_scope": STRINGS, "protected_ids": STRINGS,
    "protected_projection_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "evidence_ids": STRINGS,
}


def _operation(name, fields, optional=()):
    properties = {"op": {"const": name}, **fields,
                  "relation_additions": RELATIONS, "relation_removals": RELATIONS}
    required = [key for key in properties if key not in {*optional, "relation_additions", "relation_removals"}]
    return obj(properties, required)


OPERATION_SCHEMA = {"oneOf": [
    _operation("INSERT", {"request_id": STRING, "slot": NEW_SLOT_SCHEMA}),
    _operation("SUSPEND", {"occurrence_id": STRING, "restore_guard": MAPPING,
                           "grounding_validity": GROUNDING}, ("restore_guard", "grounding_validity")),
    _operation("OVERRIDE", {"occurrence_id": STRING, "request_id": STRING, "slot": NEW_SLOT_SCHEMA}),
    _operation("SET_PRIORITY", {"occurrence_id": STRING, "priority": {"type": "number", "minimum": 0}}),
    _operation("EXPIRE", {"occurrence_id": STRING}),
    _operation("RESTORE", {"occurrence_id": STRING, "check_id": STRING,
                           "grounding_validity": GROUNDING}, ("grounding_validity",)),
]}
COPE_PATCH_SCHEMA = obj({**BASE_PROPERTIES,
    "checks": {"type": "array", "items": CHECK_SCHEMA},
    "operations": {"type": "array", "items": OPERATION_SCHEMA}, "confidence": CONFIDENCE})
FULL_STATE_SCHEMA = obj({
    "schema_version": {"const": FULL_STATE_VERSION}, "base_revision": NONNEGATIVE,
    "slots": {"type": "array", "items": SLOT_SCHEMA}, "relations": RELATIONS,
    "semantic_history": MAPPINGS,
    "initial_facts": MAPPINGS, "progress_certificates": MAPPINGS,
    "continuation_assumptions": MAPPING,
})
PLANNING_DIRECTIVE_SCHEMA = obj({
    "schema_version": {"const": DIRECTIVE_VERSION}, "initial_facts": MAPPINGS,
    "active_goal_occurrence_ids": STRINGS,
    "remaining_goals": {"type": "array", "items": {"type": "object",
        "required": ["occurrence_id"], "properties": {"occurrence_id": STRING}}},
    "hard_constraints": MAPPINGS, "soft_preferences": MAPPINGS,
    "forbidden_regressions": STRINGS, "grounding_bindings": MAPPINGS,
    "restore_eligibility": MAPPINGS, "progress_certificates": MAPPINGS,
    "continuation_assumptions": MAPPING,
    "ordered_macro_plan": {"type": "array", "items": {"type": ["string", "object"]}},
    "current_subgoal": {"type": ["string", "object", "null"]},
    "current_target_occurrence_hypothesis": {"type": ["string", "null"]},
}, required=["schema_version", "initial_facts", "active_goal_occurrence_ids", "remaining_goals",
             "hard_constraints", "soft_preferences", "forbidden_regressions", "grounding_bindings",
             "restore_eligibility", "progress_certificates", "continuation_assumptions", "ordered_macro_plan"])
SUMMARY_SCHEMA = obj({"schema_version": {"const": SUMMARY_VERSION},
                      "summary": {"type": "string"}, "planning_directive": PLANNING_DIRECTIVE_SCHEMA})


def schema_document(schema):
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", **deepcopy(schema)}
