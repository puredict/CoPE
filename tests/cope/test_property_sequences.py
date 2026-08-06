from __future__ import annotations

import json
import random
from dataclasses import replace

from cope import (
    ConstraintMode,
    ConstraintState,
    Demote,
    Expire,
    Insert,
    PatchContext,
    Restore,
    Suspend,
    apply_patch,
    canonical_state_hash,
    deserialize_state,
    replay,
    revalidate_slot,
    serialize_state,
    validate_state,
)
from cope.errors import (
    DUPLICATE_SLOT_ID,
    EXPIRED_RESTORE,
    HASH_MISMATCH,
    PRIORITY_VIOLATION,
    SLOT_NOT_FOUND,
    VALIDATION_NOT_FOUND,
)

from conftest import apply_ok, make_patch, make_slot


PROPERTY_SEED = 20_260_724
PROPERTY_SEQUENCE_COUNT = 10_000


def _true_guard(slot, evidence) -> bool:
    return evidence["object_id"] == slot.content["object_id"]


def test_10000_seeded_operation_patch_sequences(tmp_path) -> None:
    rng = random.Random(PROPERTY_SEED)
    failure_path = tmp_path / "cope_property_failure.json"
    category_counts = {name: 0 for name in (
        "legal_restore",
        "missing_slot",
        "duplicate_insert",
        "blind_restore",
        "expired_restore",
        "priority_violation",
        "atomic_middle_failure",
        "corrupted_hash",
        "serialization_replay",
        "lineage_successor",
        "override_cycle",
    )}

    for sequence_index in range(PROPERTY_SEQUENCE_COUNT):
        category = rng.randrange(11)
        label = list(category_counts)[category]
        category_counts[label] += 1
        state_id = f"property-{sequence_index}"
        initial = ConstraintState.empty(state_id)
        root = make_slot(
            "root",
            "event-1",
            content={"object_id": f"cup-{rng.randrange(7)}", "relation": "aligned"},
            priority=rng.randrange(20, 81),
        )
        state = apply_ok(initial, 1, [Insert(f"op-insert-{sequence_index}", root)])
        trace = {"seed": PROPERTY_SEED, "sequence_index": sequence_index, "category": label}
        try:
            if category == 0:
                state = apply_ok(state, 2, [Suspend(f"op-suspend-{sequence_index}", "root", "temporary")])
                guarded = revalidate_slot(
                    state,
                    "root",
                    {"object_id": root.content["object_id"], "observation_id": sequence_index},
                    _true_guard,
                )
                state = apply_ok(state, 3, [guarded.operation])
                state = apply_ok(
                    state,
                    4,
                    [Restore(f"op-restore-{sequence_index}", "root", guarded.validation_id, "passed")],
                )
                assert state.get_slot("root").mode is ConstraintMode.ACTIVE
                assert validate_state(state).valid
            elif category == 1:
                result = apply_patch(
                    state,
                    make_patch(
                        state,
                        2,
                        [Suspend(f"op-missing-{sequence_index}", "absent", "invalid")],
                    ),
                    PatchContext.trusted(),
                )
                assert not result.accepted and result.rejection_code == SLOT_NOT_FOUND
            elif category == 2:
                duplicate = make_slot("root", "event-2", content={"object_id": "duplicate"})
                result = apply_patch(
                    state,
                    make_patch(state, 2, [Insert(f"op-duplicate-{sequence_index}", duplicate)]),
                    PatchContext.trusted(),
                )
                assert not result.accepted and result.rejection_code == DUPLICATE_SLOT_ID
            elif category == 3:
                state = apply_ok(state, 2, [Suspend(f"op-suspend-{sequence_index}", "root", "temporary")])
                result = apply_patch(
                    state,
                    make_patch(
                        state,
                        3,
                        [Restore(f"op-blind-{sequence_index}", "root", "val-missing", "blind")],
                    ),
                    PatchContext.trusted(),
                )
                assert not result.accepted and result.rejection_code == VALIDATION_NOT_FOUND
            elif category == 4:
                state = apply_ok(state, 2, [Expire(f"op-expire-{sequence_index}", "root", "moved")])
                result = apply_patch(
                    state,
                    make_patch(
                        state,
                        3,
                        [Restore(f"op-restore-{sequence_index}", "root", "val-any", "illegal")],
                    ),
                    PatchContext.trusted(),
                )
                assert not result.accepted and result.rejection_code == EXPIRED_RESTORE
            elif category == 5:
                context = PatchContext(
                    actor="weak-planner",
                    authority_priority=max(0, root.priority - 1),
                    authorized_sources=("task",),
                )
                result = apply_patch(
                    state,
                    make_patch(
                        state,
                        2,
                        [Suspend(f"op-weak-{sequence_index}", "root", "insufficient authority")],
                    ),
                    context,
                )
                assert not result.accepted and result.rejection_code == PRIORITY_VIOLATION
            elif category == 6:
                before = serialize_state(state)
                temporary = make_slot(f"temporary-{sequence_index}", "event-2")
                result = apply_patch(
                    state,
                    make_patch(
                        state,
                        2,
                        [
                            Insert(f"op-temp-{sequence_index}", temporary),
                            Suspend(f"op-fail-{sequence_index}", "absent", "middle failure"),
                        ],
                    ),
                    PatchContext.trusted(),
                )
                assert not result.accepted and result.rejection_code == SLOT_NOT_FOUND
                assert serialize_state(result.state) == before
            elif category == 7:
                tampered_slot = replace(state.get_slot("root"), priority=min(1000, root.priority + 1))
                tampered = replace(state, slots=(tampered_slot,))
                result = apply_patch(
                    tampered,
                    make_patch(
                        tampered,
                        2,
                        [Suspend(f"op-corrupt-{sequence_index}", "root", "must reject")],
                    ),
                    PatchContext.trusted(),
                )
                assert not result.accepted and result.rejection_code == HASH_MISMATCH
            elif category == 8:
                if root.priority > 0:
                    state = apply_ok(
                        state,
                        2,
                        [Demote(f"op-demote-{sequence_index}", "root", root.priority - 1, "lower")],
                    )
                payload = serialize_state(state)
                round_trip = deserialize_state(json.loads(json.dumps(payload)))
                replayed = replay(initial, state.patch_history)
                assert serialize_state(round_trip) == payload
                assert serialize_state(replayed) == payload
            elif category == 9:
                successor = make_slot(
                    "root-v2",
                    "event-2",
                    content={"object_id": root.content["object_id"], "relation": "realigned"},
                    parent=root,
                )
                state = apply_ok(
                    state,
                    2,
                    [
                        Expire(f"op-expire-{sequence_index}", "root", "moved"),
                        Insert(f"op-successor-{sequence_index}", successor),
                    ],
                )
                assert state.get_slot("root").mode is ConstraintMode.EXPIRED
                assert state.get_slot("root-v2").lineage == ("root", "root-v2")
                assert validate_state(state).valid
            else:
                other = make_slot(f"other-{sequence_index}", "event-2")
                state = apply_ok(
                    state,
                    2,
                    [Insert(f"op-other-{sequence_index}", other)],
                )
                root_bad = replace(state.get_slot("root"), overrides_slot_ids=(other.slot_id,))
                other_bad = replace(other, overrides_slot_ids=("root",))
                provisional = replace(state, slots=(root_bad, other_bad), state_hash="pending")
                corrupted = replace(provisional, state_hash=canonical_state_hash(provisional))
                report = validate_state(corrupted)
                assert not report.valid
                assert "OVERRIDE_CYCLE" in {error.code for error in report.errors}
        except Exception:
            failure_path.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            raise

    assert sum(category_counts.values()) == PROPERTY_SEQUENCE_COUNT
    assert all(count > 800 for count in category_counts.values()), category_counts
