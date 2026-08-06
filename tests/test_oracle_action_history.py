from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from cope_benchmark.oracle_skill_controller import LiberoOracleSkillController


class FakeEnv:
    def __init__(self):
        self.env = self
        self.eef = np.array([0.0, 0.0, 0.7])
        self.object_states_dict = {}
        self.objects_dict = {}
        self.robots = [SimpleNamespace(gripper=object())]

    def step(self, action):
        self.eef += np.asarray(action)[:3] * 0.01
        return {"robot0_eef_pos": self.eef.copy()}, 0.0, False, {}


def test_action_prefix_hash_is_stable_and_prefix_sensitive():
    env = FakeEnv()
    controller = LiberoOracleSkillController(
        env, {"robot0_eef_pos": env.eef.copy()}
    )
    empty_hash = controller.action_prefix_sha256()
    controller.hold("hold", 2, gripper=-1.0)
    first_hash = controller.action_prefix_sha256(1)
    full_hash = controller.action_prefix_sha256()

    assert controller.total_steps == 2
    assert len(controller.action_history) == 2
    assert empty_hash != first_hash
    assert first_hash != full_hash
    assert full_hash == controller.action_prefix_sha256(2)
