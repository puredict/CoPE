from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from libero_experiment_core import inspect_target_joint_candidates


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "audit_libero_spatial_targets.py"
SPEC = importlib.util.spec_from_file_location("audit_libero_spatial_targets", MODULE_PATH)
audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(audit)


class FakeModel:
    def __init__(self, names: list[str]) -> None:
        self._names = names
        self.njnt = len(names)
        self.jnt_type = np.zeros(len(names), dtype=int)
        self.jnt_qposadr = np.arange(len(names), dtype=int) * 7

    def joint_id2name(self, joint_id: int) -> str:
        return self._names[joint_id]

    def joint_name2id(self, joint_name: str) -> int:
        return self._names.index(joint_name)

    def geom_id2name(self, geom_id: int) -> str:
        return f"geom_{geom_id}"


class FakeData:
    def __init__(self, names: list[str]) -> None:
        self.qpos = np.zeros(len(names) * 7, dtype=float)
        self.qvel = np.zeros(len(names) * 7, dtype=float)
        for index in range(len(names)):
            addr = index * 7
            self.qpos[addr + 2] = 0.85
            self.qpos[addr + 3] = 1.0
        self.ncon = 0
        self.contact = []


class FakeSim:
    def __init__(self, names: list[str]) -> None:
        self.model = FakeModel(names)
        self.data = FakeData(names)
        self.forward_calls = 0

    def forward(self) -> None:
        self.forward_calls += 1


class FakeEnv:
    def __init__(self, names: list[str]) -> None:
        self.env = self
        self.sim = FakeSim(names)
        self.step_calls = 0
        self.reset_calls = 0

    def reset(self) -> dict[str, np.ndarray]:
        self.reset_calls += 1
        return self._get_observations(force_update=True)

    def set_init_state(self, state: np.ndarray) -> dict[str, np.ndarray]:
        self.sim.data.qpos[:] = state
        return self._get_observations(force_update=True)

    def _get_observations(self, force_update: bool = False) -> dict[str, np.ndarray]:
        image = np.zeros((16, 16, 3), dtype=np.uint8)
        marker = int(round(float(self.sim.data.qpos.sum()) * 100)) % 255
        image[0, 0, 0] = marker
        return {"agentview_image": image, "force_update": np.asarray([force_update])}

    def step(self, action):  # noqa: ANN001
        self.step_calls += 1
        raise AssertionError("audit diagnostics must not consume env.step in this test")


def fake_frame(obs: dict[str, np.ndarray], resize_size) -> np.ndarray:  # noqa: ANN001
    return obs["agentview_image"]


def test_candidate_enumeration_ignores_robot_and_scores_tokens() -> None:
    env = FakeEnv(["robot0_joint0", "black_bowl_1_joint0", "plate_1_joint0"])
    inspection = inspect_target_joint_candidates(
        env,
        "pick up the black bowl and place it on the plate",
    )
    task = audit.build_task_audit(
        task_id=0,
        task_description="pick up the black bowl and place it on the plate",
        initial_state_count=50,
        raw_candidates=inspection.candidates,
        inspection=inspection,
    )

    assert task["movable_free_joint_count"] == 2
    assert task["recommended_target_joint"] == "black_bowl_1_joint0"
    assert task["auto_reliable"] is True
    assert task["candidates"][0]["text_match_tokens"] == ["black", "bowl"]


def test_tie_is_marked_and_requires_manual_review_without_unique_semantics() -> None:
    env = FakeEnv(["red_mug_1_joint0", "blue_mug_1_joint0"])
    description = "pick up the mug and place it on the plate"
    inspection = inspect_target_joint_candidates(env, description)
    task = audit.build_task_audit(
        task_id=1,
        task_description=description,
        initial_state_count=50,
        raw_candidates=inspection.candidates,
        inspection=inspection,
    )

    assert task["recommended_target_joint"] is None
    assert task["ambiguous"] is True
    assert task["manual_review_required"] is True
    assert all(candidate["tied"] for candidate in task["candidates"])


def test_semantic_direct_object_can_recommend_explicit_joint_but_marks_review() -> None:
    env = FakeEnv(["black_bowl_1_joint0", "plate_1_joint0"])
    description = "pick up the bowl and place it on the plate"
    inspection = inspect_target_joint_candidates(env, description)
    task = audit.build_task_audit(
        task_id=2,
        task_description=description,
        initial_state_count=50,
        raw_candidates=inspection.candidates,
        inspection=inspection,
    )

    assert task["auto_reliable"] is False
    assert task["recommended_target_joint"] == "black_bowl_1_joint0"
    assert task["manual_review_required"] is True
    assert "direct object phrase" in task["selection_reason"]


def test_qpos_mutation_fresh_observation_and_restore_without_env_step() -> None:
    env = FakeEnv(["black_bowl_1_joint0", "plate_1_joint0"])
    initial_state = env.sim.data.qpos.copy()
    result = audit.run_disturbance_diagnostic(
        env=env,
        cfg=SimpleNamespace(model_family="openvla"),
        initial_state=initial_state,
        target_joint="black_bowl_1_joint0",
        dx=0.10,
        dy=0.05,
        dz=0.0,
        frame_extractor=fake_frame,
    )

    assert result["qpos_delta_matches_request"] is True
    assert result["restore_successful"] is True
    assert result["fresh_observation_changed_pixels"] > 0
    assert result["consumed_noop_env_step"] is False
    assert result["geometric_sanity"] is True
    assert env.step_calls == 0
    np.testing.assert_allclose(env.sim.data.qpos, initial_state)


def test_yaml_schema_contains_required_task_fields(tmp_path: Path) -> None:
    pytest = __import__("pytest")
    yaml = pytest.importorskip("yaml")
    payload = {
        "suite": "libero_spatial",
        "generated_at": "test",
        "disturbance_request": {"dx": 0.1, "dy": 0.05, "dz": 0.0},
        "recommended_pilot_tasks": [],
        "tasks": {
            "0": {
                "description": "pick up the bowl",
                "recommended_target_joint": "black_bowl_1_joint0",
                "candidates": [{"joint": "black_bowl_1_joint0", "score": 1, "reason": "test"}],
                "ambiguous": False,
                "manual_review_required": False,
                "disturbance": {
                    "dx": 0.1,
                    "dy": 0.05,
                    "state_0_geometric_sanity": True,
                    "camera_visibility_proxy": True,
                },
            }
        },
    }
    out = tmp_path / "audit.yaml"
    audit.write_yaml(out, payload)
    parsed = yaml.safe_load(out.read_text(encoding="utf-8"))

    task = parsed["tasks"]["0"]
    assert task["description"] == "pick up the bowl"
    assert task["recommended_target_joint"] == "black_bowl_1_joint0"
    assert isinstance(task["candidates"], list)
    assert "disturbance" in task


def test_audit_tool_has_no_openvla_model_imports() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "AutoModelForVision2Seq",
        "AutoProcessor",
        "transformers",
        "get_action(",
        "get_model(",
        "load_model_and_processor(",
    )
    for token in forbidden:
        assert token not in source
