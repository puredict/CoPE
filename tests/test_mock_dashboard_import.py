import importlib
import sys


def test_dashboard_import_does_not_import_real_robotics_stack():
    for name in ["libero_dashboard", "libero_dashboard_controller", "libero_mock_backend"]:
        sys.modules.pop(name, None)
    module = importlib.import_module("libero_dashboard")
    assert hasattr(module, "run_mock_smoke")
    forbidden = [
        "torch",
        "robosuite",
        "mujoco",
        "libero.libero",
        "prismatic",
        "transformers",
    ]
    loaded_forbidden = [name for name in forbidden if name in sys.modules]
    assert loaded_forbidden == []
