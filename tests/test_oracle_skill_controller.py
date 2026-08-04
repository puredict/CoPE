from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from cope_benchmark.oracle_skill_controller import (
    LiberoOracleSkillController,
    OracleSkillConfig,
)


class FakeState:
    def __init__(self, position):
        self.position = np.asarray(position, dtype=float)

    def get_geom_state(self):
        return {"pos": self.position}


class FakeEnv:
    def __init__(self):
        self.env = self
        self.eef = np.array([0.0, 0.0, 0.70])
        self.object_states_dict = {
            "can": FakeState([0.10, -0.10, 0.48]),
            "basket_region": FakeState([0.0, 0.25, 0.55]),
        }
        self.objects_dict = {"can": object()}
        self.robots = [SimpleNamespace(gripper=object())]
        self.grasped = False
        self.predicate_calls = []

    def step(self, action):
        action = np.asarray(action)
        self.eef += action[:3] * 0.02
        obj = self.object_states_dict["can"]
        if action[6] > 0 and np.linalg.norm(self.eef - obj.position) < 0.04:
            self.grasped = True
        if self.grasped and action[6] > 0:
            obj.position = self.eef + np.array([0.0, 0.0, -0.005])
        if action[6] < 0:
            self.grasped = False
        return {"robot0_eef_pos": self.eef.copy()}, 0.0, False, {}

    def _check_grasp(self, gripper, obj):
        return self.grasped

    def _eval_predicate(self, state):
        self.predicate_calls.append(list(state))
        assert state in (
            ["in", "can", "basket_region"],
            ["on", "can", "basket_region"],
        )
        obj = self.object_states_dict["can"].position
        target = self.object_states_dict["basket_region"].position
        return np.linalg.norm(obj[:2] - target[:2]) < 0.04


class FirstCheckMissFakeEnv(FakeEnv):
    """Inject one false grasp observation without changing the motion model."""

    def __init__(self):
        super().__init__()
        self.grasp_checks = 0

    def _check_grasp(self, gripper, obj):
        self.grasp_checks += 1
        if self.grasp_checks == 1:
            return False
        return super()._check_grasp(gripper, obj)


def test_move_to_scales_cartesian_delta_and_converges():
    env = FakeEnv()
    controller = LiberoOracleSkillController(
        env, {"robot0_eef_pos": env.eef.copy()}
    )
    record = controller.move_to("test", [0.10, -0.10, 0.60], gripper=-1.0)
    assert record.final_error_m is not None
    assert record.final_error_m < controller.config.position_tolerance_m
    assert record.steps > 0


def test_unknown_state_reports_available_symbols():
    env = FakeEnv()
    controller = LiberoOracleSkillController(
        env, {"robot0_eef_pos": env.eef.copy()}
    )
    try:
        controller.position("missing")
    except KeyError as exc:
        assert "basket_region" in str(exc)
        assert "can" in str(exc)
    else:
        raise AssertionError("missing state should raise KeyError")


def test_pick_checkpoint_can_be_safely_returned_to_start():
    env = FakeEnv()
    controller = LiberoOracleSkillController(
        env, {"robot0_eef_pos": env.eef.copy()}
    )
    checkpoint = controller.pick_object("can")
    assert checkpoint.success
    assert checkpoint.grasp_acquired
    assert checkpoint.object_lift_m >= controller.config.minimum_lift_m
    returned = controller.return_held_to_start(checkpoint)
    assert returned.success
    assert returned.released
    assert returned.return_position_error_m <= 0.06


def test_pick_checkpoint_can_resume_into_place():
    env = FakeEnv()
    controller = LiberoOracleSkillController(
        env, {"robot0_eef_pos": env.eef.copy()}
    )
    checkpoint = controller.pick_object("can")
    placed = controller.place_held(checkpoint, "basket_region")
    assert placed.success
    assert placed.target_predicate


def test_explicit_relation_is_forwarded_to_libero_predicate_evaluator():
    env = FakeEnv()
    controller = LiberoOracleSkillController(
        env, {"robot0_eef_pos": env.eef.copy()}
    )
    result = controller.pick_and_place("can", "basket_region", predicate="On")
    assert result.success
    assert env.predicate_calls
    assert all(call == ["on", "can", "basket_region"] for call in env.predicate_calls)


def test_historical_default_relation_remains_in():
    env = FakeEnv()
    controller = LiberoOracleSkillController(
        env, {"robot0_eef_pos": env.eef.copy()}
    )
    result = controller.pick_and_place("can", "basket_region")
    assert result.success
    assert env.predicate_calls
    assert all(call == ["in", "can", "basket_region"] for call in env.predicate_calls)


def test_empty_relation_fails_closed_before_evaluator_call():
    env = FakeEnv()
    controller = LiberoOracleSkillController(
        env, {"robot0_eef_pos": env.eef.copy()}
    )
    try:
        controller.predicate_satisfied("  ", "can", "basket_region")
    except ValueError as exc:
        assert "nonempty" in str(exc)
    else:
        raise AssertionError("empty relation must fail closed")
    assert env.predicate_calls == []


def test_default_grasp_protocol_preserves_single_historical_attempt():
    env = FirstCheckMissFakeEnv()
    controller = LiberoOracleSkillController(
        env, {"robot0_eef_pos": env.eef.copy()}
    )
    result = controller.pick_object("can")
    assert not result.success
    assert result.failure_reason == "grasp_not_acquired"
    assert [phase.phase for phase in result.phases] == [
        "approach_object",
        "descend_to_grasp",
        "close_gripper",
    ]


def test_opt_in_regrasp_recovers_after_failed_center_attempt():
    env = FirstCheckMissFakeEnv()
    config = OracleSkillConfig(
        grasp_attempt_xy_offsets_m=((0.0, 0.0), (0.0, 0.0))
    )
    controller = LiberoOracleSkillController(
        env, {"robot0_eef_pos": env.eef.copy()}, config=config
    )
    result = controller.pick_object("can")
    assert result.success
    assert result.grasp_acquired
    assert "regrasp_1_open_gripper" in [phase.phase for phase in result.phases]
    assert "regrasp_1_close_gripper" in [phase.phase for phase in result.phases]


def test_grasp_offset_protocol_rejects_empty_or_non_finite_values():
    for offsets in ((), ((float("nan"), 0.0),)):
        try:
            OracleSkillConfig(grasp_attempt_xy_offsets_m=offsets)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid grasp attempt offsets must fail closed")
