from __future__ import annotations

import json

import numpy as np
import pytest

from libero_experiment_core import (
    BudgetReport,
    EpisodeStatus,
    ExperimentConfig,
    build_recovery_prompt,
    choose_target_joint,
    extract_episode_status,
    infer_goal_phrase,
    json_safe,
    list_free_joints,
    make_budget_report,
    move_free_joint_xy,
    object_phrase_from_joint,
    refresh_observation_after_sim_change,
    select_target_joint,
)


class FakeModel:
    def __init__(self, names, types):
        self._names = names
        self.njnt = len(names)
        self.jnt_type = np.array(types)
        self.jnt_qposadr = np.arange(0, len(names) * 7, 7)

    def joint_id2name(self, joint_id):
        return self._names[joint_id]

    def joint_name2id(self, name):
        if name not in self._names:
            raise KeyError(name)
        return self._names.index(name)


class FakeData:
    def __init__(self, joint_count):
        self.qpos = np.zeros(joint_count * 7, dtype=float)


class FakeSim:
    def __init__(self, names, types):
        self.model = FakeModel(names, types)
        self.data = FakeData(len(names))
        self.forward_count = 0

    def forward(self):
        self.forward_count += 1


class FakeEnv:
    def __init__(self, names, types):
        self.sim = FakeSim(names, types)

    def step(self, action):
        return {"fallback": True}, 0.0, False, {"action": action}


class ObservationEnv:
    def __init__(self):
        self.sim = FakeSim(["object_joint0"], [0])
        self.called = False
        self.post_processed = False
        self.update_force = None

    def check_success(self):
        return False

    def _post_process(self):
        self.post_processed = True

    def _update_observables(self, force=False):
        self.update_force = force

    def _get_observations(self, force_update=False):
        self.called = force_update
        return {"fresh": force_update}


def test_prompt_builder_matches_existing_semantics() -> None:
    prompt, state = build_recovery_prompt(
        "structured_relocalize_prompt",
        "put the black bowl on the plate",
        "akita_black_bowl_1_joint0",
    )
    assert prompt == "relocalize the black bowl at its current position, then complete the original task: put the black bowl on the plate"
    assert state["affected_object"] == "black bowl"
    assert state["has_selective_recovery_state"] is True

    prompt, state = build_recovery_prompt(
        "stage_backtrack_subgoal",
        "put the black bowl on the plate",
        "akita_black_bowl_1_joint0",
    )
    assert prompt == "pick up the black bowl from its current position and place it on the plate"
    assert state["goal"] == "the plate"


def test_object_and_goal_helpers() -> None:
    assert object_phrase_from_joint("akita_black_bowl_1_joint0") == "black bowl"
    assert infer_goal_phrase("move the cup onto the plate") == "the plate"
    assert infer_goal_phrase("move the cup") == "the target location"


def test_choose_target_joint_scores_task_tokens() -> None:
    env = FakeEnv(["plate_1_joint0", "akita_black_bowl_1_joint0", "robot_joint0"], [0, 0, 0])
    assert choose_target_joint(env, "put the black bowl on the plate") == "akita_black_bowl_1_joint0"
    selection = select_target_joint(env, "put the black bowl on the plate")
    assert selection.selected_joint == "akita_black_bowl_1_joint0"
    assert selection.reason == "unique_highest_token_overlap_score_2"
    joints = list_free_joints(env, "put the black bowl on the plate")
    assert joints[0]["name"] == "akita_black_bowl_1_joint0"
    assert joints[0]["matched_task_tokens"] == ["black", "bowl"]


def test_choose_target_joint_rejects_zero_score_auto() -> None:
    env = FakeEnv(["plate_1_joint0", "cup_1_joint0"], [0, 0])
    with pytest.raises(ValueError, match="scored 0"):
        choose_target_joint(env, "open the drawer")


def test_choose_target_joint_rejects_tied_auto() -> None:
    env = FakeEnv(["red_mug_joint0", "blue_mug_joint0"], [0, 0])
    with pytest.raises(ValueError, match="tie"):
        choose_target_joint(env, "pick up the mug")


def test_explicit_target_joint_overrides_auto_ambiguity() -> None:
    env = FakeEnv(["red_mug_joint0", "blue_mug_joint0"], [0, 0])
    selection = select_target_joint(env, "pick up the mug", requested="blue_mug_joint0")
    assert selection.selected_joint == "blue_mug_joint0"
    assert selection.reason == "explicit_target_joint"


def test_choose_target_joint_errors_without_candidates() -> None:
    env = FakeEnv(["robot_joint0", "gripper_joint0"], [0, 0])
    with pytest.raises(ValueError, match="No movable"):
        choose_target_joint(env, "anything")


def test_move_free_joint_xy_validates_and_moves() -> None:
    env = FakeEnv(["object_joint0"], [0])
    record = move_free_joint_xy(env, "object_joint0", 0.1, -0.2)
    assert record["before_qpos"][0] == 0.0
    assert record["after_qpos"][0] == pytest.approx(0.1)
    assert record["after_qpos"][1] == pytest.approx(-0.2)
    assert env.sim.forward_count == 1


def test_move_free_joint_rejects_non_free_joint() -> None:
    env = FakeEnv(["hinge_joint0"], [1])
    with pytest.raises(ValueError, match="not a free joint"):
        move_free_joint_xy(env, "hinge_joint0", 0.1, 0.0)


def test_refresh_observation_uses_force_update() -> None:
    env = ObservationEnv()
    obs, meta = refresh_observation_after_sim_change(env, object())
    assert obs == {"fresh": True}
    assert meta["consumed_noop_env_step"] is False
    assert "force_update=True" in meta["method"]
    assert env.post_processed is True
    assert env.update_force is True
    assert "sim.forward" in meta["operations"]


def test_extract_episode_status_distinguishes_terminal_reasons() -> None:
    success = extract_episode_status(1.0, True, {}, 3, 10)
    assert isinstance(success, EpisodeStatus)
    assert success.status == "success"
    assert success.success is True

    timeout = extract_episode_status(0.0, False, {}, 10, 10)
    assert timeout.status == "timeout"

    stopped = extract_episode_status(0.0, False, {"stopped_by_verifier": True}, 4, 10)
    assert stopped.status == "stopped"

    error = extract_episode_status(0.0, False, {"simulator_error": True}, 4, 10)
    assert error.status == "simulator_error"

    failure = extract_episode_status(0.0, False, {}, 4, 10)
    assert failure.status == "failure"


def test_make_budget_report_counts_original_policy_budget() -> None:
    budget = make_budget_report(
        policy_step_budget=10,
        warmup_simulator_steps=2,
        policy_inference_steps=12,
        extra_environment_steps=1,
        pre_disturbance_policy_steps=5,
        reset_count=1,
        rollback_count=0,
        success=True,
    )
    assert isinstance(budget, BudgetReport)
    assert budget.environment_control_steps == 15
    assert budget.recovery_policy_steps == 7
    assert budget.success_within_original_budget is False


def test_json_safe_removes_numpy_values() -> None:
    payload = {"x": np.float32(1.5), "arr": np.array([1, 2]), "nested": [np.int64(3)]}
    safe = json_safe(payload)
    assert safe == {"x": pytest.approx(1.5), "arr": [1, 2], "nested": [3]}
    json.dumps(safe)


def test_clean_config_disables_auto_disturbance() -> None:
    cfg = ExperimentConfig(checkpoint="mock", mode="clean", enable_auto_disturbance=True)
    assert cfg.enable_auto_disturbance is False
