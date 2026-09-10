"""Recursive structural separation of public trace data and sealed outcomes."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .canonical import strict_loads, to_primitive


class LeakageError(ValueError):
    pass


_FORBIDDEN_KEYS = frozenset(
    {
        "affectedoccurrenceids",
        "canonicaleffect",
        "canonicalstate",
        "correctoperation",
        "correctpatch",
        "expectedoperator",
        "expectedoperators",
        "expectedoccurrenceid",
        "expectedtarget",
        "expectedtargetoccurrence",
        "faultlabel",
        "faultlabels",
        "groundtruth",
        "hiddencanonicaleffect",
        "hiddencause",
        "hiddeneventcause",
        "hiddenoutcome",
        "hiddentruth",
        "hiddentruthsha256",
        "oraclelabel",
        "oraclelabels",
        "responsibilitylabel",
        "responsiblemodule",
        "responsiblemodules",
        "sealedcause",
        "sealedevaluation",
        "sealedoutcome",
        "simulatorintervention",
        "truefamily",
    }
)
_SERIALIZED_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_ -]*(?=[\"':=])")


def normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def assert_public_safe(value: Any) -> None:
    """Reject sealed keys even when nested or embedded as serialized JSON."""
    primitive = to_primitive(value)

    def walk(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if normalized_key(key) in _FORBIDDEN_KEYS:
                    raise LeakageError(f"sealed field at {path}.{key}")
                walk(nested, f"{path}.{key}")
        elif isinstance(item, (list, tuple)):
            for index, nested in enumerate(item):
                walk(nested, f"{path}[{index}]")
        elif isinstance(item, str):
            normalized_text = normalized_key(item)
            if any(token in normalized_text for token in _FORBIDDEN_KEYS):
                raise LeakageError(f"sealed token at {path}")
            for token in _SERIALIZED_KEY.findall(item):
                if normalized_key(token) in _FORBIDDEN_KEYS:
                    raise LeakageError(f"serialized sealed field at {path}")
            if item.lstrip().startswith(("{", "[")):
                try:
                    decoded = strict_loads(item)
                except (ValueError, TypeError):
                    return
                walk(decoded, path + "<json>")

    walk(primitive, "$")
