from __future__ import annotations

import copy

import pytest

from cope.libero_predicate_validator import (
    LiberoPredicateRevalidationValidator,
    PredicateSnapshotError,
    build_live_libero_predicate_snapshot,
    build_predicate_snapshot,
)
from cope.schema import ConstraintSlot
from cope.types import stable_hash


COMMIT = "2fcfb32ec9c3a4b80642ddea494d9e32c85eb11b"
OBS_HASH = "a" * 64
SIM_HASH = "b" * 64
EVENT = {"event_id": "semantic-event-1"}


def slot(object_name: str = "cream_cheese_1", *, atomic: bool = True) -> ConstraintSlot:
    content = (
        {"predicate": "in", "arguments": [object_name, "basket_1_contain_region"]}
        if atomic
        else {"instruction": "put both objects in the basket"}
    )
    return ConstraintSlot(
        slot_id=f"goal:{object_name}",
        constraint_type="task_goal",
        content=content,
        source="task",
        mode="suspended",
        priority=100,
        created_event_id="genesis",
        last_updated_event_id="suspend-event",
        lineage=(f"goal:{object_name}",),
    )


def packet(*, test_only: bool = True) -> dict:
    return build_predicate_snapshot(
        task_suite="libero_10",
        task_id=1,
        event_id=EVENT["event_id"],
        policy_step=280,
        observation_sha256=OBS_HASH,
        simulator_state_sha256=SIM_HASH,
        producer_commit=COMMIT,
        predicates=(
            ("in", ("cream_cheese_1", "basket_1_contain_region"), True),
            ("in", ("butter_1", "basket_1_contain_region"), False),
        ),
        test_only=test_only,
        source_kind="unit_test" if test_only else "live_libero_eval_predicate",
    )


def evidence(value: dict) -> dict:
    return {
        "provider_evidence": {"claim": "ignored"},
        "observation": {"sha256": OBS_HASH, "predicate_snapshot": value},
        "event": EVENT,
    }


def rehash(value: dict) -> None:
    unsigned = dict(value)
    unsigned.pop("snapshot_sha256", None)
    value["snapshot_sha256"] = stable_hash(unsigned)


def validator(*, allow_test_packets: bool) -> LiberoPredicateRevalidationValidator:
    return LiberoPredicateRevalidationValidator(
        {
            "predicate_snapshot": {
                "allow_test_packets": allow_test_packets,
                "task_suite": "libero_10",
                "task_id": 1,
                "producer_commit": COMMIT,
            }
        }
    )


def test_test_mode_metadata_is_fake_and_production_metadata_is_not() -> None:
    assert validator(allow_test_packets=True).metadata["is_fake"] is True
    assert validator(allow_test_packets=False).metadata["is_fake"] is False
    assert validator(allow_test_packets=False).metadata["validator_commit"] == COMMIT


def test_atomic_predicates_return_recorded_values_and_ignore_provider_claims() -> None:
    checked = validator(allow_test_packets=True)
    assert checked(slot("cream_cheese_1"), evidence(packet())) is True
    assert checked(slot("butter_1"), evidence(packet())) is False


@pytest.mark.parametrize(
    "corruption",
    ("packet_hash", "event", "observation", "simulator_hash", "duplicate", "unsupported_slot"),
)
def test_validator_rejects_corrupt_or_unsupported_inputs(corruption: str) -> None:
    value = copy.deepcopy(packet())
    candidate_slot = slot()
    if corruption == "packet_hash":
        value["snapshot_sha256"] = "0" * 64
    elif corruption == "event":
        value["event_id"] = "wrong-event"
        rehash(value)
    elif corruption == "observation":
        value["observation_sha256"] = "c" * 64
        rehash(value)
    elif corruption == "simulator_hash":
        value["simulator_state_sha256"] = "not-a-hash"
        rehash(value)
    elif corruption == "duplicate":
        value["predicates"].append(copy.deepcopy(value["predicates"][0]))
        rehash(value)
    elif corruption == "unsupported_slot":
        candidate_slot = slot(atomic=False)
    with pytest.raises(PredicateSnapshotError):
        validator(allow_test_packets=True)(candidate_slot, evidence(value))


def test_production_rejects_test_packet() -> None:
    with pytest.raises(PredicateSnapshotError, match="test-only"):
        validator(allow_test_packets=False)(slot(), evidence(packet(test_only=True)))


class FakeBaseEnv:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def _eval_predicate(self, state):
        key = tuple(str(item) for item in state)
        self.calls.append(key)
        return key[1] == "cream_cheese_1"


class FakeWrapper:
    def __init__(self) -> None:
        self.env = FakeBaseEnv()


def test_live_builder_calls_registered_libero_task1_predicates() -> None:
    env = FakeWrapper()
    value = build_live_libero_predicate_snapshot(
        env,
        task_suite="libero_10",
        task_id=1,
        event_id=EVENT["event_id"],
        policy_step=280,
        observation_sha256=OBS_HASH,
        simulator_state_sha256=SIM_HASH,
        producer_commit=COMMIT,
        test_only=True,
    )
    assert env.env.calls == [
        ("in", "cream_cheese_1", "basket_1_contain_region"),
        ("in", "butter_1", "basket_1_contain_region"),
    ]
    assert [item["value"] for item in value["predicates"]] == [False, True]

