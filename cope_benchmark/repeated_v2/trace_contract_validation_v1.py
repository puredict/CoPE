"""Validation and recursive leakage checks for the frozen trace contract."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .canonical import canonical_json, strict_loads, to_primitive
from .enums import EventFamily
from .trace_contract_v1 import (
    AcceptedPatchRecordV1,
    RuntimeTraceBundleV1,
    SealedOutcomeV1,
    TRACE_CONTRACT_VERSION,
    patch_record_json_schema,
    trace_json_schema,
    TRACE_RECORD_TYPES,
)


class TraceContractError(ValueError):
    status = "INVALID_EXP1_TRACE_CONTRACT"


class TraceLeakageError(TraceContractError):
    status = "INVALID_TRACE_HIDDEN_STATE_LEAKAGE"


_FORBIDDEN_KEYS = frozenset({
    "canonicaleventcause", "canonicaleventfamily", "canonicaleffect",
    "canonicalplanningproblem", "canonicalresponsibilityroute", "canonicalstate",
    "correctoccurrence", "correctoperator", "correctpatch", "correctresponsibilityroute",
    "expectedcopeoperator", "expectedeventfamily", "expectedlifecyletransition",
    "expectedlifecycletransition", "expectedoccurrence", "expectedoperator",
    "expectedpatch", "expectedtarget", "goldoccurrence", "goldoccurrencetarget",
    "groundtruth", "hiddencanonicaleffect", "hiddencause", "hiddeneventcause",
    "hiddeneventfamily", "hiddenstate", "hiddentruth", "methodresultlabel",
    "mujocostate", "objectstate", "oraclecorrectionpacket", "privilegedstate",
    "responsibilityroute", "simstate", "simulatorstate", "simulatortruth",
    "trueeventcause", "trueeventfamily", "truefamily",
})
_FAMILY_LABELS = frozenset(family.value for family in EventFamily)


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def leakage_paths(value: Any) -> tuple[str, ...]:
    """Return every recursively detected non-public field/value path.

    Patch operators are method outputs and are deliberately permitted.  The
    scanner blocks answer-bearing labels, canonical state, and simulator truth.
    """
    violations: list[str] = []

    def walk(item: Any, path: str) -> None:
        if isinstance(item, SealedOutcomeV1):
            violations.append(path + ":sealed_outcome_object")
            return
        if isinstance(item, Mapping):
            for name, nested in item.items():
                if not isinstance(name, str):
                    violations.append(path + ":non_string_key")
                    continue
                if _key(name) in _FORBIDDEN_KEYS:
                    violations.append(f"{path}.{name}:forbidden_key")
                walk(nested, f"{path}.{name}")
            return
        if isinstance(item, (list, tuple)):
            for index, nested in enumerate(item):
                walk(nested, f"{path}[{index}]")
            return
        if isinstance(item, str):
            if any(label in item for label in _FAMILY_LABELS):
                violations.append(path + ":canonical_event_family")
            stripped = item.lstrip()
            if stripped.startswith(("{", "[")):
                try:
                    decoded = strict_loads(item)
                except (ValueError, UnicodeError):
                    return
                walk(decoded, path + "<serialized_json>")

    try:
        primitive = to_primitive(value)
    except (ValueError, UnicodeError) as exc:
        raise TraceContractError("trace is not canonical JSON data") from exc
    walk(value, "$")
    if primitive is not value:
        walk(primitive, "$<primitive>")
    return tuple(dict.fromkeys(violations))


def assert_no_hidden_leakage(value: Any) -> None:
    violations = leakage_paths(value)
    if violations:
        raise TraceLeakageError("hidden trace fields: " + ", ".join(violations))


def _validate_schema(instance: Any, schema: Mapping[str, Any]) -> None:
    try:
        import jsonschema
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(instance)
    except ImportError as exc:
        raise TraceContractError("jsonschema is required for trace validation") from exc
    except jsonschema.ValidationError as exc:
        raise TraceContractError("trace JSON schema validation failed") from exc


def validate_public_bundle(value: RuntimeTraceBundleV1 | Mapping[str, Any]) -> RuntimeTraceBundleV1:
    try:
        bundle = value if type(value) is RuntimeTraceBundleV1 else RuntimeTraceBundleV1.from_dict(value)
    except (TypeError, ValueError) as exc:
        raise TraceContractError("invalid runtime trace bundle") from exc
    _validate_schema(bundle.to_dict(), trace_json_schema(RuntimeTraceBundleV1))
    assert_no_hidden_leakage(bundle)
    return bundle


def validate_sealed_outcome(value: SealedOutcomeV1 | Mapping[str, Any]) -> SealedOutcomeV1:
    try:
        outcome = value if type(value) is SealedOutcomeV1 else SealedOutcomeV1.from_dict(value)
    except (TypeError, ValueError) as exc:
        raise TraceContractError("invalid sealed outcome") from exc
    _validate_schema(outcome.to_dict(), trace_json_schema(SealedOutcomeV1))
    return outcome


def validate_schema_directory(schema_dir: str | Path) -> dict[str, str]:
    """Verify checked-in schemas equal the executable contract exactly."""
    import hashlib
    try:
        import jsonschema
    except ImportError as exc:
        raise TraceContractError("jsonschema is required for trace validation") from exc
    root = Path(schema_dir)
    expected = {name: trace_json_schema(record_type) for name, record_type in TRACE_RECORD_TYPES.items()}
    expected["patch_record"] = patch_record_json_schema()
    hashes: dict[str, str] = {}
    for name, generated in expected.items():
        path = root / f"{name}.schema.json"
        try:
            checked = strict_loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise TraceContractError(f"cannot read schema {path}") from exc
        if checked != generated:
            raise TraceContractError(f"checked-in schema drift: {path.name}")
        jsonschema.Draft202012Validator.check_schema(generated)
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def load_canonical_record(path: str | Path) -> Any:
    raw = Path(path).read_text(encoding="utf-8")
    value = strict_loads(raw)
    if raw != canonical_json(value) + "\n":
        raise TraceContractError("trace record is not canonical JSON with one terminal newline")
    return value


__all__ = [
    "TraceContractError", "TraceLeakageError", "leakage_paths",
    "assert_no_hidden_leakage", "validate_public_bundle", "validate_sealed_outcome",
    "validate_schema_directory", "load_canonical_record",
]
