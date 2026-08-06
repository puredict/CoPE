from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np

from cope_benchmark.oracle_safety_telemetry import OracleSafetyTelemetry
from cope_benchmark.oracle_skill_controller import LiberoOracleSkillController


class FakeModel:
    def body_id2name(self, index):
        return ("world", "can")[index]

    def geom_id2name(self, index):
        return ("table", "can_geom")[index]


class FakeTelemetryEnv:
    def __init__(self):
        contact = SimpleNamespace(geom1=0, geom2=1)
        data = SimpleNamespace(
            cfrc_ext=np.array(
                [[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                 [0.0, 0.0, 2.0, 3.0, 4.0, 0.0]],
                dtype=float,
            ),
            ncon=1,
            contact=[contact],
        )
        self.sim = SimpleNamespace(model=FakeModel(), data=data)
        self.control_timestep = 0.05
        self.env = self


def test_telemetry_records_post_event_force_contacts_actions_and_displacement():
    env = FakeTelemetryEnv()
    telemetry = OracleSafetyTelemetry(env)
    telemetry.begin(
        event_step=10,
        object_positions={"done": [0.0, 0.0, 0.0], "idle": [1.0, 0.0, 0.0]},
    )
    telemetry.record(np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0]), 11)
    env.sim.data.ncon = 0
    env.sim.data.cfrc_ext[1, 3:] = [0.0, 0.0, 2.0]
    telemetry.record(np.zeros(7), 12)
    result = telemetry.summarize(
        final_object_positions={
            "done": [0.0, 0.003, 0.004],
            "idle": [1.0, 0.0, 0.0],
        },
        final_step=12,
    )

    assert result["post_event_steps"] == 2
    assert result["peak_external_force_proxy_n"] == 5.0
    assert result["peak_external_force_body"] == "can"
    assert result["peak_external_torque_proxy_nm"] == 2.0
    assert result["contact_active_steps"] == 1
    assert result["max_simultaneous_contacts"] == 1
    assert result["translation_saturation_steps"] == 1
    assert len(result["post_event_action_sha256"]) == 64
    pairs = json.loads(result["contact_pair_step_counts_json"])
    assert pairs == {"can_geom <-> table": 1}
    displacements = json.loads(result["object_displacements_m_json"])
    assert displacements["done"] == 0.005
    assert displacements["idle"] == 0.0


class FakeStepEnv:
    def __init__(self):
        self.env = self
        self.eef = np.array([0.0, 0.0, 0.7])
        self.object_states_dict = {}

    def step(self, action):
        self.eef += np.asarray(action)[:3] * 0.02
        return {"robot0_eef_pos": self.eef.copy()}, 0.0, False, {}


def test_controller_calls_observer_after_each_counted_step():
    calls = []
    env = FakeStepEnv()
    controller = LiberoOracleSkillController(
        env,
        {"robot0_eef_pos": env.eef.copy()},
        step_observer=lambda action, step: calls.append((action.copy(), step)),
    )
    controller.hold("observe", 2, gripper=-1.0)
    assert [step for _, step in calls] == [1, 2]
    assert all(action[6] == -1.0 for action, _ in calls)


def test_move_to_honors_translation_action_limit():
    calls = []
    env = FakeStepEnv()
    controller = LiberoOracleSkillController(
        env,
        {"robot0_eef_pos": env.eef.copy()},
        step_observer=lambda action, step: calls.append(action.copy()),
    )
    result = controller.move_to(
        "slow_descent",
        [0.10, 0.0, 0.70],
        gripper=1.0,
        translation_action_limit=0.25,
    )
    assert result.final_error_m is not None
    assert result.final_error_m < controller.config.position_tolerance_m
    assert max(np.max(np.abs(action[:3])) for action in calls) <= 0.25
