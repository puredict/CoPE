"""Frozen canonical JSON rules for the Experiment-1 trace contract."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

CANONICAL_SERIALIZATION_VERSION = "cope-canonical-json/v1"


def to_primitive(value: Any) -> Any:
    """Convert a supported value to a finite, acyclic JSON tree."""
    return _to_primitive(value, active=set(), path="$")


def _to_primitive(value: Any, *, active: set[int], path: str) -> Any:
    if isinstance(value, Enum):
        return _to_primitive(value.value, active=active, path=path)
    if value is None or type(value) in (str, bool, int):
        if isinstance(value, str):
            value.encode("utf-8")
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"non-finite number at {path}")
        return int(value) if value.is_integer() else value
    if id(value) in active:
        raise ValueError(f"cyclic value at {path}")
    active.add(id(value))
    try:
        if is_dataclass(value) and not isinstance(value, type):
            return {
                member.name: _to_primitive(
                    getattr(value, member.name), active=active, path=f"{path}.{member.name}"
                )
                for member in fields(value)
            }
        if isinstance(value, Mapping):
            if any(type(key) is not str for key in value):
                raise ValueError(f"non-string object key at {path}")
            return {
                key: _to_primitive(item, active=active, path=f"{path}.{key}")
                for key, item in value.items()
            }
        if isinstance(value, (tuple, list)):
            return [
                _to_primitive(item, active=active, path=f"{path}[{index}]")
                for index, item in enumerate(value)
            ]
        raise ValueError(f"unsupported JSON value {type(value).__name__} at {path}")
    finally:
        active.remove(id(value))


def canonical_json(value: Any) -> str:
    return json.dumps(
        to_primitive(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def strict_loads(value: str) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = item
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    return to_primitive(
        json.loads(value, object_pairs_hook=unique, parse_constant=reject_constant)
    )


def freeze_json(value: Any) -> Any:
    def freeze(item: Any) -> Any:
        if isinstance(item, dict):
            return MappingProxyType({key: freeze(nested) for key, nested in item.items()})
        if isinstance(item, list):
            return tuple(freeze(nested) for nested in item)
        return item

    return freeze(to_primitive(value))
