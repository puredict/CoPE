"""Fail-closed public projection and recursive structural leakage checks."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .canonical import freeze_json, strict_loads, to_primitive
from .enums import EventFamily


class EventLeakageError(ValueError):
    pass


_FORBIDDEN_KEYS = frozenset({
    "hiddencanonicaleffect", "hiddencause", "hiddeneventcause", "hiddentruth",
    "truefamily", "canonicaleffect", "canonicalstate", "expectedoperator",
    "expectedoperators", "expectedtarget", "expectedtargetoccurrence",
    "expectedtargetoccurrenceid", "expectedoccurrenceid", "affectedoccurrenceids",
    "faultlabel", "faultlabels", "groundtruth", "correctpatch", "correctoperation",
    "responsibilitylabel", "simulatorintervention", "sealedevaluation",
    "hiddentruthsha256", "hiddenapplication",
})
_FAMILY_LABELS = frozenset(f.value for f in EventFamily)
_OPERATOR_TOKEN = re.compile(r"\b(?:INSERT|SUSPEND|OVERRIDE|SET_PRIORITY|EXPIRE|RESTORE|REVALIDATE|DEMOTED)\b")


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def assert_public_safe(value: Any) -> None:
    """Reject hidden types, keys, serialized records, and explicit oracle labels.

    This is a structural guard, not a semantic detector for arbitrary prose.
    Public records must still originate in the shared detector/user substrate.
    """
    from .schema import HiddenCanonicalEffect, SealedEvaluation
    if isinstance(value, (HiddenCanonicalEffect, SealedEvaluation)):
        raise EventLeakageError("hidden record cannot cross the public boundary")

    def walk(item: Any, path: str) -> None:
        if isinstance(item, (HiddenCanonicalEffect, SealedEvaluation)):
            raise EventLeakageError(f"hidden record at {path}")
        if isinstance(item, Mapping):
            for name, nested in item.items():
                if _key(name) in _FORBIDDEN_KEYS:
                    raise EventLeakageError(f"hidden field at {path}.{name}")
                walk(nested, f"{path}.{name}")
        elif isinstance(item, (list, tuple)):
            for i, nested in enumerate(item):
                walk(nested, f"{path}[{i}]")
        elif isinstance(item, str):
            if _OPERATOR_TOKEN.search(item) or any(label in item for label in _FAMILY_LABELS):
                raise EventLeakageError(f"operator or hidden family label at {path}")
            if any(_key(token) in _FORBIDDEN_KEYS for token in re.findall(r"[a-zA-Z][a-zA-Z_ -]*(?=[\"':=])", item)):
                raise EventLeakageError(f"serialized hidden field at {path}")
            if item.lstrip().startswith(("{", "[")):
                try:
                    parsed = strict_loads(item)
                except ValueError:
                    return
                walk(parsed, path + "<json>")

    # Validate JSON/cycles before traversing the original tagged records.
    primitive = to_primitive(value)
    # Retain the original objects so hidden tags are also checked recursively.
    if isinstance(value, (Mapping, list, tuple)):
        walk(value, "$")
    walk(primitive, "$")


def public_event_payload(payload: Any) -> Mapping[str, Any]:
    """Accept only the allowlisted public record, never a merged event dict."""
    from .schema import EventEvidence, PublicEventPayload
    if type(payload) not in (PublicEventPayload, EventEvidence):
        raise EventLeakageError("public projection requires an explicit PublicEventPayload")
    assert_public_safe(payload)
    return freeze_json(payload.to_dict())


def validate_evidence_references(payload: Any, records: Sequence[Any]) -> None:
    from .schema import EvidenceRecord
    public_event_payload(payload)
    if any(type(record) is not EvidenceRecord for record in records):
        raise ValueError("evidence references must resolve to EvidenceRecord values")
    indexed = {r.evidence_id: r for r in records}
    if len(indexed) != len(records):
        raise ValueError("duplicate evidence record ID")
    for evidence_id in payload.evidence_ids:
        if evidence_id not in indexed:
            raise ValueError(f"unresolved evidence reference: {evidence_id}")
        if indexed[evidence_id].timestamp > payload.timestamp:
            raise ValueError("event evidence cannot refer to future evidence")
