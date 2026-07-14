from __future__ import annotations

import inspect
from types import SimpleNamespace

import numpy as np

import libero_real_backend
from libero_experiment_core import ExperimentConfig
from libero_real_backend import RealExperimentBackend


def test_real_backend_exposes_dashboard_contract_without_loading_runtime() -> None:
    backend = RealExperimentBackend()
    required = [
        "load",
        "reset",
        "step_once",
        "apply_disturbance",
        "get_snapshot",
        "stop",
        "close",
    ]
    for name in required:
        assert callable(getattr(backend, name))

    assert backend.loaded is False
    snap = backend.get_snapshot()
    assert snap["backend"] == "real"
    assert snap["model_loaded"] is False

    load_sig = inspect.signature(backend.load)
    reset_sig = inspect.signature(backend.reset)
    assert "config" in load_sig.parameters
    assert {"task", "initial_state", "seed"}.issubset(reset_sig.parameters)


def test_real_backend_stop_is_idempotent_before_load() -> None:
    backend = RealExperimentBackend()
    backend.stop()
    backend.close()
    assert backend.loaded is False


def test_manual_disturbance_records_audit_fields_without_policy_step(monkeypatch) -> None:
    backend = RealExperimentBackend()
    cfg = ExperimentConfig(
        checkpoint="fake://openvla",
        mode="reactive_disturbed",
        target_joint="akita_black_bowl_1_joint0",
        enable_auto_disturbance=False,
    )
    backend.model_cfg = object()
    backend.runtime = SimpleNamespace(
        config=cfg,
        env=object(),
        obs={},
        resize_size=64,
        target_selection=SimpleNamespace(selected_joint="akita_black_bowl_1_joint0"),
        policy_step=3,
        disturbance_count=0,
        manual_disturbance_count=0,
        auto_disturbance_count=0,
        extra_environment_steps=0,
        original_prompt="pick up the black bowl",
        current_prompt="pick up the black bowl",
        recovery_state=None,
        last_disturbance=None,
        last_fresh_observation=None,
        latest_frame=None,
    )

    def fake_move(env, joint, dx, dy):
        return {
            "joint": joint,
            "joint_id": 1,
            "qpos_addr": 7,
            "before_qpos": [1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0],
            "after_qpos": [1.1, 2.05, 3.0, 0.0, 0.0, 0.0, 1.0],
            "delta_xy": [dx, dy],
            "applied_at": "2026-07-14T00:00:00Z",
        }

    monkeypatch.setattr(libero_real_backend, "move_free_joint_xy", fake_move)
    monkeypatch.setattr(
        libero_real_backend,
        "refresh_observation_after_sim_change",
        lambda env, model_cfg: (
            {"agentview_image": np.zeros((4, 4, 3), dtype=np.uint8)},
            {
                "method": "env.env._get_observations(force_update=True)",
                "consumed_noop_env_step": False,
            },
        ),
    )
    monkeypatch.setattr(
        libero_real_backend,
        "frame_from_obs",
        lambda obs, resize_size: np.zeros((4, 4, 3), dtype=np.uint8),
    )

    record = backend.apply_disturbance(
        cfg,
        policy_step=3,
        source="manual_ui",
        target_joint="akita_black_bowl_1_joint0",
        dx=0.10,
        dy=0.05,
    )

    assert record["applied"] is True
    assert record["target_joint"] == "akita_black_bowl_1_joint0"
    assert record["before_position"] == [1.0, 2.0, 3.0]
    assert record["after_position"] == [1.1, 2.05, 3.0]
    assert record["actual_delta"] == [0.10000000000000009, 0.04999999999999982, 0.0]
    assert record["fresh_observation"] is True
    assert record["observation_refresh_method"] == "env.env._get_observations(force_update=True)"
    assert record["consumed_noop_env_step"] is False
    assert record["policy_step_before_disturbance"] == 3
    assert record["policy_step_after_disturbance"] == 3
    assert record["policy_step_unchanged_by_disturbance"] is True
    assert record["refresh"]["fresh_observation"] is True
    assert record["refresh"]["observation_refresh_method"] == record["observation_refresh_method"]
