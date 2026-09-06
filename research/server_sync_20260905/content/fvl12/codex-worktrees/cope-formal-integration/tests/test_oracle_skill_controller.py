from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from cope_benchmark.oracle_skill_controller import LiberoOracleSkillController


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
        assert state == ["in", "can", "basket_region"]
        obj = self.object_states_dict["can"].position
        target = self.object_states_dict["basket_region"].position
        return np.linalg.norm(obj[:2] - target[:2]) < 0.04


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
