from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from .errors import (
    BLIND_RESTORE,
    CONFLICTING_OVERRIDE,
    DUPLICATE_EVENT_ID,
    DUPLICATE_OPERATION_ID,
    DUPLICATE_PATCH_ID,
    DUPLICATE_SLOT_ID,
    EXPIRED_RESTORE,
    INSERT_REQUIRES_LINEAGE,
    INVALID_LINEAGE,
    INVALID_OVERRIDE_EDGE,
    INVALID_PATCH,
    INVALID_TRANSITION,
    INVALID_VALIDATION_ID,
    PRIORITY_VIOLATION,
    SAFETY_OVERRIDE_FORBIDDEN,
    SLOT_NOT_FOUND,
    STALE_PATCH_HASH,
    STATE_INVALID,
    UNAUTHORIZED_SOURCE_MUTATION,
    UNKNOWN_OPERATION,
    VALIDATION_FAILED,
    VALIDATION_NOT_FOUND,
    VALIDATION_STALE,
    CoPEError,
    TransitionError,
)
from .schema import (
    AppliedPatch,
    ConstraintMode,
    ConstraintSlot,
    ConstraintSource,
    ConstraintState,
    Demote,
    EventRecord,
    Expire,
    Insert,
    Operation,
    Override,
    Patch,
    PatchContext,
    Restore,
    Revalidate,
    Suspend,
    TransitionResult,
    ValidationIssue,
    ValidationRecord,
    ValidationReport,
    freeze_json,
)
from .serialization import canonical_state_hash, serialize_operation
from .validator import validate_state


def _operation_ids(patch: Patch) -> tuple[str, ...]:
    ids: list[str] = []
    for operation in patch.operations:
        if not isinstance(operation, (Insert, Suspend, Override, Demote, Revalidate, Restore, Expire)):
            raise TransitionError(
                UNKNOWN_OPERATION,
                f"unsupported operation class {type(operation).__name__}",
                operation_type=type(operation).__name__,
            )
        ids.append(operation.operation_id)
    return tuple(ids)


def _require_slot(slots: Mapping[str, ConstraintSlot], slot_id: str) -> ConstraintSlot:
    try:
        return slots[slot_id]
    except KeyError as exc:
        raise TransitionError(SLOT_NOT_FOUND, f"slot {slot_id!r} does not exist", slot_id=slot_id) from exc


def _authorize(slot: ConstraintSlot, context: PatchContext, action: str) -> None:
    authorized = set(context.authorized_sources)
    if slot.source is ConstraintSource.SAFETY and not context.allow_safety_override:
        raise TransitionError(
            SAFETY_OVERRIDE_FORBIDDEN,
            f"{action} of safety slot {slot.slot_id!r} requires explicit safety authorization",
            slot_id=slot.slot_id,
            action=action,
        )
    if slot.source not in authorized:
        raise TransitionError(
            UNAUTHORIZED_SOURCE_MUTATION,
            f"actor {context.actor!r} is not authorized to mutate {slot.source.value} slot {slot.slot_id!r}",
            slot_id=slot.slot_id,
            source=slot.source.value,
            actor=context.actor,
            action=action,
        )
    if context.authority_priority < slot.priority:
        raise TransitionError(
            PRIORITY_VIOLATION,
            f"authority priority {context.authority_priority} is below slot priority {slot.priority}",
            slot_id=slot.slot_id,
            slot_priority=slot.priority,
            authority_priority=context.authority_priority,
            action=action,
        )


def _authorize_creation(slot: ConstraintSlot, context: PatchContext, action: str) -> None:
    if slot.source not in set(context.authorized_sources):
        raise TransitionError(
            UNAUTHORIZED_SOURCE_MUTATION,
            f"actor {context.actor!r} is not authorized to assert {slot.source.value} source",
            slot_id=slot.slot_id,
            source=slot.source.value,
            actor=context.actor,
            action=action,
        )
    if slot.source is ConstraintSource.SAFETY and not context.allow_safety_override:
        raise TransitionError(
            SAFETY_OVERRIDE_FORBIDDEN,
            f"{action} of safety slot {slot.slot_id!r} requires explicit safety authorization",
            slot_id=slot.slot_id,
            action=action,
        )
    if context.authority_priority < slot.priority:
        raise TransitionError(
            PRIORITY_VIOLATION,
            f"authority priority {context.authority_priority} is below asserted priority {slot.priority}",
            slot_id=slot.slot_id,
            slot_priority=slot.priority,
            authority_priority=context.authority_priority,
            action=action,
        )


def _validate_insert(slot: ConstraintSlot, slots: Mapping[str, ConstraintSlot], patch: Patch) -> None:
    if slot.slot_id in slots:
        raise TransitionError(DUPLICATE_SLOT_ID, f"slot {slot.slot_id!r} already exists", slot_id=slot.slot_id)
    if slot.mode is not ConstraintMode.ACTIVE:
        raise TransitionError(INVALID_TRANSITION, "Insert requires a slot in active mode", slot_id=slot.slot_id)
    if slot.created_event_id != patch.event_id or slot.last_updated_event_id != patch.event_id:
        raise TransitionError(
            INVALID_PATCH,
            "inserted slot created_event_id and last_updated_event_id must equal patch.event_id",
            slot_id=slot.slot_id,
            event_id=patch.event_id,
        )
    if slot.overrides_slot_ids:
        raise TransitionError(
            INVALID_OVERRIDE_EDGE,
            "Insert cannot create override edges; use Override",
            slot_id=slot.slot_id,
        )
    if slot.parent_slot_id is None:
        if slot.lineage != (slot.slot_id,):
            raise TransitionError(
                INSERT_REQUIRES_LINEAGE,
                "root Insert lineage must contain exactly its own slot_id",
                slot_id=slot.slot_id,
            )
    else:
        parent = _require_slot(slots, slot.parent_slot_id)
        expected = parent.lineage + (slot.slot_id,)
        if slot.lineage != expected:
            raise TransitionError(
                INVALID_LINEAGE,
                f"derived Insert lineage must be {expected!r}",
                slot_id=slot.slot_id,
                expected=expected,
                actual=slot.lineage,
            )


def _validate_override_replacement(
    target: ConstraintSlot,
    replacement: ConstraintSlot,
    slots: Mapping[str, ConstraintSlot],
    patch: Patch,
) -> None:
    if replacement.slot_id in slots:
        raise TransitionError(
            DUPLICATE_SLOT_ID,
            f"replacement slot {replacement.slot_id!r} already exists",
            slot_id=replacement.slot_id,
        )
    if replacement.mode is not ConstraintMode.ACTIVE:
        raise TransitionError(INVALID_TRANSITION, "Override replacement must be active")
    if replacement.created_event_id != patch.event_id or replacement.last_updated_event_id != patch.event_id:
        raise TransitionError(
            INVALID_PATCH,
            "replacement created_event_id and last_updated_event_id must equal patch.event_id",
            slot_id=replacement.slot_id,
        )
    if replacement.parent_slot_id != target.slot_id:
        raise TransitionError(
            INVALID_LINEAGE,
            "Override replacement parent_slot_id must reference the overridden slot",
            slot_id=replacement.slot_id,
            expected_parent=target.slot_id,
        )
    expected_lineage = target.lineage + (replacement.slot_id,)
    if replacement.lineage != expected_lineage:
        raise TransitionError(
            INVALID_LINEAGE,
            f"Override replacement lineage must be {expected_lineage!r}",
            slot_id=replacement.slot_id,
        )
    if replacement.overrides_slot_ids != (target.slot_id,):
        raise TransitionError(
            INVALID_OVERRIDE_EDGE,
            "Override replacement must contain exactly one edge to the target slot",
            slot_id=replacement.slot_id,
            target_slot_id=target.slot_id,
        )
    if replacement.priority < target.priority:
        raise TransitionError(
            PRIORITY_VIOLATION,
            "Override replacement priority must be greater than or equal to target priority",
            slot_id=replacement.slot_id,
            replacement_priority=replacement.priority,
            target_priority=target.priority,
        )


def _affected_ids(operation: Operation) -> tuple[str, ...]:
    if isinstance(operation, Insert):
        return (operation.slot.slot_id,)
    if isinstance(operation, Override):
        return (operation.slot_id, operation.replacement.slot_id)
    return (operation.slot_id,)


def _rejection(
    state: ConstraintState,
    patch: Patch,
    report: ValidationReport,
    error: CoPEError,
) -> TransitionResult:
    if report.valid:
        report = ValidationReport(
            valid=False,
            errors=(ValidationIssue(error.code, error.message, "$.patch"),),
            warnings=report.warnings,
        )
    audit = freeze_json(
        {
            "accepted": False,
            "patch_id": patch.patch_id,
            "event_id": patch.event_id,
            "before_hash": state.state_hash,
            "after_hash": state.state_hash,
            "applied_operation_ids": [],
            "rejection": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        }
    )
    assert isinstance(audit, Mapping)
    return TransitionResult(
        state=state,
        before_hash=state.state_hash,
        after_hash=state.state_hash,
        accepted=False,
        validation_report=report,
        applied_operation_ids=(),
        rejection_reason=error.message,
        rejection_code=error.code,
        audit_record=audit,
    )


def apply_patch(state: ConstraintState, patch: Patch, context: PatchContext) -> TransitionResult:
    """Atomically apply a typed patch through the engine's sole mutation entrypoint."""
    before_report = validate_state(state)
    if not before_report.valid:
        first = before_report.errors[0]
        return _rejection(
            state,
            patch,
            before_report,
            TransitionError(first.code, f"input state is invalid: {first.message}", path=first.path),
        )

    try:
        if patch.input_state_hash != state.state_hash:
            raise TransitionError(
                STALE_PATCH_HASH,
                "patch input_state_hash does not match the current state",
                expected=state.state_hash,
                actual=patch.input_state_hash,
            )
        if patch.patch_id in {record.patch.patch_id for record in state.patch_history}:
            raise TransitionError(DUPLICATE_PATCH_ID, f"patch_id {patch.patch_id!r} already exists")
        if patch.event_id in {record.event_id for record in state.event_history}:
            raise TransitionError(DUPLICATE_EVENT_ID, f"event_id {patch.event_id!r} already exists")
        operation_ids = _operation_ids(patch)
        if len(set(operation_ids)) != len(operation_ids):
            raise TransitionError(DUPLICATE_OPERATION_ID, "operation IDs within a patch must be unique")
        historical_operation_ids = {
            operation.operation_id
            for record in state.patch_history
            for operation in record.patch.operations
        }
        repeated = historical_operation_ids.intersection(operation_ids)
        if repeated:
            raise TransitionError(
                DUPLICATE_OPERATION_ID,
                f"operation IDs already exist: {sorted(repeated)}",
            )

        slots = {slot.slot_id: slot for slot in state.slots}
        validations = list(state.validation_history)
        validation_by_id = {record.validation_id: record for record in validations}
        operation_audit: list[dict[str, Any]] = []
        affected: set[str] = set()

        for operation in patch.operations:
            operation_audit.append(serialize_operation(operation))
            affected.update(_affected_ids(operation))

            if isinstance(operation, Insert):
                _authorize_creation(operation.slot, context, "insert")
                _validate_insert(operation.slot, slots, patch)
                slots[operation.slot.slot_id] = operation.slot
                continue

            if isinstance(operation, Suspend):
                slot = _require_slot(slots, operation.slot_id)
                _authorize(slot, context, "suspend")
                if slot.mode not in {ConstraintMode.ACTIVE, ConstraintMode.DEMOTED}:
                    raise TransitionError(
                        INVALID_TRANSITION,
                        f"cannot suspend slot in {slot.mode.value} mode",
                        slot_id=slot.slot_id,
                    )
                slots[slot.slot_id] = replace(
                    slot,
                    mode=ConstraintMode.SUSPENDED,
                    last_updated_event_id=patch.event_id,
                )
                continue

            if isinstance(operation, Override):
                target = _require_slot(slots, operation.slot_id)
                _authorize(target, context, "override")
                if target.mode not in {ConstraintMode.ACTIVE, ConstraintMode.DEMOTED}:
                    raise TransitionError(
                        INVALID_TRANSITION,
                        f"cannot override slot in {target.mode.value} mode",
                        slot_id=target.slot_id,
                    )
                _authorize_creation(operation.replacement, context, "override replacement")
                _validate_override_replacement(target, operation.replacement, slots, patch)
                slots[target.slot_id] = replace(
                    target,
                    mode=ConstraintMode.OVERRIDDEN,
                    last_updated_event_id=patch.event_id,
                )
                slots[operation.replacement.slot_id] = operation.replacement
                continue

            if isinstance(operation, Demote):
                slot = _require_slot(slots, operation.slot_id)
                _authorize(slot, context, "demote")
                if slot.mode not in {ConstraintMode.ACTIVE, ConstraintMode.DEMOTED}:
                    raise TransitionError(
                        INVALID_TRANSITION,
                        f"cannot demote slot in {slot.mode.value} mode",
                        slot_id=slot.slot_id,
                    )
                if not 0 <= operation.new_priority < slot.priority:
                    raise TransitionError(
                        PRIORITY_VIOLATION,
                        "Demote new_priority must be non-negative and strictly lower",
                        slot_id=slot.slot_id,
                        current_priority=slot.priority,
                        new_priority=operation.new_priority,
                    )
                for target_id in slot.overrides_slot_ids:
                    target = _require_slot(slots, target_id)
                    if operation.new_priority < target.priority:
                        raise TransitionError(
                            PRIORITY_VIOLATION,
                            "cannot demote an active overriding slot below its target",
                            slot_id=slot.slot_id,
                            target_slot_id=target_id,
                        )
                slots[slot.slot_id] = replace(
                    slot,
                    mode=ConstraintMode.DEMOTED,
                    priority=operation.new_priority,
                    last_updated_event_id=patch.event_id,
                )
                continue

            if isinstance(operation, Revalidate):
                slot = _require_slot(slots, operation.slot_id)
                if slot.mode is ConstraintMode.EXPIRED:
                    raise TransitionError(
                        EXPIRED_RESTORE,
                        f"expired slot {slot.slot_id!r} cannot be revalidated for restoration",
                        slot_id=slot.slot_id,
                    )
                if slot.mode not in {ConstraintMode.SUSPENDED, ConstraintMode.OVERRIDDEN}:
                    raise TransitionError(
                        INVALID_TRANSITION,
                        "Revalidate requires suspended or overridden mode",
                        slot_id=slot.slot_id,
                        mode=slot.mode.value,
                    )
                if operation.applies_to_last_updated_event_id != slot.last_updated_event_id:
                    raise TransitionError(
                        VALIDATION_STALE,
                        "revalidation guard was evaluated against a different slot update",
                        slot_id=slot.slot_id,
                        expected=slot.last_updated_event_id,
                        actual=operation.applies_to_last_updated_event_id,
                    )
                from .recovery import stable_validation_id

                expected_id = stable_validation_id(
                    state_id=state.state_id,
                    slot_id=slot.slot_id,
                    validator_id=operation.validator_id,
                    evidence=operation.evidence,
                    result=operation.result,
                    applies_to_last_updated_event_id=operation.applies_to_last_updated_event_id,
                )
                if operation.validation_id != expected_id:
                    raise TransitionError(
                        INVALID_VALIDATION_ID,
                        "validation_id is not the stable digest of the guard inputs",
                        expected=expected_id,
                        actual=operation.validation_id,
                    )
                if operation.validation_id in validation_by_id:
                    raise TransitionError(
                        INVALID_VALIDATION_ID,
                        f"validation_id {operation.validation_id!r} already exists",
                    )
                record = ValidationRecord(
                    validation_id=operation.validation_id,
                    slot_id=slot.slot_id,
                    validator_id=operation.validator_id,
                    result=operation.result,
                    evidence=operation.evidence,
                    state_revision=state.revision,
                    applies_to_last_updated_event_id=operation.applies_to_last_updated_event_id,
                    event_id=patch.event_id,
                    operation_id=operation.operation_id,
                )
                validations.append(record)
                validation_by_id[record.validation_id] = record
                continue

            if isinstance(operation, Restore):
                slot = _require_slot(slots, operation.slot_id)
                if slot.mode is ConstraintMode.EXPIRED:
                    raise TransitionError(
                        EXPIRED_RESTORE,
                        f"expired slot {slot.slot_id!r} can never be restored",
                        slot_id=slot.slot_id,
                    )
                if slot.mode not in {ConstraintMode.SUSPENDED, ConstraintMode.OVERRIDDEN}:
                    raise TransitionError(
                        INVALID_TRANSITION,
                        "Restore requires suspended or overridden mode",
                        slot_id=slot.slot_id,
                        mode=slot.mode.value,
                    )
                if not operation.validation_id:
                    raise TransitionError(BLIND_RESTORE, "Restore requires a validation_id", slot_id=slot.slot_id)
                validation = validation_by_id.get(operation.validation_id)
                if validation is None:
                    raise TransitionError(
                        VALIDATION_NOT_FOUND,
                        f"validation {operation.validation_id!r} does not exist",
                        slot_id=slot.slot_id,
                    )
                if validation.slot_id != slot.slot_id:
                    raise TransitionError(
                        BLIND_RESTORE,
                        "validation belongs to a different slot",
                        slot_id=slot.slot_id,
                        validation_slot_id=validation.slot_id,
                    )
                if not validation.result:
                    raise TransitionError(
                        VALIDATION_FAILED,
                        "failed revalidation cannot authorize Restore",
                        slot_id=slot.slot_id,
                        validation_id=validation.validation_id,
                    )
                if validation.applies_to_last_updated_event_id != slot.last_updated_event_id:
                    raise TransitionError(
                        VALIDATION_STALE,
                        "successful validation is stale for the current slot",
                        slot_id=slot.slot_id,
                        validation_id=validation.validation_id,
                    )
                conflicting = [
                    candidate.slot_id
                    for candidate in slots.values()
                    if slot.slot_id in candidate.overrides_slot_ids
                    and candidate.mode in {ConstraintMode.ACTIVE, ConstraintMode.DEMOTED}
                ]
                if conflicting:
                    raise TransitionError(
                        CONFLICTING_OVERRIDE,
                        "cannot restore while an active overriding constraint exists",
                        slot_id=slot.slot_id,
                        overriding_slot_ids=sorted(conflicting),
                    )
                slots[slot.slot_id] = replace(
                    slot,
                    mode=ConstraintMode.ACTIVE,
                    last_updated_event_id=patch.event_id,
                    evidence_refs=slot.evidence_refs + (validation.validation_id,),
                )
                continue

            if isinstance(operation, Expire):
                slot = _require_slot(slots, operation.slot_id)
                _authorize(slot, context, "expire")
                if slot.mode is ConstraintMode.EXPIRED:
                    raise TransitionError(
                        INVALID_TRANSITION,
                        f"slot {slot.slot_id!r} is already expired",
                        slot_id=slot.slot_id,
                    )
                slots[slot.slot_id] = replace(
                    slot,
                    mode=ConstraintMode.EXPIRED,
                    last_updated_event_id=patch.event_id,
                )
                continue

            raise TransitionError(
                UNKNOWN_OPERATION,
                f"unsupported operation class {type(operation).__name__}",
            )

        next_revision = state.revision + 1
        event = EventRecord(
            event_id=patch.event_id,
            patch_id=patch.patch_id,
            revision=next_revision,
            reason=patch.reason,
            generator=patch.generator,
            applied_operation_ids=operation_ids,
            affected_slot_ids=tuple(sorted(affected)),
            details={
                "actor": context.actor,
                "event_source": context.event_source.value if context.event_source else None,
                "information_budget": context.information_budget,
                "policy_step_budget": context.policy_step_budget,
                "high_level_call_count": context.high_level_call_count,
                "manual_intervention": context.manual_intervention,
                "operations": operation_audit,
            },
        )
        provisional = ConstraintState(
            schema_version=state.schema_version,
            state_id=state.state_id,
            revision=next_revision,
            slots=tuple(sorted(slots.values(), key=lambda item: item.slot_id)),
            event_history=state.event_history + (event,),
            patch_history=state.patch_history + (AppliedPatch(patch, context),),
            validation_history=tuple(validations),
            state_hash="pending",
        )
        next_state = replace(provisional, state_hash=canonical_state_hash(provisional))
        final_report = validate_state(next_state)
        if not final_report.valid:
            first = final_report.errors[0]
            raise TransitionError(
                first.code,
                f"patch would violate state invariants: {first.message}",
                path=first.path,
            )
        audit = freeze_json(
            {
                "accepted": True,
                "patch_id": patch.patch_id,
                "event_id": patch.event_id,
                "generator": patch.generator,
                "actor": context.actor,
                "before_hash": state.state_hash,
                "after_hash": next_state.state_hash,
                "revision_before": state.revision,
                "revision_after": next_state.revision,
                "applied_operation_ids": operation_ids,
                "operations": operation_audit,
                "validation": {"valid": True, "error_count": 0},
            }
        )
        assert isinstance(audit, Mapping)
        return TransitionResult(
            state=next_state,
            before_hash=state.state_hash,
            after_hash=next_state.state_hash,
            accepted=True,
            validation_report=final_report,
            applied_operation_ids=operation_ids,
            rejection_reason=None,
            rejection_code=None,
            audit_record=audit,
        )
    except CoPEError as error:
        return _rejection(state, patch, before_report, error)
