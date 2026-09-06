"""Strict, dependency-free proposal parsing. No extraction, coercion or repair."""

import json
import math
import re
from collections.abc import Mapping
from enum import Enum

from .canonical import to_primitive
from .generic_contract import GENERIC_TRANSACTION_SCHEMA
from .patch_contract import (COPE_PATCH_SCHEMA, FULL_STATE_SCHEMA, PLANNING_DIRECTIVE_SCHEMA,
                             SLOT_PROPERTIES, SUMMARY_SCHEMA)


class ProposalError(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProposalError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _finite(value, path="$"):
    if isinstance(value, float) and not math.isfinite(value):
        raise ProposalError(f"non-finite number at {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProposalError(f"non-string key at {path}")
            _finite(item, f"{path}.{key}")
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _finite(item, f"{path}[{index}]")
    elif value is not None and not isinstance(value, (str, bool, int, float)):
        raise ProposalError(f"non-JSON value at {path}")


def _matches_type(value, kind):
    return {"object": lambda: isinstance(value, dict), "array": lambda: isinstance(value, list),
            "string": lambda: isinstance(value, str), "integer": lambda: type(value) is int,
            "number": lambda: type(value) in (int, float), "boolean": lambda: type(value) is bool,
            "null": lambda: value is None}[kind]()


def validate_schema(value, schema, path="$"):
    if "oneOf" in schema:
        matches = 0
        for choice in schema["oneOf"]:
            try:
                validate_schema(value, choice, path)
                matches += 1
            except ProposalError:
                pass
        if matches != 1:
            raise ProposalError(f"{path}: expected exactly one valid interface variant")
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        raise ProposalError(f"{path}: wrong constant")
    if "enum" in schema and not any(type(value) is type(item) and value == item for item in schema["enum"]):
        raise ProposalError(f"{path}: invalid enumeration")
    if "type" in schema:
        kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_matches_type(value, kind) for kind in kinds):
            raise ProposalError(f"{path}: wrong type; expected {kinds}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        missing = set(schema.get("required", ())) - value.keys()
        if missing:
            raise ProposalError(f"{path}: missing required fields {sorted(missing)}")
        if schema.get("additionalProperties") is False and value.keys() - props.keys():
            raise ProposalError(f"{path}: unknown fields {sorted(value.keys() - props.keys())}")
        for key, item in value.items():
            if key in props:
                validate_schema(item, props[key], f"{path}.{key}")
    elif isinstance(value, list):
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            raise ProposalError(f"{path}: duplicate items")
        for index, item in enumerate(value):
            validate_schema(item, schema.get("items", {}), f"{path}[{index}]")
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or (schema.get("minLength") and not value.strip()):
            raise ProposalError(f"{path}: empty string")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise ProposalError(f"{path}: pattern mismatch")
    elif type(value) in (int, float):
        if value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            raise ProposalError(f"{path}: out of range")


def _parse(raw, schema):
    if isinstance(raw, str):
        try:
            value = json.loads(raw, object_pairs_hook=_pairs,
                               parse_constant=lambda value: (_ for _ in ()).throw(ProposalError(f"invalid number {value}")))
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ProposalError(f"invalid JSON: {exc}") from exc
    elif isinstance(raw, Mapping):
        try:
            # Canonical serialization normalizes integral floats for hashing,
            # but interface parsing must not coerce a float into an integer.
            # Validate JSON/cycles first, then retain the supplied number types.
            to_primitive(raw)
            def copy_json(item):
                if isinstance(item, Enum):
                    return copy_json(item.value)
                if isinstance(item, Mapping):
                    return {key: copy_json(value) for key, value in item.items()}
                if isinstance(item, (tuple, list)):
                    return [copy_json(value) for value in item]
                return item
            value = copy_json(raw)
        except (ValueError, TypeError) as exc:
            raise ProposalError(str(exc)) from exc
    else:
        raise ProposalError("proposal must be a JSON object or exact JSON text")
    _finite(value)
    validate_schema(value, schema)
    return value


def _public_semantics(value):
    from .evidence import assert_public_safe
    from .prompts import scan_public_input
    try:
        assert_public_safe(value)
        # Carrier syntax is stripped by the typed parser before this boundary.
        # Scan keys as well as values so free-form objects and encoded JSON
        # cannot hide typed operator, condition, method, or path labels.
        scan_public_input(value, generic=True)
    except ValueError as exc:
        raise ProposalError(str(exc)) from exc


def parse_cope_proposal(raw):
    proposal = _parse(raw, COPE_PATCH_SCHEMA)
    # Typed syntax is allowed only in the explicit carrier, never hidden in a
    # semantic field such as provenance, guard or argument text.
    semantic = {key: value for key, value in proposal.items() if key not in {"operations", "checks"}}
    semantic["operations"] = [{key: value for key, value in operation.items() if key != "op"}
                               for operation in proposal["operations"]]
    semantic["checks"] = [{key: value for key, value in check.items() if key != "kind"}
                           for check in proposal["checks"]]
    _public_semantics(semantic)
    return proposal


def parse_generic_proposal(raw):
    proposal = _parse(raw, GENERIC_TRANSACTION_SCHEMA)
    _public_semantics(proposal)
    for write in proposal["writes"]:
        field = write["path"][1:]
        validate_schema(write["value"], SLOT_PROPERTIES[field], f"$.writes.{field}")
    return proposal


def parse_full_state(raw):
    proposal = _parse(raw, FULL_STATE_SCHEMA)
    _public_semantics(proposal)
    ids = [slot["occurrence_id"] for slot in proposal["slots"]]
    if len(ids) != len(set(ids)):
        raise ProposalError("duplicate occurrence ID")
    try:
        from .schema import CommitmentOccurrence, ProgressCertificate, RelationEdge
        for slot in proposal["slots"]:
            CommitmentOccurrence.from_dict(slot)
        for edge in proposal["relations"]:
            RelationEdge.from_dict(edge)
        for certificate in proposal["progress_certificates"]:
            ProgressCertificate.from_dict(certificate)
    except ValueError as exc:
        raise ProposalError(str(exc)) from exc
    return proposal


def parse_planning_directive(raw):
    proposal = _parse(raw, PLANNING_DIRECTIVE_SCHEMA)
    _public_semantics(proposal)
    try:
        from .schema import ProgressCertificate
        for certificate in proposal["progress_certificates"]:
            ProgressCertificate.from_dict(certificate)
    except ValueError as exc:
        raise ProposalError(str(exc)) from exc
    return proposal


def parse_proposal(method, raw):
    method = method.value if isinstance(method, Enum) else method
    if method in {"cope_typed_edit", "oracle_persistent_update"}:
        return parse_cope_proposal(raw)
    if method == "generic_persistent_edit":
        return parse_generic_proposal(raw)
    if method == "full_state_regeneration":
        return parse_full_state(raw)
    if method == "summary_memory_replan":
        proposal = _parse(raw, SUMMARY_SCHEMA)
        _public_semantics(proposal)
        parse_planning_directive(proposal["planning_directive"])
        return proposal
    if method in {"full_history_replan", "rag_replan", "skill_local_replan", "classical_execution_monitor"}:
        return parse_planning_directive(raw)
    raise ProposalError(f"unknown method: {method}")
