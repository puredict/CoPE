"""Semantic tests for the CoPE constraint-state layer (memo v0.3, §3-§4).

These test the *rules*, not the outcomes: an operator that is allowed to
silently do the wrong thing would still produce a passing benchmark number.
"""
from __future__ import annotations

import pytest

from cope.constraint_slot import (
    ConstraintSlot, Priority, RevalidationResult, SlotMode, SlotSource,
)
from cope.constraint_state import ConstraintState
from cope.naming import canonical_id
from cope.patch import FIRST_PAPER_SUBSET, OpType, Patch, PatchOp
from cope.patch_operators import PatchApplicationError, apply_op, apply_patch
from cope.patch_validator import validate_patch, validate_state
from cope.state_store import StateStore

WORLD = {"unavailable_targets": []}


def _state(*slots):
    return ConstraintState().put_many(slots)


def _goal(sid="g1", **kw):
    return ConstraintSlot(id=sid, grounding=f"place_{sid}", **kw)


# --------------------------------------------------------------- schema
def test_first_paper_subset_is_the_seven_memo_operators():
    assert [o.value for o in FIRST_PAPER_SUBSET] == [
        "Insert", "Suspend", "Override", "Inherit", "Expire", "Revalidate",
        "Restore"]


def test_slot_carries_all_nine_schema_fields():
    s = _goal()
    for f in ("id", "grounding", "mode", "priority", "source", "validity",
              "restore", "lineage", "history"):
        assert hasattr(s, f), f


def test_only_active_slots_participate():
    for mode, expect in [(SlotMode.ACTIVE, True), (SlotMode.SUSPENDED, False),
                         (SlotMode.OVERRIDDEN, False), (SlotMode.EXPIRED, False)]:
        assert _goal(mode=mode).participates is expect


# --------------------------------------------------------------- Revalidate
def test_revalidate_never_changes_mode():
    """Memo §4: Revalidate returns OK/DEGRADED/FAIL and has no side effect."""
    for mode in (SlotMode.ACTIVE, SlotMode.SUSPENDED, SlotMode.OVERRIDDEN):
        st = _state(_goal(mode=mode))
        st2, rec = apply_op(st, PatchOp(OpType.REVALIDATE, target_id="g1"),
                            "p", WORLD)
        assert st2.get("g1").mode is mode
        assert rec["mode_unchanged"] is True


def test_revalidate_distinguishes_ok_degraded_fail():
    ok = _goal()
    assert ok.revalidate(WORLD) is RevalidationResult.OK
    degraded = _goal(mode=SlotMode.SUSPENDED, restore=lambda w: False)
    assert degraded.revalidate(WORLD) is RevalidationResult.DEGRADED
    failed = _goal(validity=lambda w: False)
    assert failed.revalidate(WORLD) is RevalidationResult.FAIL
    assert _goal(mode=SlotMode.EXPIRED).revalidate(WORLD) is RevalidationResult.FAIL


# --------------------------------------------------------------- Expire
def test_expired_is_a_soft_delete_that_is_never_restorable():
    st = _state(_goal(mode=SlotMode.EXPIRED))
    st2, rec = apply_op(st, PatchOp(OpType.RESTORE, target_id="g1"), "p", WORLD)
    assert rec["applied"] is False
    assert "expired" in rec["refused"]
    assert st2.get("g1") is not None       # the record survives for the audit


def test_expire_preserves_the_slot_and_its_history():
    st = _state(_goal())
    st2, _ = apply_op(st, PatchOp(OpType.EXPIRE, target_id="g1", reason="user"),
                      "p", WORLD)
    s = st2.get("g1")
    assert s.mode is SlotMode.EXPIRED
    assert s.history[-1].operation == "Expire"
    assert s.history[-1].detail == "user"


# --------------------------------------------------------------- Suspend/Restore
def test_suspend_snapshots_priority_and_records_a_restore_path():
    st = _state(_goal(priority=Priority.HARD))
    st2, _ = apply_op(st, PatchOp(OpType.SUSPEND, target_id="g1",
                                  args={"restore": lambda w: True}), "p", WORLD)
    s = st2.get("g1")
    assert s.mode is SlotMode.SUSPENDED
    assert s.priority_snapshot is Priority.HARD
    assert s.restore is not None


def test_restore_is_refused_when_revalidation_is_not_ok():
    st = _state(_goal(mode=SlotMode.SUSPENDED, restore=lambda w: False))
    st2, rec = apply_op(st, PatchOp(OpType.RESTORE, target_id="g1"), "p", WORLD)
    assert rec["applied"] is False
    assert rec["result"] == "DEGRADED"
    assert st2.get("g1").mode is SlotMode.SUSPENDED


def test_restore_returns_the_snapshotted_priority():
    st = _state(_goal(priority=Priority.HARD))
    st, _ = apply_op(st, PatchOp(OpType.SUSPEND, target_id="g1"), "p", WORLD)
    st, _ = apply_op(st, PatchOp(OpType.DEMOTE, target_id="g1",
                                 args={"priority": Priority.SOFT}), "p", WORLD)
    st, rec = apply_op(st, PatchOp(OpType.RESTORE, target_id="g1"), "p", WORLD)
    assert rec["applied"] is True
    assert st.get("g1").priority is Priority.HARD


def test_restore_not_preceded_by_revalidate_is_a_validation_violation():
    st = _state(_goal(mode=SlotMode.SUSPENDED))
    patch = Patch(patch_id="p", ops=(PatchOp(OpType.RESTORE, target_id="g1"),))
    rep = validate_patch(st, patch)
    assert not rep.ok
    assert any("revalid" in v.lower() for v in rep.violations)


# --------------------------------------------------------------- Override
def test_override_creates_a_symmetric_acyclic_edge():
    st = _state(_goal())
    st2, _ = apply_op(st, PatchOp(OpType.OVERRIDE, target_id="g1",
                                  new_slot_id="g1@B"), "p", WORLD)
    old, cover = st2.get("g1"), st2.get("g1@B")
    assert old.mode is SlotMode.OVERRIDDEN
    assert old.lineage.overridden_by == "g1@B"
    assert "g1" in cover.lineage.overrides
    assert st2.graph_consistent()


def test_repeated_override_keeps_the_graph_consistent():
    st = _state(_goal())
    st, _ = apply_op(st, PatchOp(OpType.OVERRIDE, target_id="g1",
                                 new_slot_id="g1@B"), "p1", WORLD)
    st, _ = apply_op(st, PatchOp(OpType.OVERRIDE, target_id="g1@B",
                                 new_slot_id="g1@C"), "p2", WORLD)
    assert st.graph_consistent()
    assert [s.id for s in st.active()] == ["g1@C"]


# --------------------------------------------------------------- Inherit
def test_inherit_leaves_the_slot_active_and_records_the_inheritance():
    st = _state(_goal())
    st2, _ = apply_op(st, PatchOp(OpType.INHERIT, target_id="g1",
                                  args={"patch_index": 3}), "p", WORLD)
    s = st2.get("g1")
    assert s.mode is SlotMode.ACTIVE
    assert 3 in s.lineage.inherited_at
    assert s.history[-1].operation == "Inherit"


def test_inherit_refuses_a_non_active_slot():
    st = _state(_goal(mode=SlotMode.SUSPENDED))
    with pytest.raises(PatchApplicationError):
        apply_op(st, PatchOp(OpType.INHERIT, target_id="g1"), "p", WORLD)


# --------------------------------------------------------------- invariants
def test_slots_are_never_deleted():
    store = StateStore()
    store.seed([_goal("g1"), _goal("g2")])
    ok, _ = store.apply_patch(
        Patch(patch_id="p", ops=(PatchOp(OpType.EXPIRE, target_id="g1"),)), WORLD)
    assert ok
    assert set(store.state.ids()) == {"g1", "g2"}


def test_history_is_monotonic_per_slot():
    store = StateStore()
    store.seed([_goal("g1")])
    for i in range(3):
        store.apply_patch(Patch(patch_id=f"p{i}", ops=(
            PatchOp(OpType.REVALIDATE, target_id="g1"),)), WORLD)
    assert store.history_monotonic()
    assert [e.seq for e in store.state.get("g1").history] == [1, 2, 3]


def test_expired_is_terminal_in_the_transition_table():
    st = _state(_goal(mode=SlotMode.EXPIRED))
    for op in (OpType.SUSPEND, OpType.RESTORE, OpType.INHERIT):
        patch = Patch(patch_id="p", ops=(PatchOp(op, target_id="g1"),))
        rep = validate_patch(st, patch)
        applied_ok = rep.ok
        if applied_ok:
            # if the pre-check lets it through, the operator must still refuse
            try:
                st2, rec = apply_op(st, PatchOp(op, target_id="g1"), "p", WORLD)
                assert rec.get("applied") is False
            except PatchApplicationError:
                pass


def test_canonical_id_strips_regeneration_and_override_decorations():
    assert canonical_id("g_butter") == "g_butter"
    assert canonical_id("g_butter@basket_A") == "g_butter"
    assert canonical_id("g_butter#r1") == "g_butter"
    assert canonical_id("g_butter#r1@basket_A") == "g_butter"
