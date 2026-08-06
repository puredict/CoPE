from __future__ import annotations

import pytest

from cope import (
    ConstraintState,
    Expire,
    Insert,
    PatchContext,
    Restore,
    Suspend,
    apply_patch,
)
from cope.errors import (
    DUPLICATE_OPERATION_ID,
    DUPLICATE_SLOT_ID,
    EXPIRED_RESTORE,
    PRIORITY_VIOLATION,
    SLOT_NOT_FOUND,
    STALE_PATCH_HASH,
    VALIDATION_NOT_FOUND,
)

from conftest import apply_ok, make_patch, make_slot, state_with_root


MANUAL_COUNTEREXAMPLES = [
    (f"missing-slot-{index:02d}", "missing", SLOT_NOT_FOUND) for index in range(8)
] + [
    (f"duplicate-insert-{index:02d}", "duplicate", DUPLICATE_SLOT_ID) for index in range(8)
] + [
    (f"blind-restore-{index:02d}", "blind", VALIDATION_NOT_FOUND) for index in range(8)
] + [
    (f"expired-restore-{index:02d}", "expired", EXPIRED_RESTORE) for index in range(8)
] + [
    (f"priority-violation-{index:02d}", "priority", PRIORITY_VIOLATION) for index in range(8)
] + [
    (f"middle-failure-{index:02d}", "middle", SLOT_NOT_FOUND) for index in range(8)
] + [
    (f"stale-input-hash-{index:02d}", "stale", STALE_PATCH_HASH) for index in range(8)
] + [
    (f"duplicate-operation-{index:02d}", "duplicate-op", DUPLICATE_OPERATION_ID) for index in range(8)
]


@pytest.mark.parametrize("label,kind,expected_code", MANUAL_COUNTEREXAMPLES, ids=lambda value: str(value))
def test_64_manual_counterexamples_have_stable_error_codes(label, kind, expected_code) -> None:
    state = state_with_root(slot_id="root")
    context = PatchContext.trusted(label)
    number = 2

    if kind == "missing":
        operations = [Suspend(f"op-{label}", f"absent-{label}", "invalid slot")]
        patch = make_patch(state, number, operations)
    elif kind == "duplicate":
        duplicate = make_slot("root", "event-2", content={"case": label})
        patch = make_patch(state, number, [Insert(f"op-{label}", duplicate)])
    elif kind == "blind":
        state = apply_ok(state, 2, [Suspend(f"op-suspend-{label}", "root", "temporary")])
        number = 3
        patch = make_patch(
            state,
            number,
            [Restore(f"op-{label}", "root", f"unknown-validation-{label}", "blind")],
        )
    elif kind == "expired":
        state = apply_ok(state, 2, [Expire(f"op-expire-{label}", "root", "obsolete")])
        number = 3
        patch = make_patch(
            state,
            number,
            [Restore(f"op-{label}", "root", f"validation-{label}", "illegal")],
        )
    elif kind == "priority":
        context = PatchContext(
            actor=label,
            authority_priority=int(label[-2:]),
            authorized_sources=("task",),
        )
        patch = make_patch(state, number, [Suspend(f"op-{label}", "root", "too weak")])
    elif kind == "middle":
        temporary = make_slot(f"temporary-{label}", "event-2")
        patch = make_patch(
            state,
            number,
            [
                Insert(f"op-first-{label}", temporary),
                Suspend(f"op-fail-{label}", f"absent-{label}", "middle failure"),
            ],
        )
    elif kind == "stale":
        patch = make_patch(
            state,
            number,
            [Suspend(f"op-{label}", "root", "stale")],
            input_hash=("0" * 63 + label[-1]),
        )
    elif kind == "duplicate-op":
        operation_id = f"op-{label}"
        patch = make_patch(
            state,
            number,
            [
                Suspend(operation_id, "root", "first"),
                Expire(operation_id, "root", "second"),
            ],
        )
    else:
        raise AssertionError(kind)

    before_hash = state.state_hash
    result = apply_patch(state, patch, context)
    assert not result.accepted, label
    assert result.rejection_code == expected_code, label
    assert result.before_hash == result.after_hash == before_hash, label
    assert result.state is state, label
