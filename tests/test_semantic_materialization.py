from __future__ import annotations

import copy

import pytest

from cope.semantic_cancellation import (
    apply_oracle_cancellation_patch,
    build_cancellation_event,
    build_oracle_cancellation_state,
)
from cope.semantic_materialization import (
    materialize_cancellation_receipt,
    materialize_replacement_receipt,
)
from cope.semantic_replacement import (
    FullStateValidationError,
    MilestoneEvent,
    apply_oracle_replacement_patch,
    build_oracle_full_state,
    build_replacement_event,
)


def replacement_pair(*, previous_state_version: int = 0, replacement: str = "alphabet_soup_1"):
    milestone = MilestoneEvent(120, "cream_cheese_1", "butter_1", 5)
    event = build_replacement_event(
        milestone,
        pair_key=f"replacement-{previous_state_version}-{replacement}",
        previous_state_version=previous_state_version,
        replacement_object=replacement,
    )
    receipt = apply_oracle_replacement_patch(
        event,
        physically_true_objects=("cream_cheese_1",),
    )
    return event, receipt


def cancellation_pair(*, previous_state_version: int = 0):
    milestone = MilestoneEvent(135, "cream_cheese_1", "butter_1", 5)
    event = build_cancellation_event(
        milestone,
        pair_key=f"cancellation-{previous_state_version}",
        previous_state_version=previous_state_version,
    )
    receipt = apply_oracle_cancellation_patch(
        event,
        physically_true_objects=("cream_cheese_1",),
    )
    return event, receipt


@pytest.mark.parametrize(("previous_state_version", "replacement"), ((0, "alphabet_soup_1"), (5, "milk_1")))
def test_replacement_materializes_to_exact_native_full_state(previous_state_version, replacement) -> None:
    event, receipt = replacement_pair(
        previous_state_version=previous_state_version,
        replacement=replacement,
    )
    materialized = materialize_replacement_receipt(
        receipt,
        event,
        physically_true_objects=("cream_cheese_1",),
    )
    assert materialized == build_oracle_full_state(
        event,
        previous_state_version=previous_state_version,
    )
    assert receipt["oracle_full_state"]["state_version"] == previous_state_version + 1


@pytest.mark.parametrize("previous_state_version", (0, 3))
def test_cancellation_materializes_to_exact_native_full_state(previous_state_version) -> None:
    event, receipt = cancellation_pair(previous_state_version=previous_state_version)
    materialized = materialize_cancellation_receipt(
        receipt,
        event,
        physically_true_objects=("cream_cheese_1",),
    )
    assert materialized == build_oracle_cancellation_state(
        event,
        previous_state_version=previous_state_version,
    )


@pytest.mark.parametrize(
    "corruption",
    ("provider", "event", "hash", "mode", "grounding", "lineage"),
)
def test_replacement_materializer_rejects_corrupted_receipts(corruption: str) -> None:
    event, original = replacement_pair()
    receipt = copy.deepcopy(original)
    if corruption == "provider":
        receipt["provider_called"] = True
    elif corruption == "event":
        receipt["patch"]["event_id"] = "wrong-event"
    elif corruption == "hash":
        receipt["transition"]["after_hash"] = "0" * 64
    else:
        replacement_id = receipt["patch"]["replacement_id"]
        slot = next(item for item in receipt["state_after"]["slots"] if item["slot_id"] == replacement_id)
        if corruption == "mode":
            slot["mode"] = "expired"
        elif corruption == "grounding":
            slot["content"]["arguments"][1] = "table"
        elif corruption == "lineage":
            slot["lineage"] = [replacement_id]
    with pytest.raises(FullStateValidationError):
        materialize_replacement_receipt(
            receipt,
            event,
            physically_true_objects=("cream_cheese_1",),
        )


@pytest.mark.parametrize("corruption", ("provider", "event", "hash", "mode", "grounding"))
def test_cancellation_materializer_rejects_corrupted_receipts(corruption: str) -> None:
    event, original = cancellation_pair()
    receipt = copy.deepcopy(original)
    if corruption == "provider":
        receipt["provider_called"] = True
    elif corruption == "event":
        receipt["patch"]["event_id"] = "wrong-event"
    elif corruption == "hash":
        receipt["transition"]["after_hash"] = "0" * 64
    else:
        pending_id = receipt["patch"]["target_id"]
        slot = next(item for item in receipt["state_after"]["slots"] if item["slot_id"] == pending_id)
        if corruption == "mode":
            slot["mode"] = "active"
        elif corruption == "grounding":
            slot["content"]["arguments"][1] = "table"
    with pytest.raises(FullStateValidationError):
        materialize_cancellation_receipt(
            receipt,
            event,
            physically_true_objects=("cream_cheese_1",),
        )
