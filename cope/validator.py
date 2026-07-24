from __future__ import annotations

from collections.abc import Iterable
from contextvars import ContextVar

from .errors import (
    DANGLING_REFERENCE,
    DUPLICATE_EVENT_ID,
    DUPLICATE_OPERATION_ID,
    DUPLICATE_PATCH_ID,
    DUPLICATE_SLOT_ID,
    HASH_MISMATCH,
    HISTORY_REPLAY_MISMATCH,
    INVALID_LINEAGE,
    INVALID_OVERRIDE_EDGE,
    LINEAGE_CYCLE,
    OVERRIDE_CYCLE,
    PRIORITY_VIOLATION,
    SCHEMA_VERSION_UNSUPPORTED,
    STATE_INVALID,
    UNKNOWN_OPERATION,
)
from .schema import (
    SCHEMA_VERSION,
    ConstraintMode,
    ConstraintState,
    Expire,
    Insert,
    Override,
    Revalidate,
    Restore,
    Suspend,
    Demote,
    ValidationIssue,
    ValidationReport,
)
from .serialization import canonical_state_hash


_HISTORY_AUDIT_ACTIVE: ContextVar[bool] = ContextVar("cope_history_audit_active", default=False)


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicate: set[str] = set()
    for value in values:
        if value in seen:
            duplicate.add(value)
        seen.add(value)
    return duplicate


def _cycles(graph: dict[str, tuple[str, ...]]) -> list[tuple[str, ...]]:
    found: list[tuple[str, ...]] = []
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            start = visiting.index(node)
            found.append(tuple(visiting[start:] + [node]))
            return
        if node in visited:
            return
        visiting.append(node)
        for neighbor in graph.get(node, ()):
            if neighbor in graph:
                visit(neighbor)
        visiting.pop()
        visited.add(node)

    for node in graph:
        visit(node)
    return found


def validate_state(state: ConstraintState) -> ValidationReport:
    """Validate all state invariants, including canonical hash integrity."""
    errors: list[ValidationIssue] = []

    def issue(code: str, message: str, path: str) -> None:
        errors.append(ValidationIssue(code, message, path))

    if state.schema_version != SCHEMA_VERSION:
        issue(
            SCHEMA_VERSION_UNSUPPORTED,
            f"expected schema_version {SCHEMA_VERSION!r}, got {state.schema_version!r}",
            "$.schema_version",
        )
    if state.revision != len(state.patch_history):
        issue(
            STATE_INVALID,
            f"revision {state.revision} does not match patch history length {len(state.patch_history)}",
            "$.revision",
        )
    if len(state.event_history) != len(state.patch_history):
        issue(
            STATE_INVALID,
            "every successful patch must have exactly one event history record",
            "$.event_history",
        )

    slots = {slot.slot_id: slot for slot in state.slots}
    for duplicate in sorted(_duplicates(slot.slot_id for slot in state.slots)):
        issue(DUPLICATE_SLOT_ID, f"duplicate slot_id {duplicate!r}", "$.slots")

    patch_ids = [record.patch.patch_id for record in state.patch_history]
    event_ids = [record.event_id for record in state.event_history]
    for duplicate in sorted(_duplicates(patch_ids)):
        issue(DUPLICATE_PATCH_ID, f"duplicate patch_id {duplicate!r}", "$.patch_history")
    for duplicate in sorted(_duplicates(event_ids)):
        issue(DUPLICATE_EVENT_ID, f"duplicate event_id {duplicate!r}", "$.event_history")

    all_operation_ids: list[str] = []
    valid_operation_types = (Insert, Suspend, Override, Demote, Revalidate, Restore, Expire)
    for index, record in enumerate(state.patch_history):
        patch = record.patch
        all_operation_ids.extend(
            operation.operation_id
            for operation in patch.operations
            if hasattr(operation, "operation_id")
        )
        for operation_index, operation in enumerate(patch.operations):
            if not isinstance(operation, valid_operation_types):
                issue(
                    UNKNOWN_OPERATION,
                    f"unknown operation class {type(operation).__name__}",
                    f"$.patch_history[{index}].patch.operations[{operation_index}]",
                )
    for duplicate in sorted(_duplicates(all_operation_ids)):
        issue(DUPLICATE_OPERATION_ID, f"duplicate operation_id {duplicate!r}", "$.patch_history")

    known_events = set(event_ids)
    for index, slot in enumerate(state.slots):
        path = f"$.slots[{index}]"
        if slot.created_event_id not in known_events:
            issue(
                DANGLING_REFERENCE,
                f"created_event_id {slot.created_event_id!r} does not exist",
                f"{path}.created_event_id",
            )
        if slot.last_updated_event_id not in known_events:
            issue(
                DANGLING_REFERENCE,
                f"last_updated_event_id {slot.last_updated_event_id!r} does not exist",
                f"{path}.last_updated_event_id",
            )
        if not slot.lineage or slot.lineage[-1] != slot.slot_id:
            issue(
                INVALID_LINEAGE,
                "lineage must be non-empty and end with the slot's own ID",
                f"{path}.lineage",
            )
        if len(set(slot.lineage)) != len(slot.lineage):
            issue(LINEAGE_CYCLE, f"lineage contains a cycle: {slot.lineage!r}", f"{path}.lineage")
        if slot.parent_slot_id is None:
            if slot.lineage != (slot.slot_id,):
                issue(
                    INVALID_LINEAGE,
                    "root slot lineage must contain only its own ID",
                    f"{path}.lineage",
                )
        elif slot.parent_slot_id not in slots:
            issue(
                DANGLING_REFERENCE,
                f"parent_slot_id {slot.parent_slot_id!r} does not exist",
                f"{path}.parent_slot_id",
            )
        else:
            expected = slots[slot.parent_slot_id].lineage + (slot.slot_id,)
            if slot.lineage != expected:
                issue(
                    INVALID_LINEAGE,
                    f"derived slot lineage must equal parent lineage plus own ID; expected {expected!r}",
                    f"{path}.lineage",
                )
        for target_id in slot.overrides_slot_ids:
            if target_id == slot.slot_id:
                issue(INVALID_OVERRIDE_EDGE, "slot cannot override itself", f"{path}.overrides_slot_ids")
            elif target_id not in slots:
                issue(
                    DANGLING_REFERENCE,
                    f"overridden slot {target_id!r} does not exist",
                    f"{path}.overrides_slot_ids",
                )
            else:
                target = slots[target_id]
                if slot.mode in {ConstraintMode.ACTIVE, ConstraintMode.DEMOTED}:
                    if target.mode not in {ConstraintMode.OVERRIDDEN, ConstraintMode.EXPIRED}:
                        issue(
                            INVALID_OVERRIDE_EDGE,
                            f"active overriding slot requires target {target_id!r} to be overridden or expired",
                            f"{path}.overrides_slot_ids",
                        )
                    if slot.priority < target.priority:
                        issue(
                            PRIORITY_VIOLATION,
                            f"overriding slot priority {slot.priority} is below target priority {target.priority}",
                            f"{path}.priority",
                        )

    lineage_graph = {
        slot.slot_id: ((slot.parent_slot_id,) if slot.parent_slot_id is not None else ())
        for slot in state.slots
    }
    for cycle in _cycles(lineage_graph):
        issue(LINEAGE_CYCLE, f"lineage cycle detected: {' -> '.join(cycle)}", "$.slots")
    override_graph = {slot.slot_id: slot.overrides_slot_ids for slot in state.slots}
    for cycle in _cycles(override_graph):
        issue(OVERRIDE_CYCLE, f"override cycle detected: {' -> '.join(cycle)}", "$.slots")

    validation_ids = [record.validation_id for record in state.validation_history]
    for duplicate in sorted(_duplicates(validation_ids)):
        issue(STATE_INVALID, f"duplicate validation_id {duplicate!r}", "$.validation_history")
    operation_id_set = set(all_operation_ids)
    for index, record in enumerate(state.validation_history):
        path = f"$.validation_history[{index}]"
        if record.slot_id not in slots:
            issue(DANGLING_REFERENCE, f"validation slot {record.slot_id!r} does not exist", f"{path}.slot_id")
        if record.event_id not in known_events:
            issue(DANGLING_REFERENCE, f"validation event {record.event_id!r} does not exist", f"{path}.event_id")
        if record.operation_id not in operation_id_set:
            issue(
                DANGLING_REFERENCE,
                f"validation operation {record.operation_id!r} does not exist",
                f"{path}.operation_id",
            )
        if not 0 <= record.state_revision < state.revision:
            issue(
                STATE_INVALID,
                f"validation state_revision {record.state_revision} is outside state history",
                f"{path}.state_revision",
            )

    for index, (event, applied) in enumerate(zip(state.event_history, state.patch_history)):
        patch = applied.patch
        path = f"$.event_history[{index}]"
        expected_revision = index + 1
        if event.revision != expected_revision:
            issue(
                STATE_INVALID,
                f"event revision must be {expected_revision}, got {event.revision}",
                f"{path}.revision",
            )
        if event.patch_id != patch.patch_id or event.event_id != patch.event_id:
            issue(STATE_INVALID, "event record does not match its applied patch", path)
        expected_operation_ids = tuple(operation.operation_id for operation in patch.operations)
        if event.applied_operation_ids != expected_operation_ids:
            issue(
                STATE_INVALID,
                "event applied_operation_ids do not match patch operations",
                f"{path}.applied_operation_ids",
            )

    try:
        expected_hash = canonical_state_hash(state)
        if state.state_hash != expected_hash:
            issue(
                HASH_MISMATCH,
                f"state_hash mismatch: expected {expected_hash}, got {state.state_hash}",
                "$.state_hash",
            )
    except Exception as exc:
        issue(STATE_INVALID, f"state cannot be canonically serialized: {exc}", "$")

    if not errors and state.patch_history and not _HISTORY_AUDIT_ACTIVE.get():
        token = _HISTORY_AUDIT_ACTIVE.set(True)
        try:
            from .replay import replay
            from .serialization import serialize_state

            reconstructed = replay(ConstraintState.empty(state.state_id), state.patch_history)
            if serialize_state(reconstructed) != serialize_state(state):
                issue(
                    HISTORY_REPLAY_MISMATCH,
                    "state content does not match deterministic replay of append-only patch history",
                    "$",
                )
        except Exception as exc:
            issue(
                getattr(exc, "code", HISTORY_REPLAY_MISMATCH),
                f"patch history cannot be replayed: {exc}",
                "$.patch_history",
            )
        finally:
            _HISTORY_AUDIT_ACTIVE.reset(token)

    return ValidationReport(valid=not errors, errors=tuple(errors), warnings=())
