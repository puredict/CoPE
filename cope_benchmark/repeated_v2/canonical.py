"""Versioned canonical UTF-8 JSON, strict loading, and immutable JSON snapshots.

Objects sort by Unicode key, arrays retain order, finite integral floats and
negative zero normalize to integers. No implicit stringification or NaN is
allowed. This is the v2 normalization, not a claim of RFC 8785 compatibility.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any


def to_primitive(value: Any) -> Any:
    return _primitive(value, set(), "$")


def _primitive(value: Any, active: set[int], path: str) -> Any:
    if isinstance(value, Enum):
        return _primitive(value.value, active, path)
    if value is None or type(value) in (str, bool, int):
        if isinstance(value, str):
            value.encode("utf-8")  # Unpaired surrogates are not canonical UTF-8.
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
            return {f.name: _primitive(getattr(value, f.name), active, f"{path}.{f.name}") for f in fields(value)}
        if isinstance(value, Mapping):
            if any(type(k) is not str for k in value):
                raise ValueError(f"JSON object keys must be strings at {path}")
            for key in value:
                key.encode("utf-8")
            return {k: _primitive(v, active, f"{path}.{k}") for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_primitive(v, active, f"{path}[{i}]") for i, v in enumerate(value)]
        raise ValueError(f"unsupported JSON value {type(value).__name__} at {path}")
    finally:
        active.remove(id(value))


def canonical_json(value: Any) -> str:
    return json.dumps(to_primitive(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def freeze_json(value: Any) -> Any:
    def freeze(item: Any) -> Any:
        if isinstance(item, dict):
            return MappingProxyType({k: freeze(v) for k, v in item.items()})
        if isinstance(item, list):
            return tuple(freeze(v) for v in item)
        return item
    return freeze(to_primitive(value))


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

    return to_primitive(json.loads(value, object_pairs_hook=unique, parse_constant=reject_constant))
