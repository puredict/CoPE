from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .errors import INVALID_PATCH, STATE_INVALID, InvariantError, SchemaError
from .operations import apply_patch
from .schema import AppliedPatch, ConstraintState
from .serialization import deserialize_context, deserialize_patch
from .validator import validate_state


def _applied_patch(value: AppliedPatch | Mapping[str, Any], index: int) -> AppliedPatch:
    if isinstance(value, AppliedPatch):
        return value
    if isinstance(value, Mapping) and set(value) == {"patch", "context"}:
        return AppliedPatch(
            patch=deserialize_patch(value["patch"], path=f"$.patch_history[{index}].patch"),
            context=deserialize_context(value["context"], path=f"$.patch_history[{index}].context"),
        )
    raise SchemaError(
        INVALID_PATCH,
        "replay entries must be AppliedPatch values or objects containing patch and context",
        index=index,
    )


def replay(
    initial_state: ConstraintState,
    patch_history: Sequence[AppliedPatch | Mapping[str, Any]],
) -> ConstraintState:
    """Deterministically replay accepted patches with their authorization context."""
    report = validate_state(initial_state)
    if not report.valid:
        first = report.errors[0]
        raise InvariantError(first.code, f"initial state is invalid: {first.message}", path=first.path)
    state = initial_state
    for index, value in enumerate(patch_history):
        record = _applied_patch(value, index)
        result = apply_patch(state, record.patch, record.context)
        if not result.accepted:
            raise InvariantError(
                result.rejection_code or STATE_INVALID,
                f"replay rejected patch {record.patch.patch_id!r}: {result.rejection_reason}",
                index=index,
                patch_id=record.patch.patch_id,
            )
        state = result.state
    return state
