"""Opt-in real LIBERO physics smoke, without learned models or rendering GPUs.

Run COPE_RUN_LIBERO_SMOKE=1 with an interpreter containing installed LIBERO,
MuJoCo and existing assets. Imports use an isolated temporary LIBERO config;
the test never changes ~/.libero or downloads assets/checkpoints. This does not
establish VLA feasibility or repeated-interruption benchmark performance.
"""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest


ASSET_ROOT_PROGRAM = r'''
from pathlib import Path

def find_libero_asset_root(spec):
    if spec is None:
        raise RuntimeError("BLOCKED_SIMULATOR_DEPENDENCIES_UNAVAILABLE: libero")
    locations = list(spec.submodule_search_locations or ())
    if spec.origin:
        locations.append(str(Path(spec.origin).parent))
    candidates = []
    for location in locations:
        for candidate in (Path(location) / "libero", Path(location)):
            if candidate not in candidates:
                candidates.append(candidate)
    required = ("assets", "bddl_files", "init_files")
    for candidate in candidates:
        if all((candidate / name).is_dir() for name in required):
            return candidate
    raise RuntimeError("BLOCKED_SIMULATOR_ASSETS_UNAVAILABLE: "
                       "assets, bddl_files, init_files; searched "
                       + ", ".join(str(candidate) for candidate in candidates))
'''


SMOKE_PROGRAM = ASSET_ROOT_PROGRAM + r'''
import importlib.util,json,os,tempfile
root=find_libero_asset_root(importlib.util.find_spec("libero"))
with tempfile.TemporaryDirectory(prefix="cope-libero-smoke-") as config_dir:
    config={"benchmark_root":str(root),"bddl_files":str(root/"bddl_files"),
            "init_states":str(root/"init_files"),"assets":str(root/"assets"),
            "datasets":str(root.parent/"datasets")}
    Path(config_dir,"config.yaml").write_text(json.dumps(config))
    os.environ["LIBERO_CONFIG_PATH"]=config_dir
    from libero.libero import benchmark
    from libero.libero.envs.env_wrapper import ControlEnv
    import numpy as np
    suite=benchmark.get_benchmark_dict()["libero_10"]()
    task=suite.get_task(1)
    print("task=" + task.name,flush=True)
    env=ControlEnv(bddl_file_name=str(root/"bddl_files"/task.problem_folder/task.bddl_file),
                   use_camera_obs=False,has_renderer=False,has_offscreen_renderer=False,
                   hard_reset=True)
    try:
        env.seed(17)
        env.reset()
        states=suite.get_task_init_states(1)
        observation=env.set_init_state(states[0])
        assert "robot0_eef_pos" in observation
        state=env.get_sim_state().copy()
        print("reset_ok initial_states=" + str(len(states)),flush=True)
        observation,reward,done,info=env.step([0.,0.,0.,0.,0.,0.,-1.])
        assert np.isfinite(np.asarray(observation["robot0_eef_pos"])).all()
        print("step_ok reward=" + str(float(reward)) + " done=" + str(bool(done)),flush=True)
        observation=env.set_init_state(state)
        assert np.array_equal(env.get_sim_state(),state), "physics state restore mismatch"
        print("restore_exact=True",flush=True)
        env._update_observables(force=True)
        refreshed=env.env._get_observations(force_update=True)
        assert np.array_equal(refreshed["robot0_eef_pos"],observation["robot0_eef_pos"])
        print("fresh_observation_without_step=True",flush=True)
        print("PASS_CPU_LIBERO_PHYSICS_SMOKE",flush=True)
    finally:
        env.close()
'''


class SimulatorAssetDiscoveryTests(unittest.TestCase):
    def setUp(self):
        namespace = {}
        exec(ASSET_ROOT_PROGRAM, namespace)
        self.discover = namespace["find_libero_asset_root"]

    def test_regular_package_origin_finds_existing_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "libero"
            root = package / "libero"
            for name in ("assets", "bddl_files", "init_files"):
                (root / name).mkdir(parents=True)
            spec = SimpleNamespace(origin=str(package / "__init__.py"),
                                   submodule_search_locations=None)
            self.assertEqual(self.discover(spec), root)

    def test_namespace_search_locations_skip_incomplete_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            incomplete = Path(directory) / "first"
            (incomplete / "libero" / "assets").mkdir(parents=True)
            complete = Path(directory) / "second"
            root = complete / "libero"
            for name in ("assets", "bddl_files", "init_files"):
                (root / name).mkdir(parents=True)
            spec = SimpleNamespace(origin=None,
                                   submodule_search_locations=[str(incomplete), str(complete)])
            self.assertEqual(self.discover(spec), root)

    def test_missing_asset_directory_fails_without_creating_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            (root / "bddl_files").mkdir()
            spec = SimpleNamespace(origin=None, submodule_search_locations=[str(root)])
            with self.assertRaisesRegex(RuntimeError, "BLOCKED_SIMULATOR_ASSETS_UNAVAILABLE"):
                self.discover(spec)
            self.assertFalse((root / "init_files").exists())


@unittest.skipUnless(os.environ.get("COPE_RUN_LIBERO_SMOKE") == "1",
                     "opt in with COPE_RUN_LIBERO_SMOKE=1; requires local simulator assets")
class SimulatorSmokeTests(unittest.TestCase):
    def test_real_libero_reset_step_restore_and_fresh_observation(self):
        missing = [name for name in ("libero", "robosuite", "mujoco", "torch", "numpy")
                   if importlib.util.find_spec(name) is None]
        if missing:
            self.skipTest("BLOCKED_SIMULATOR_DEPENDENCIES_UNAVAILABLE: " + ", ".join(missing))
        environment = dict(os.environ)
        environment.update(PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1",
                           TRANSFORMERS_OFFLINE="1", CUDA_VISIBLE_DEVICES="")
        result = subprocess.run([sys.executable, "-c", SMOKE_PROGRAM], env=environment,
                                capture_output=True, text=True, timeout=90)
        print(result.stdout, end="")
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)
        self.assertIn("PASS_CPU_LIBERO_PHYSICS_SMOKE", result.stdout)


if __name__ == "__main__":
    unittest.main()
