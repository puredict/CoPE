from __future__ import annotations

from dataclasses import replace
from typing import Iterable

import pytest

from cope import (
    ConstraintSlot,
    ConstraintState,
    Insert,
    Patch,
    PatchContext,
    apply_patch,
    canonical_state_hash,
)


def make_slot(
    slot_id: str,
    event_id: str,
    *,
    constraint_type: str = "object_alignment",
    content: dict | None = None,
    source: str = "task",
    mode: str = "active",
    priority: int = 50,
    parent: ConstraintSlot | None = None,
    overrides: tuple[str, ...] = (),
    metadata: dict | None = None,
) -> ConstraintSlot:
    return ConstraintSlot(
        slot_id=slot_id,
        constraint_type=constraint_type,
        content=content or {"object_id": "cup-1", "relation": "aligned"},
        source=source,
        mode=mode,
        priority=priority,
        created_event_id=event_id,
        last_updated_event_id=event_id,
        parent_slot_id=parent.slot_id if parent else None,
        overrides_slot_ids=overrides,
        lineage=(parent.lineage + (slot_id,)) if parent else (slot_id,),
        metadata=metadata or {},
    )


def make_patch(
    state: ConstraintState,
    number: int,
    operations: Iterable,
    *,
    reason: str = "test transition",
    generator: str = "pytest",
    input_hash: str | None = None,
) -> Patch:
    return Patch(
        patch_id=f"patch-{number}",
        event_id=f"event-{number}",
        reason=reason,
        operations=tuple(operations),
        generator=generator,
        input_state_hash=input_hash or state.state_hash,
        created_at=number,
        metadata={"sequence": number},
    )


def apply_ok(
    state: ConstraintState,
    number: int,
    operations: Iterable,
    context: PatchContext | None = None,
) -> ConstraintState:
    result = apply_patch(state, make_patch(state, number, operations), context or PatchContext.trusted("pytest"))
    assert result.accepted, (result.rejection_code, result.rejection_reason)
    return result.state


def state_with_root(
    *,
    source: str = "task",
    priority: int = 50,
    slot_id: str = "alignment-1",
) -> ConstraintState:
    state = ConstraintState.empty("test-state")
    slot = make_slot(slot_id, "event-1", source=source, priority=priority)
    return apply_ok(state, 1, [Insert("op-insert-root", slot)])


def rehash(state: ConstraintState) -> ConstraintState:
    return replace(state, state_hash=canonical_state_hash(state))


@pytest.fixture
def trusted_context() -> PatchContext:
    return PatchContext.trusted("pytest")


@pytest.fixture
def root_state() -> ConstraintState:
    return state_with_root()
