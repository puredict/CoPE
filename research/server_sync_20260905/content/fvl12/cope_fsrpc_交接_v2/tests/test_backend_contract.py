from __future__ import annotations

import pytest

from cope.backends import BackendUnavailable, make_backend
from cope.backends.base import SimulatorRepairBackend


def test_backend_factory_is_explicit_and_fails_fast():
    backend = make_backend("synthetic2d")
    assert isinstance(backend, SimulatorRepairBackend)
    assert backend.backend_name == "synthetic2d"
    with pytest.raises(BackendUnavailable, match="unknown simulator backend"):
        make_backend("not-a-real-backend")


def test_synthetic_backend_checkpoint_restore_contract():
    backend = make_backend("synthetic2d")
    backend.initialize({})
    backend.reset(seed=3)
    backend.begin_leg({"id": "g_milk", "object": "milk", "target": "basket_A"})
    checkpoint = backend.checkpoint("unit")
    backend.step([0.02, 0.01, 0.0])
    assert backend.state_hash() != checkpoint.state_hash
    restored = backend.restore(checkpoint)
    assert restored["restored"]
    assert restored["state_hash"] == checkpoint.state_hash


def test_backend_contract_lists_required_real_simulator_operations():
    required = {
        "initialize",
        "reset",
        "begin_leg",
        "observe",
        "step",
        "checkpoint",
        "restore",
        "state_hash",
        "retarget",
        "cancel_goal",
        "set_target_availability",
        "move_target",
        "collision_status",
        "attachment_status",
        "task_success",
        "settle_world",
        "write_video",
        "finish_episode",
    }
    assert required.issubset(set(SimulatorRepairBackend.__abstractmethods__))
