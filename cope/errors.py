from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class ErrorDetail:
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


class CoPEError(Exception):
    """Base exception carrying a stable, machine-readable error code."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def as_detail(self) -> ErrorDetail:
        return ErrorDetail(self.code, self.message, self.details)


class SchemaError(CoPEError):
    pass


class InvariantError(CoPEError):
    pass


class TransitionError(CoPEError):
    pass


SCHEMA_VERSION_UNSUPPORTED = "SCHEMA_VERSION_UNSUPPORTED"
SCHEMA_UNKNOWN_FIELD = "SCHEMA_UNKNOWN_FIELD"
SCHEMA_MISSING_FIELD = "SCHEMA_MISSING_FIELD"
UNKNOWN_OPERATION = "UNKNOWN_OPERATION"
INVALID_ENUM = "INVALID_ENUM"
INVALID_JSON_VALUE = "INVALID_JSON_VALUE"
INVALID_PATCH = "INVALID_PATCH"
STATE_INVALID = "STATE_INVALID"
HASH_MISMATCH = "HASH_MISMATCH"
HISTORY_REPLAY_MISMATCH = "HISTORY_REPLAY_MISMATCH"
STALE_PATCH_HASH = "STALE_PATCH_HASH"
DUPLICATE_PATCH_ID = "DUPLICATE_PATCH_ID"
DUPLICATE_EVENT_ID = "DUPLICATE_EVENT_ID"
DUPLICATE_OPERATION_ID = "DUPLICATE_OPERATION_ID"
DUPLICATE_SLOT_ID = "DUPLICATE_SLOT_ID"
SLOT_NOT_FOUND = "SLOT_NOT_FOUND"
INVALID_TRANSITION = "INVALID_TRANSITION"
LINEAGE_CYCLE = "LINEAGE_CYCLE"
OVERRIDE_CYCLE = "OVERRIDE_CYCLE"
DANGLING_REFERENCE = "DANGLING_REFERENCE"
INVALID_LINEAGE = "INVALID_LINEAGE"
INVALID_OVERRIDE_EDGE = "INVALID_OVERRIDE_EDGE"
PRIORITY_VIOLATION = "PRIORITY_VIOLATION"
UNAUTHORIZED_SOURCE_MUTATION = "UNAUTHORIZED_SOURCE_MUTATION"
SAFETY_OVERRIDE_FORBIDDEN = "SAFETY_OVERRIDE_FORBIDDEN"
BLIND_RESTORE = "BLIND_RESTORE"
VALIDATION_NOT_FOUND = "VALIDATION_NOT_FOUND"
VALIDATION_FAILED = "VALIDATION_FAILED"
VALIDATION_STALE = "VALIDATION_STALE"
EXPIRED_RESTORE = "EXPIRED_RESTORE"
INVALID_VALIDATION_ID = "INVALID_VALIDATION_ID"
VALIDATOR_ERROR = "VALIDATOR_ERROR"
INSERT_REQUIRES_LINEAGE = "INSERT_REQUIRES_LINEAGE"
CONFLICTING_OVERRIDE = "CONFLICTING_OVERRIDE"
