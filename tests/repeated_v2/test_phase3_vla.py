"""Protocol boundary tests use injected clients; they are not VLA evidence."""

import hashlib
import math
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from cope_benchmark.repeated_v2.vla_adapter import (
    ActionChunk, BLOCKED_VLA_ADAPTER_UNAVAILABLE, NativeOpenVLAAdapter,
    VLAAdapterUnavailable, VLAContractError, checkpoint_sha256,
    create_native_openvla, load_vla_adapter, public_observation,
    require_vla_adapter, restore_adapter, snapshot_adapter,
    to_environment_action, validate_action_chunk,
)


class LearnedClient:
    provider_id = "local_learned_client"
    learned_policy = True
    uses_privileged_state = False
    stateless = True

    def __init__(self, checkpoint):
        self.identity = {
            "provider_id": self.provider_id,
            "policy_model_id": "openvla-7b",
            "adapter_type": "observation_client",
            "checkpoint_path": str(checkpoint),
            "checkpoint_sha256": checkpoint_sha256(checkpoint),
            "action_dim": 7,
            "max_chunk_horizon": 8,
            "action_space": "libero_environment",
        }
        self.closed = False

    def reset(self, **kwargs): pass
    def begin_subgoal(self, compiled_instruction): pass
    def act(self, observation): return ActionChunk(((0.0,) * 7,))
    def close(self): self.closed = True


class VLAContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.checkpoint = Path(self.temporary.name) / "weights.bin"
        self.checkpoint.write_bytes(b"synthetic unit-test checkpoint, never research evidence")
        self.adapter = LearnedClient(self.checkpoint)

    def test_formal_gate_requires_exact_booleans(self):
        require_vla_adapter(self.adapter)
        for value in (1, "true", None, False):
            with self.subTest(learned_policy=value):
                self.adapter.learned_policy = value
                with self.assertRaises(VLAContractError):
                    require_vla_adapter(self.adapter)
        self.adapter.learned_policy = True
        for value in (0, "false", None, True):
            with self.subTest(uses_privileged_state=value):
                self.adapter.uses_privileged_state = value
                with self.assertRaises(VLAContractError):
                    require_vla_adapter(self.adapter)

    def test_every_identity_surface_rejects_scripted_policy_markers(self):
        for key in ("provider_id", "policy_model_id", "adapter_type"):
            for marker in ("oracle", "mock", "fake", "scripted", "heuristic", "dummy"):
                with self.subTest(key=key, marker=marker):
                    adapter = LearnedClient(self.checkpoint)
                    adapter.identity[key] += "_" + marker
                    if key == "provider_id":
                        adapter.provider_id = adapter.identity[key]
                    with self.assertRaises(VLAContractError):
                        require_vla_adapter(adapter)
        class OracleClient(LearnedClient): pass
        with self.assertRaises(VLAContractError):
            require_vla_adapter(OracleClient(self.checkpoint))

    def test_checkpoint_hash_is_verified_against_actual_bytes(self):
        expected = hashlib.sha256(self.checkpoint.read_bytes()).hexdigest()
        self.assertEqual(checkpoint_sha256(self.checkpoint), expected)
        self.checkpoint.write_bytes(b"changed")
        with self.assertRaisesRegex(VLAContractError, "hash mismatch"):
            require_vla_adapter(self.adapter)
        with self.assertRaises(VLAContractError):
            require_vla_adapter(self.adapter, verify_checkpoint=False)

    def test_missing_hash_or_unverifiable_remote_hash_rejected(self):
        self.adapter.identity["checkpoint_sha256"] = "looks plausible"
        with self.assertRaises(VLAContractError):
            require_vla_adapter(self.adapter)
        self.adapter.identity["checkpoint_sha256"] = "a" * 64
        self.adapter.identity["checkpoint_path"] = "https://model.invalid/checkpoint"
        with self.assertRaises(VLAAdapterUnavailable):
            require_vla_adapter(self.adapter)

    def test_directory_hash_is_order_independent_and_content_sensitive(self):
        root = Path(self.temporary.name) / "checkpoint"
        root.mkdir()
        (root / "b").write_bytes(b"b")
        (root / "a").write_bytes(b"a")
        before = checkpoint_sha256(root)
        self.assertEqual(before, checkpoint_sha256(root))
        (root / "a").write_bytes(b"c")
        self.assertNotEqual(before, checkpoint_sha256(root))
        (root / "linked-directory").symlink_to(root, target_is_directory=True)
        with self.assertRaises(VLAContractError):
            checkpoint_sha256(root)

    def test_huggingface_file_symlinks_hash_resolved_bytes_without_copy(self):
        root = Path(self.temporary.name) / 'hf-snapshot'
        root.mkdir()
        link = root / 'model.safetensors'
        link.symlink_to(self.checkpoint)
        expected = hashlib.sha256(b'model.safetensors\0' + hashlib.sha256(self.checkpoint.read_bytes()).digest()).hexdigest()
        self.assertEqual(checkpoint_sha256(root), expected)
        self.assertEqual(checkpoint_sha256(link), checkpoint_sha256(self.checkpoint))
        self.assertTrue(link.is_symlink())
        self.checkpoint.write_bytes(b'new target contents')
        self.assertNotEqual(checkpoint_sha256(root), expected)

    def test_checkpoint_symlink_cycles_and_target_switch_during_hash_fail_closed(self):
        root = Path(self.temporary.name)
        cycle = root / 'cycle'
        cycle.symlink_to(cycle)
        with self.assertRaises(VLAContractError):
            checkpoint_sha256(cycle)
        replacement = root / 'replacement.bin'
        replacement.write_bytes(b'different checkpoint')
        link = root / 'model-link'
        link.symlink_to(self.checkpoint)
        original_open = Path.open
        def switch_target(path, *args, **kwargs):
            opened = original_open(path, *args, **kwargs)
            if path == self.checkpoint.resolve() and args == ('rb',):
                link.unlink()
                link.symlink_to(replacement)
            return opened
        with patch.object(Path, 'open', switch_target):
            with self.assertRaisesRegex(VLAContractError, 'changed'):
                checkpoint_sha256(link)

    def test_actions_reject_wrong_rank_dimension_nonfinite_and_booleans(self):
        valid = validate_action_chunk([[0, 0.1, -0.2, 0, 0, 0, 1]], max_horizon=1)
        self.assertEqual(valid.values, ((0.0, 0.1, -0.2, 0.0, 0.0, 0.0, 1.0),))
        invalid = ([], [0] * 7, [[0] * 6], [[0] * 8], [[True] * 7],
                   [["0"] * 7], [[math.nan] * 7], [[math.inf] * 7], [[0j] * 7],
                   [[0] * 7] * 2)
        for chunk in invalid:
            with self.subTest(chunk=chunk):
                with self.assertRaises(VLAContractError):
                    validate_action_chunk(chunk, max_horizon=1)

    def test_common_executor_conversion_matches_openvla_gripper_and_never_double_transforms(self):
        raw = [0.1, -0.2, 0.3, -0.4, 0.5, -0.6, 0.25]
        self.assertEqual(to_environment_action(self.adapter, raw), tuple(raw))
        self.adapter.identity["action_space"] = "openvla_raw_normalize_binarize_then_invert_gripper"
        for value, expected in ((0, 1), (0.25, 1), (0.5, 0), (0.75, -1), (1, -1)):
            with self.subTest(gripper=value):
                raw[-1] = value
                converted = to_environment_action(self.adapter, raw)
                self.assertEqual(converted[:-1], tuple(raw[:-1]))
                self.assertEqual(converted[-1], expected)
                self.assertEqual(raw[-1], value)
        self.adapter.identity.pop("action_space")
        with self.assertRaises(VLAContractError):
            to_environment_action(self.adapter, raw)

    def test_privileged_observations_are_rejected_and_public_copy_is_detached(self):
        observation = {"rgb": [[[0, 0, 0]]], "proprio": [0] * 8, "step": 4}
        projected = public_observation(observation)
        self.assertEqual(set(projected), {"full_image", "state", "step"})
        projected["state"][0] = 5
        self.assertEqual(observation["proprio"][0], 0)
        for key in ("env", "sim", "task_id", "object_poses", "contacts", "canonical_state"):
            with self.subTest(key=key):
                with self.assertRaises(VLAContractError):
                    public_observation({**observation, key: {}})
        with self.assertRaises(VLAContractError):
            public_observation({**observation, "full_image": []})
        for name in ("rgb", "proprio", "timestamp", "observation_ref"):
            with self.subTest(name=name):
                with self.assertRaises(VLAContractError):
                    public_observation({**observation, name: {"canonical_state": "hidden"}})

    def test_stateful_clients_need_both_snapshot_and_restore(self):
        self.adapter.stateless = False
        with self.assertRaisesRegex(VLAContractError, "snapshot and restore"):
            require_vla_adapter(self.adapter)
        self.adapter.stateless = True
        self.assertEqual(snapshot_adapter(self.adapter), {"stateless": True})
        restore_adapter(self.adapter, {"stateless": True})
        with self.assertRaises(VLAContractError):
            restore_adapter(self.adapter, {"unexpected": "state"})

    def test_factory_is_lazy_and_failed_admission_closes_client(self):
        module = types.ModuleType("phase3_client_fixture")
        module.make = lambda config: self.adapter
        sys.modules[module.__name__] = module
        self.addCleanup(sys.modules.pop, module.__name__, None)
        self.assertIs(load_vla_adapter("phase3_client_fixture:make"), self.adapter)
        self.adapter.learned_policy = False
        with self.assertRaises(VLAContractError):
            load_vla_adapter("phase3_client_fixture:make")
        self.assertTrue(self.adapter.closed)
        with self.assertRaises(VLAAdapterUnavailable) as missing:
            load_vla_adapter("phase3_no_such_client:make")
        self.assertEqual(missing.exception.status, BLOCKED_VLA_ADAPTER_UNAVAILABLE)
        for spec in ("broken", ":factory", "module:", "a:b:c"):
            with self.assertRaises(VLAContractError):
                load_vla_adapter(spec)

    def test_native_missing_dependencies_are_blocked_without_loading_model(self):
        before = "torch" in sys.modules
        with self.assertRaises(VLAAdapterUnavailable) as caught:
            create_native_openvla({"checkpoint_path": str(Path(self.temporary.name) / "absent")})
        self.assertEqual(caught.exception.status, BLOCKED_VLA_ADAPTER_UNAVAILABLE)
        self.assertEqual("torch" in sys.modules, before)

    def test_native_gpu_gate_rejects_busy_device_before_model_loading(self):
        root = Path(self.temporary.name)
        checkpoint = root / "model"
        checkpoint.mkdir()
        (checkpoint / "config.json").write_text("{}")
        (checkpoint / "model.safetensors").write_bytes(b"fixture")
        runtime = root / "runtime"
        (runtime / "experiments/robot").mkdir(parents=True)
        (runtime / "experiments/robot/robot_utils.py").write_text("# fixture")
        config = {"checkpoint_path": str(checkpoint), "runtime_path": str(runtime),
                  "checkpoint_sha256": checkpoint_sha256(checkpoint)}
        for gpu_output, process_output in (("0, GPU-unit, 99, 0\n", ""),
                                           ("0, GPU-unit, 0, 0\n", "GPU-unit, 123\n")):
            responses = [types.SimpleNamespace(stdout=gpu_output), types.SimpleNamespace(stdout=process_output)]
            with patch("cope_benchmark.repeated_v2.vla_adapter.subprocess.run", side_effect=responses) as query:
                with self.assertRaises(VLAAdapterUnavailable):
                    create_native_openvla(config)
                self.assertTrue(all(call.args[0][0] == "nvidia-smi" for call in query.call_args_list))

    def test_native_rng_snapshot_restores_only_cpu_and_selected_initialized_gpu(self):
        calls = []
        class Tensor:
            def __init__(self, values): self.values = values
            def tolist(self): return self.values
            def cpu(self): return self
        class Generator:
            def __init__(self, name): self.name = name
            def manual_seed(self, seed): calls.append(("seed", self.name, seed))
        initialized = [True]
        torch = types.SimpleNamespace(
            random=types.SimpleNamespace(default_generator=Generator("cpu")),
            get_rng_state=lambda: Tensor([1, 2]),
            set_rng_state=lambda state: calls.append(("restore", "cpu", state.tolist())),
            tensor=lambda values, **kwargs: Tensor(values), uint8="uint8",
            cuda=types.SimpleNamespace(
                is_initialized=lambda: initialized[0],
                default_generators=[Generator("cuda:0"), Generator("cuda:1")],
                get_rng_state=lambda *, device: (calls.append(("capture", device)) or Tensor([3, 4])),
                set_rng_state=lambda state, *, device: calls.append(("restore", device, state.tolist())),
            ),
        )
        with patch.dict(sys.modules, {"torch": torch}):
            NativeOpenVLAAdapter._seed_torch(7)
            state = NativeOpenVLAAdapter._torch_snapshot()
            NativeOpenVLAAdapter._restore_torch(state)
            self.assertEqual(state, {"cpu": [1, 2], "cuda_0": [3, 4]})
            self.assertIn(("seed", "cpu", 7), calls)
            self.assertIn(("seed", "cuda:0", 7), calls)
            self.assertIn(("restore", 0, [3, 4]), calls)
            self.assertNotIn(("seed", "cuda:1", 7), calls)
            initialized[0] = False
            calls.clear()
            self.assertEqual(NativeOpenVLAAdapter._torch_snapshot(), {"cpu": [1, 2]})
            self.assertFalse(calls)
            with self.assertRaises(VLAAdapterUnavailable):
                NativeOpenVLAAdapter._restore_torch(state)

    def test_native_wrapper_only_calls_client_with_sensors_and_instruction(self):
        calls = []
        def inference(cfg, model, inputs, instruction, *, processor):
            calls.append((inputs, instruction))
            return [0, 0, 0, 0, 0, 0, 0.25]
        identity = {**self.adapter.identity, "provider_id": "openvla_native",
                    "max_chunk_horizon": 1}
        native = NativeOpenVLAAdapter(model=object(), processor=object(),
            model_config=object(), get_action=inference, identity=identity)
        obs = {"rgb": [[[1, 2, 3]]], "proprio": [0] * 8, "timestamp": 10,
               "observation_ref": "fresh-frame"}
        native.reset(task={"language": "move the cup"}, seed=7, initial_observation=obs)
        native.begin_subgoal({"instruction": "place the cup gently"})
        result = native.act(obs)
        self.assertEqual(result.values[0][-1], 0.25)  # no adapter-side gripper transform
        self.assertEqual(set(calls[0][0]), {"full_image", "state"})
        self.assertEqual(calls[0][1], "place the cup gently")
        saved = snapshot_adapter(native)
        native.begin_subgoal({"instruction": "something else"})
        restore_adapter(native, saved)
        native.act(obs)
        self.assertEqual(calls[-1][1], "place the cup gently")
        with self.assertRaises(VLAContractError):
            restore_adapter(native, {**saved, "checkpoint_sha256": "0" * 64})
        with self.assertRaises(VLAContractError):
            native.act({**obs, "object_positions": {}})
        self.assertEqual(len(calls), 2)
        native.close()
        with self.assertRaises(VLAContractError):
            native.act(obs)

    def test_native_json_restored_images_match_production_pil_input(self):
        import numpy as np
        from PIL import Image

        calls = []
        def inference(cfg, model, inputs, instruction, *, processor):
            # Mirrors the actual production get_vla_action image entrypoint.
            frame = Image.fromarray(inputs['full_image']).convert('RGB')
            calls.append((frame.size, np.asarray(frame).tolist()))
            return np.zeros(7)
        native = NativeOpenVLAAdapter(model=object(), processor=object(),
            model_config=object(), get_action=inference, identity=self.adapter.identity)
        native.begin_subgoal({'instruction': 'place the cup'})
        observation = {'rgb': [[[1, 2, 3], [253, 254, 255]]], 'proprio': [0] * 8}
        native.act(observation)
        self.assertEqual(calls, [((2, 1), observation['rgb'])])
        self.assertIsInstance(observation['rgb'], list)
        for invalid in ([], [[1, 2, 3]], [[[1, 2]]], [[[1, 2, 256]]],
                        [[[1, 2, -1]]], [[[1, 2, 0.5]]], [[[1, 2, 3]], [[1, 2, 3], [4, 5, 6]]]):
            with self.subTest(image=invalid):
                with self.assertRaises(VLAContractError):
                    native.act({'rgb': invalid})
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
