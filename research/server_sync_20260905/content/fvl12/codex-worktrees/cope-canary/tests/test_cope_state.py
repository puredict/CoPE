from __future__ import annotations

from pathlib import Path

import pytest

from cope_state import (
    ConstraintSlot,
    ConstraintState,
    PatchApplicationError,
    apply_patch,
    build_policy_prompt_from_constraint_state,
    expire,
    inherit,
    initial_libero_pick_place_state,
    insert,
    make_object_displacement_patch,
    plan_guarded_recovery,
    revalidate,
    restore,
    suspend,
    validate_state_invariants,
)


def test_patch_application_preserves_identity_and_history() -> None:
    state = ConstraintState()
    state = apply_patch(
        state,
        [
            insert(ConstraintSlot(id="avoid_spill", priority=90, source="safety")),
            suspend("avoid_spill", reason="temporary override"),
            revalidate("avoid_spill", "OK"),
            restore("avoid_spill"),
        ],
    )

    assert state.slots["avoid_spill"].id == "avoid_spill"
    assert state.slots["avoid_spill"].mode == "active"
    assert state.revision == 4
    assert [event["revision"] for event in state.history] == [1, 2, 3, 4]
    assert [event["op"] for event in state.slots["avoid_spill"].history] == [
        "Insert",
        "Suspend",
        "Revalidate",
        "Restore",
    ]
    assert validate_state_invariants(state) == []


def test_restore_requires_guarded_revalidation() -> None:
    state = apply_patch(ConstraintState(), [insert(ConstraintSlot(id="pour_rate")), suspend("pour_rate")])

    with pytest.raises(PatchApplicationError, match="prior OK/DEGRADED Revalidate"):
        apply_patch(state, [restore("pour_rate")])

    failed = apply_patch(state, [revalidate("pour_rate", "FAIL")])
    with pytest.raises(PatchApplicationError, match="prior OK/DEGRADED Revalidate"):
        apply_patch(failed, [restore("pour_rate")])


def test_guarded_recovery_expires_failed_slots_and_restores_ok_slots() -> None:
    state = apply_patch(
        ConstraintState(),
        [
            insert(ConstraintSlot(id="normal_pour", priority=50)),
            insert(ConstraintSlot(id="spout_alignment", priority=40)),
            suspend("normal_pour"),
            suspend("spout_alignment"),
        ],
    )
    ops = plan_guarded_recovery(
        state,
        {
            "normal_pour": "OK",
            "spout_alignment": "FAIL",
        },
    )
    recovered = apply_patch(state, ops)

    assert recovered.slots["normal_pour"].mode == "active"
    assert recovered.slots["spout_alignment"].mode == "expired"
    assert validate_state_invariants(recovered) == []


def test_object_displacement_patch_expires_old_pose_and_preserves_unaffected_slots() -> None:
    state = initial_libero_pick_place_state(
        task_description="pick up the black bowl and place it on the plate",
        affected_object="black bowl",
        target_joint="akita_black_bowl_1_joint0",
        goal="plate",
    )
    patch = make_object_displacement_patch(
        affected_object="black bowl",
        target_joint="akita_black_bowl_1_joint0",
        before_qpos=[0.0, 0.1, 0.9, 1, 0, 0, 0],
        after_qpos=[0.1, 0.15, 0.9, 1, 0, 0, 0],
        goal="plate",
    )
    next_state = apply_patch(state, patch)

    assert next_state.slots["target_pose:black_bowl"].mode == "expired"
    assert next_state.slots["target_pose_current:black_bowl"].mode == "active"
    assert next_state.slots["grasp_validity:black_bowl"].mode == "suspended"
    assert next_state.slots["task_goal:pick_place"].mode == "active"
    assert next_state.slots["goal_pose:plate"].mode == "active"
    assert [event["op"] for event in next_state.history] == [
        "Revalidate",
        "Expire",
        "Insert",
        "Suspend",
        "Inherit",
        "Inherit",
    ]
    assert validate_state_invariants(next_state) == []


def test_expired_slots_cannot_be_inherited_or_restored() -> None:
    state = apply_patch(ConstraintState(), [insert(ConstraintSlot(id="cup_pose")), expire("cup_pose")])

    with pytest.raises(PatchApplicationError, match="cannot inherit expired slot"):
        apply_patch(state, [inherit("cup_pose")])
    with pytest.raises(PatchApplicationError, match="cannot restore expired slot"):
        apply_patch(state, [restore("cup_pose")])


def test_policy_prompt_adapter_uses_applied_patch_state_without_claiming_detector_autonomy() -> None:
    state = initial_libero_pick_place_state(
        task_description="pick up the black bowl and place it on the plate",
        affected_object="black bowl",
        target_joint="akita_black_bowl_1_joint0",
        goal="plate",
    )
    patched = apply_patch(
        state,
        make_object_displacement_patch(
            affected_object="black bowl",
            target_joint="akita_black_bowl_1_joint0",
            before_qpos=[0.0, 0.1, 0.9, 1, 0, 0, 0],
            after_qpos=[0.1, 0.15, 0.9, 1, 0, 0, 0],
            goal="plate",
        ),
    )

    prompt, metadata = build_policy_prompt_from_constraint_state(
        original_task="pick up the black bowl and place it on the plate",
        state=patched,
        affected_object="black bowl",
    )

    assert "relocalize the black bowl at its current position" in prompt
    assert "regrasp if needed" in prompt
    assert metadata["adapter"] == "cope_constraint_state_prompt_v0"
    assert metadata["decision"] == "relocalize_regrasp_then_continue"
    assert metadata["active_current_pose_slot"] == "target_pose_current:black_bowl"
    assert metadata["expired_old_pose_slot"] == "target_pose:black_bowl"
    assert metadata["suspended_grasp_slot"] == "grasp_validity:black_bowl"


def test_cope_state_does_not_reimplement_existing_correctness_helpers() -> None:
    source = Path(__file__).resolve().parents[1].joinpath("cope_state.py").read_text(encoding="utf-8")
    forbidden_names = [
        "extract_episode_status",
        "refresh_observation_after_sim_change",
        "make_budget_report",
        "select_target_joint",
        "choose_target_joint",
    ]
    for name in forbidden_names:
        assert name not in source
