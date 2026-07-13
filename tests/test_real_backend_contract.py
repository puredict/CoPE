from __future__ import annotations

import inspect

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
