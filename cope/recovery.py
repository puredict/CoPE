from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, Mapping

from .errors import EXPIRED_RESTORE, INVALID_TRANSITION, VALIDATION_FAILED, VALIDATOR_ERROR, TransitionError
from .schema import (
    ConstraintMode,
    ConstraintSlot,
    ConstraintState,
    Revalidate,
    RevalidationResult,
    freeze_json,
)
from .serialization import thaw_json


def stable_validation_id(
    *,
    state_id: str,
    slot_id: str,
    validator_id: str,
    evidence: Mapping[str, Any],
    result: bool,
    applies_to_last_updated_event_id: str,
) -> str:
    payload = {
        "state_id": state_id,
        "slot_id": slot_id,
        "validator_id": validator_id,
        "evidence": thaw_json(evidence),
        "result": result,
        "applies_to_last_updated_event_id": applies_to_last_updated_event_id,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return "val-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validator_identity(validator: Any) -> str:
    identity = getattr(validator, "validator_id", None)
    if identity is None:
        identity = getattr(validator, "__name__", None)
    if not isinstance(identity, str) or not identity.strip():
        raise TransitionError(
            VALIDATOR_ERROR,
            "validator must expose a non-empty validator_id or __name__",
        )
    return identity


def _run_validator(
    validator: Any,
    slot: ConstraintSlot,
    evidence: Mapping[str, Any],
) -> bool:
    function = getattr(validator, "validate", validator)
    if not callable(function):
        raise TransitionError(VALIDATOR_ERROR, "validator is not callable and has no validate method")
    return bool(function(slot, evidence))


def revalidate_slot(
    state: ConstraintState,
    slot_id: str,
    evidence: Mapping[str, Any],
    validator: Callable[[ConstraintSlot, Mapping[str, Any]], bool] | Any,
) -> RevalidationResult:
    """Run an explicit restoration guard and return a deterministic Revalidate operation."""
    slot = state.get_slot(slot_id)
    if slot.mode is ConstraintMode.EXPIRED:
        raise TransitionError(
            EXPIRED_RESTORE,
            f"expired slot {slot_id!r} cannot be revalidated for restoration",
            slot_id=slot_id,
        )
    if slot.mode not in {ConstraintMode.SUSPENDED, ConstraintMode.OVERRIDDEN}:
        raise TransitionError(
            INVALID_TRANSITION,
            "revalidation guard requires suspended or overridden mode",
            slot_id=slot_id,
            mode=slot.mode.value,
        )
    frozen_evidence = freeze_json(evidence, path="$.evidence")
    assert isinstance(frozen_evidence, Mapping)
    validator_id = _validator_identity(validator)
    error_code: str | None = None
    error_message: str | None = None
    try:
        success = _run_validator(validator, slot, frozen_evidence)
        if not success:
            error_code = VALIDATION_FAILED
            error_message = "validator guard returned false"
    except Exception as exc:
        success = False
        error_code = VALIDATOR_ERROR
        error_message = f"validator raised {type(exc).__name__}: {exc}"
    validation_id = stable_validation_id(
        state_id=state.state_id,
        slot_id=slot.slot_id,
        validator_id=validator_id,
        evidence=frozen_evidence,
        result=success,
        applies_to_last_updated_event_id=slot.last_updated_event_id,
    )
    operation = Revalidate(
        operation_id=f"op-{validation_id}",
        slot_id=slot.slot_id,
        validation_id=validation_id,
        validator_id=validator_id,
        evidence=frozen_evidence,
        result=success,
        applies_to_last_updated_event_id=slot.last_updated_event_id,
        reason="explicit restoration guard",
    )
    return RevalidationResult(
        success=success,
        validation_id=validation_id,
        validator_id=validator_id,
        evidence=frozen_evidence,
        operation=operation,
        error_code=error_code,
        error_message=error_message,
    )
