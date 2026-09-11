"""Learned-policy boundary; imports and model loading are deliberately lazy.

The adapter never receives an environment, object poses, contacts, a task ID or
canonical commitments. The runner owns stepping and action-space conversion.
An unavailable learned policy is a blocked run, never an oracle fallback.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import math
import numbers
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


BLOCKED_VLA_ADAPTER_UNAVAILABLE = "BLOCKED_VLA_ADAPTER_UNAVAILABLE"


class VLAAdapterUnavailable(RuntimeError):
    status = BLOCKED_VLA_ADAPTER_UNAVAILABLE


class VLAContractError(ValueError):
    status = "INVALID_VLA_CONTRACT"


@dataclass(frozen=True)
class ActionChunk:
    values: tuple[tuple[float, ...], ...]


@runtime_checkable
class VLAAdapter(Protocol):
    """Plugins own all cross-call hidden state and RNG in snapshot/restore.

    Declaring stateless means inference has no cross-call hidden state or random
    stream; instruction/seed or other reset configuration must still be restored
    when the implementation carries it, as the native adapter does.
    """
    provider_id: str
    learned_policy: bool
    uses_privileged_state: bool
    stateless: bool
    identity: Mapping[str, Any]

    def reset(self, *, task: Mapping[str, Any], seed: int,
              initial_observation: Mapping[str, Any]) -> None: ...
    def begin_subgoal(self, compiled_instruction: Mapping[str, Any]) -> None: ...
    def act(self, observation: Mapping[str, Any]) -> ActionChunk: ...
    def snapshot(self) -> Mapping[str, Any]: ...
    def restore(self, state: Mapping[str, Any]) -> None: ...
    def close(self) -> None: ...


# Metadata does not enter the native policy. Unknown keys fail closed, including
# accidental simulator-observation dictionaries carrying object truth.
PUBLIC_OBSERVATION_KEYS = frozenset({
    "full_image", "wrist_image", "state", "rgb", "rgb_wrist", "proprio",
    "observation_ref", "observation_step", "step", "timestamp",
    # This field is copied from named pose observables in the ordinary LIBERO
    # observation dictionary.  It is available to the public evidence and
    # verifier components, but is deliberately removed by public_observation
    # before a VLA client receives its sensor mapping.
    "agent_visible_named_poses",
})
_FORBIDDEN_IDENTIFIERS = re.compile(r"oracle|mock|scripted|fake|heuristic|dummy|stub|placeholder", re.I)
ACTION_SPACES = frozenset({"libero_environment", "openvla_raw_normalize_binarize_then_invert_gripper"})
_CHECKPOINT_HASH_CACHE: dict[str, tuple[Any, str]] = {}


def _contract_hash(fields: Sequence[str]) -> str:
    return hashlib.sha256(json.dumps({"fields": list(fields)}, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()


def _sensor_values(value: Any, name: str) -> None:
    """Reject arbitrary nested structures masquerading as a sensor array."""
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        raise VLAContractError(f"{name} must be a numeric sensor array")
    def visit(node: Any) -> None:
        if isinstance(node, (list, tuple)):
            for child in node:
                visit(child)
        elif isinstance(node, bool) or not isinstance(node, numbers.Real) or not math.isfinite(float(node)):
            raise VLAContractError(f"{name} must contain finite numbers only")
    visit(value)


def public_observation(observation: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(observation, Mapping):
        raise VLAContractError("public observation must be a mapping")
    unexpected = set(observation) - PUBLIC_OBSERVATION_KEYS
    if unexpected:
        raise VLAContractError(f"non-public observation keys: {sorted(map(str, unexpected))}")
    result = copy.deepcopy(dict(observation))
    named_poses = result.pop("agent_visible_named_poses", None)
    if named_poses is not None:
        if not isinstance(named_poses, Mapping) or any(
                not isinstance(name, str) or not isinstance(pose, Mapping)
                or set(pose) != {"position", "quaternion"}
                for name, pose in named_poses.items()):
            raise VLAContractError("agent-visible named poses have an invalid schema")
        for name, pose in named_poses.items():
            _sensor_values(pose["position"], name + ".position")
            _sensor_values(pose["quaternion"], name + ".quaternion")
            if len(pose["position"]) != 3 or len(pose["quaternion"]) != 4:
                raise VLAContractError("agent-visible named poses require position[3] and quaternion[4]")
    for alias, canonical in (("rgb", "full_image"), ("rgb_wrist", "wrist_image"), ("proprio", "state")):
        if alias in result:
            if canonical in result:
                raise VLAContractError(f"ambiguous observation: both {alias} and {canonical}")
            result[canonical] = result.pop(alias)
    for name in ("full_image", "wrist_image", "state"):
        if name in result:
            _sensor_values(result[name], name)
    for name in ("observation_ref",):
        if name in result and not isinstance(result[name], str):
            raise VLAContractError(f"{name} must be a string")
    for name in ("observation_step", "step", "timestamp"):
        if name in result and (isinstance(result[name], bool) or
                               not isinstance(result[name], numbers.Real) or
                               not math.isfinite(float(result[name]))):
            raise VLAContractError(f"{name} must be a finite number")
    return result


def validate_action_chunk(chunk: Any, *, action_dim: int = 7,
                          max_horizon: int = 16) -> ActionChunk:
    if type(action_dim) is not int or action_dim <= 0 or type(max_horizon) is not int or max_horizon <= 0:
        raise VLAContractError("action dimension and horizon must be positive integers")
    values = getattr(chunk, "values", chunk)
    if hasattr(values, "tolist"):
        values = values.tolist()
    if not isinstance(values, (tuple, list)) or not 1 <= len(values) <= max_horizon:
        raise VLAContractError("action chunk must contain 1..max_horizon actions")
    actions = []
    for row in values:
        if hasattr(row, "tolist"):
            row = row.tolist()
        if not isinstance(row, (tuple, list)) or len(row) != action_dim:
            raise VLAContractError(f"each action must have exactly {action_dim} coordinates")
        converted = []
        for value in row:
            if isinstance(value, bool) or not isinstance(value, numbers.Real):
                raise VLAContractError("actions must be real numbers, not booleans or numeric strings")
            value = float(value)
            if not math.isfinite(value):
                raise VLAContractError("actions must be finite")
            converted.append(value)
        actions.append(tuple(converted))
    return ActionChunk(tuple(actions))


def checkpoint_sha256(path: str | Path) -> str:
    """Hash actual local checkpoint bytes, never an unverified service claim.

    Files use their ordinary SHA256. Directories use SHA256 over sorted relative
    names, NUL separators and per-file SHA256 digests. Hugging Face file
    symlinks are resolved in place; directory symlinks are never traversed.
    Link targets and file metadata must remain stable throughout hashing.
    """
    source = Path(path).expanduser()
    def signature(info: Any) -> tuple[Any, ...]:
        return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)
    def file_snapshot(file: Path) -> tuple[Path, tuple[Any, ...], tuple[Any, ...]]:
        try:
            target = file.resolve(strict=True)
            entry, contents = file.lstat(), target.stat()
        except (OSError, RuntimeError) as exc:
            raise VLAContractError(f"checkpoint file link is missing or cyclic: {file}") from exc
        if not stat.S_ISREG(contents.st_mode):
            raise VLAContractError(f"checkpoint entry must resolve to a regular file: {file}")
        return target, signature(entry), signature(contents)
    if not source.exists() and not source.is_symlink():
        raise VLAAdapterUnavailable(f"checkpoint source unavailable: {source}")
    if source.is_symlink() and source.is_dir():
        raise VLAContractError("checkpoint directory symlinks cannot be traversed")
    snapshots: dict[Path, tuple[Path, tuple[Any, ...], tuple[Any, ...]]] = {}
    def file_digest(file: Path) -> bytes:
        before = file_snapshot(file)
        snapshots[file] = before
        value = hashlib.sha256()
        with before[0].open("rb") as handle:
            if signature(os.fstat(handle.fileno())) != before[2]:
                raise VLAContractError("checkpoint file changed before hashing")
            for data in iter(lambda: handle.read(1024 * 1024), b""):
                value.update(data)
            if signature(os.fstat(handle.fileno())) != before[2]:
                raise VLAContractError("checkpoint file changed while hashing")
        if file_snapshot(file) != before:
            raise VLAContractError("checkpoint file or symlink target changed while hashing")
        return value.digest()
    if source.is_file() or source.is_symlink():
        before = file_snapshot(source)
        cache_key = str(source.resolve())
        cached = _CHECKPOINT_HASH_CACHE.get(cache_key)
        if cached is not None and cached[0] == before:
            return cached[1]
        result = file_digest(source).hex()
        _CHECKPOINT_HASH_CACHE[cache_key] = (before, result)
        return result
    if not source.is_dir():
        raise VLAAdapterUnavailable(f"checkpoint is neither a file nor directory: {source}")
    files = sorted(source.rglob("*"))
    for file in files:
        if file.is_symlink():
            file_snapshot(file)  # Reject cycles, broken links, and directory links.
    files = [file for file in files if file.is_file() or file.is_symlink()]
    if not files:
        raise VLAAdapterUnavailable(f"checkpoint directory is empty: {source}")
    before_manifest = tuple((file.relative_to(source).as_posix(), file_snapshot(file))
                            for file in files)
    cache_key = str(source.resolve())
    cached = _CHECKPOINT_HASH_CACHE.get(cache_key)
    if cached is not None and cached[0] == before_manifest:
        return cached[1]
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.relative_to(source).as_posix().encode("utf-8") + b"\0")
        digest.update(file_digest(file))
    after_files = sorted(file for file in source.rglob("*") if file.is_file() or file.is_symlink())
    if after_files != files or any(file_snapshot(file) != before for file, before in snapshots.items()):
        raise VLAContractError("checkpoint manifest or symlink targets changed while hashing")
    result = digest.hexdigest()
    _CHECKPOINT_HASH_CACHE[cache_key] = (before_manifest, result)
    return result


def to_environment_action(adapter: Any, row: Any) -> tuple[float, ...]:
    """Common-executor conversion; preserves the policy's raw trace separately."""
    action = validate_action_chunk([row], action_dim=7, max_horizon=1).values[0]
    action_space = adapter.identity.get("action_space")
    if action_space == "libero_environment":
        return action
    if action_space == "openvla_raw_normalize_binarize_then_invert_gripper":
        normalized = 2.0 * action[-1] - 1.0
        gripper = -1.0 if normalized > 0 else (1.0 if normalized < 0 else 0.0)
        return (*action[:-1], gripper)
    raise VLAContractError("adapter must declare a supported action_space; transformation cannot be inferred")


def require_vla_adapter(adapter: Any, *, formal: bool = True,
                        verify_checkpoint: bool = True) -> Mapping[str, Any]:
    """Apply formal admission independently of a factory's claimed identity."""
    for name in ("reset", "begin_subgoal", "act", "close"):
        if not callable(getattr(adapter, name, None)):
            raise VLAContractError(f"VLA adapter missing callable {name}")
    identity = getattr(adapter, "identity", None)
    if not isinstance(identity, Mapping):
        raise VLAContractError("VLA adapter must expose an identity mapping")
    if formal:
        if getattr(adapter, "learned_policy", None) is not True:
            raise VLAContractError("formal VLA adapter must declare learned_policy=True")
        if getattr(adapter, "uses_privileged_state", None) is not False:
            raise VLAContractError("formal VLA adapter must declare uses_privileged_state=False")
        identifiers = [getattr(adapter, "provider_id", ""), identity.get("provider_id", ""),
                       identity.get("policy_model_id", ""), identity.get("adapter_type", ""),
                       type(adapter).__name__, type(adapter).__module__]
        if any(not isinstance(item, str) or not item.strip() for item in identifiers[:4]):
            raise VLAContractError("provider, model and adapter identifiers must be nonempty strings")
        if identity["provider_id"] != adapter.provider_id:
            raise VLAContractError("adapter and identity provider IDs differ")
        if any(_FORBIDDEN_IDENTIFIERS.search(item) for item in identifiers):
            raise VLAContractError("formal VLA gate rejects simulated or oracle policy identifiers")
        expected = identity.get("checkpoint_sha256")
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise VLAContractError("formal VLA requires checkpoint_sha256")
        source = identity.get("checkpoint_path")
        if not isinstance(source, str) or not source:
            raise VLAContractError("formal VLA requires a verifiable local checkpoint_path")
        if not verify_checkpoint:
            raise VLAContractError("formal VLA cannot disable checkpoint verification")
        if checkpoint_sha256(source) != expected:
            raise VLAContractError("checkpoint content hash mismatch")
    for key in ("action_dim", "max_chunk_horizon"):
        value = identity.get(key)
        if type(value) is not int or value <= 0:
            raise VLAContractError(f"VLA identity {key} must be a positive integer")
    if identity["action_dim"] != 7:
        raise VLAContractError("the common LIBERO executor requires 7-dimensional actions")
    if identity.get("action_space") not in ACTION_SPACES:
        raise VLAContractError("VLA identity must declare a supported action_space")
    if getattr(adapter, "stateless", None) not in (True, False) or type(getattr(adapter, "stateless", None)) is not bool:
        raise VLAContractError("VLA adapter must explicitly declare stateless")
    if not adapter.stateless and (not callable(getattr(adapter, "snapshot", None)) or
                                  not callable(getattr(adapter, "restore", None))):
        raise VLAContractError("stateful VLA adapters require snapshot and restore")
    return copy.deepcopy(dict(identity))


def snapshot_adapter(adapter: Any) -> dict[str, Any]:
    snapshot = getattr(adapter, "snapshot", None)
    if callable(snapshot):
        state = snapshot()
        if not isinstance(state, Mapping):
            raise VLAContractError("VLA snapshot must be a mapping")
        return copy.deepcopy(dict(state))
    if getattr(adapter, "stateless", None) is True:
        return {"stateless": True}
    raise VLAContractError("VLA adapter cannot be snapshotted")


def restore_adapter(adapter: Any, state: Mapping[str, Any]) -> None:
    restore = getattr(adapter, "restore", None)
    if callable(restore):
        restore(copy.deepcopy(dict(state)))
    elif getattr(adapter, "stateless", None) is not True or state != {"stateless": True}:
        raise VLAContractError("VLA adapter cannot restore supplied state")


def load_vla_adapter(factory: str, *, config: Mapping[str, Any] | None = None,
                     formal: bool = True) -> VLAAdapter:
    if not isinstance(factory, str) or factory.count(":") != 1:
        raise VLAContractError("VLA factory must be module:factory")
    module_name, function_name = factory.split(":")
    if not module_name or not function_name:
        raise VLAContractError("VLA factory must be module:factory")
    try:
        builder = getattr(importlib.import_module(module_name), function_name)
    except (ImportError, AttributeError) as exc:
        raise VLAAdapterUnavailable(f"cannot import VLA factory {factory}: {exc}") from exc
    if not callable(builder):
        raise VLAContractError("VLA factory is not callable")
    try:
        adapter = builder(copy.deepcopy(dict(config or {})))
    except VLAAdapterUnavailable:
        raise
    except (ImportError, FileNotFoundError) as exc:
        raise VLAAdapterUnavailable(f"VLA factory dependency unavailable: {exc}") from exc
    try:
        require_vla_adapter(adapter, formal=formal)
    except BaseException:
        close = getattr(adapter, "close", None)
        if callable(close):
            close()
        raise
    return adapter


def _instruction(value: Mapping[str, Any]) -> str:
    for key in ("instruction", "language", "prompt"):
        text = value.get(key)
        if isinstance(text, str) and text.strip():
            return text.strip()
    raise VLAContractError("compiled instruction requires explicit nonempty instruction text")


class NativeOpenVLAAdapter:
    """Reuse CoPE's production loader, but call only observation-to-action code.

    No simulator object is accepted or retained. The standard OpenVLA model is
    autoregressively decoded per observation and has no cross-call policy state.
    Instruction and seed are still persisted to preserve episode continuation.
    """

    provider_id = "openvla_native"
    version = "native_openvla_observation_client_v1"
    learned_policy = True
    uses_privileged_state = False
    uses_hidden_canonical_state = False
    uses_privileged_simulator_state = False
    stateless = True

    def __init__(self, *, model: Any, processor: Any, model_config: Any,
                 get_action: Any, identity: Mapping[str, Any]):
        self._model = model
        self._processor = processor
        self._model_config = model_config
        self._get_action = get_action
        self.identity = dict(identity)
        self._instruction = ""
        self._seed = 0
        self._closed = False

    def reset(self, *, task: Mapping[str, Any], seed: int,
              initial_observation: Mapping[str, Any]) -> None:
        public_observation(initial_observation)
        if type(seed) is not int:
            raise VLAContractError("policy seed must be an integer")
        self._instruction = _instruction(task)
        self._seed = seed
        self._seed_torch(seed)

    @staticmethod
    def _seed_torch(seed: int) -> None:
        torch = sys.modules.get("torch")
        if torch is None:
            return  # dependency-free injected-client tests
        # torch.manual_seed seeds all CUDA devices. Use the CPU generator and
        # only the already initialized local cuda:0 selected by the factory.
        torch.random.default_generator.manual_seed(seed)
        if torch.cuda.is_initialized():
            torch.cuda.default_generators[0].manual_seed(seed)

    @staticmethod
    def _torch_snapshot() -> Mapping[str, Any] | None:
        torch = sys.modules.get("torch")
        if torch is None:
            return None
        result = {"cpu": torch.get_rng_state().tolist()}
        if torch.cuda.is_initialized():
            result["cuda_0"] = torch.cuda.get_rng_state(device=0).cpu().tolist()
        return result

    @staticmethod
    def _restore_torch(state: Mapping[str, Any] | None) -> None:
        if state is None:
            return
        torch = sys.modules.get("torch")
        if torch is None:
            raise VLAAdapterUnavailable("Torch is required to restore native VLA RNG")
        if set(state) - {"cpu", "cuda_0"} or "cpu" not in state:
            raise VLAContractError("invalid native Torch RNG snapshot")
        torch.set_rng_state(torch.tensor(state["cpu"], dtype=torch.uint8, device="cpu"))
        if "cuda_0" in state:
            if not torch.cuda.is_initialized():
                raise VLAAdapterUnavailable("selected CUDA device must already be initialized before restore")
            torch.cuda.set_rng_state(torch.tensor(state["cuda_0"], dtype=torch.uint8,
                                                  device="cpu"), device=0)

    def begin_subgoal(self, compiled_instruction: Mapping[str, Any]) -> None:
        self._instruction = _instruction(compiled_instruction)

    def act(self, observation: Mapping[str, Any]) -> ActionChunk:
        if self._closed:
            raise VLAContractError("VLA adapter is closed")
        if not self._instruction:
            raise VLAContractError("VLA adapter requires reset or begin_subgoal before act")
        public = public_observation(observation)
        if "full_image" not in public:
            raise VLAContractError("OpenVLA requires a public rendered full_image")
        inputs = {key: public[key] for key in ("full_image", "wrist_image", "state") if key in public}
        # Journal snapshots contain JSON arrays. The audited production client
        # calls PIL.Image.fromarray, which cannot consume restored Python lists.
        # Reconstruct only sensor arrays, never simulator fields or object poses.
        try:
            numpy = importlib.import_module("numpy")
        except ImportError as exc:
            raise VLAAdapterUnavailable("NumPy is required by the native OpenVLA client") from exc
        for name in ("full_image", "wrist_image"):
            if name not in inputs:
                continue
            try:
                value = numpy.asarray(inputs[name])
            except (ValueError, TypeError) as exc:
                raise VLAContractError(f"{name} must be a rectangular RGB image") from exc
            if (value.ndim != 3 or value.shape[2] != 3 or min(value.shape[:2]) < 1 or
                    numpy.any(value < 0) or numpy.any(value > 255) or
                    numpy.any(value != numpy.floor(value))):
                raise VLAContractError(f"{name} must contain HxWx3 integer RGB values in 0..255")
            inputs[name] = value.astype(numpy.uint8, copy=True)
        if "state" in inputs:
            inputs["state"] = numpy.asarray(inputs["state"], dtype=float)
        raw = self._get_action(self._model_config, self._model, inputs,
                               self._instruction, processor=self._processor)
        # The audited base OpenVLA client returns one 7-D action; chunk clients
        # return Hx7. Gripper conversion remains the common executor's job.
        if hasattr(raw, "tolist"):
            raw = raw.tolist()
        if isinstance(raw, (list, tuple)) and raw and isinstance(raw[0], numbers.Real):
            raw = [raw]
        return validate_action_chunk(raw, action_dim=self.identity["action_dim"],
                                     max_horizon=self.identity["max_chunk_horizon"])

    def snapshot(self) -> Mapping[str, Any]:
        return {"version": 1, "instruction": self._instruction, "seed": self._seed,
                "checkpoint_sha256": self.identity["checkpoint_sha256"],
                "torch_rng": self._torch_snapshot()}

    def restore(self, state: Mapping[str, Any]) -> None:
        if state.get("version") != 1 or state.get("checkpoint_sha256") != self.identity["checkpoint_sha256"]:
            raise VLAContractError("VLA snapshot identity mismatch")
        if not isinstance(state.get("instruction"), str) or type(state.get("seed")) is not int:
            raise VLAContractError("invalid VLA snapshot")
        self._instruction = state["instruction"]
        self._seed = state["seed"]
        self._restore_torch(state.get("torch_rng"))

    def close(self) -> None:
        self._closed = True
        self._model = None
        self._processor = None


def validate_native_openvla_assets(config: Mapping[str, Any]) -> Mapping[str, Any]:
    """Verify checkpoint/runtime bytes without importing Torch or touching a GPU."""
    checkpoint = Path(str(config.get("checkpoint_path", ""))).expanduser()
    runtime = Path(str(config.get("runtime_path", "/home/lijingsu/vla/src/openvla"))).expanduser()
    if not checkpoint.is_dir() or not (checkpoint / "config.json").is_file():
        raise VLAAdapterUnavailable(f"local OpenVLA checkpoint missing: {checkpoint}")
    if not (runtime / "experiments/robot/robot_utils.py").is_file():
        raise VLAAdapterUnavailable(f"production OpenVLA runtime unavailable: {runtime}")
    expected = config.get("checkpoint_sha256")
    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise VLAContractError("native factory requires pinned checkpoint_sha256")
    actual = checkpoint_sha256(checkpoint)
    if actual != expected:
        raise VLAContractError("native checkpoint content hash mismatch")
    return {
        "provider_id": NativeOpenVLAAdapter.provider_id,
        "version": NativeOpenVLAAdapter.version,
        "uses_hidden_canonical_state": False,
        "uses_privileged_simulator_state": False,
        "input_schema_hash": _contract_hash(("rgb", "instruction")),
        "output_schema_hash": _contract_hash(("finite_action_chunk_1x7",)),
        "policy_model_id": str(config.get("policy_model_id", "openvla-7b-finetuned-libero-10")),
        "adapter_type": "native_openvla_observation_client",
        "checkpoint_sha256": actual, "checkpoint_path": str(checkpoint.resolve()),
        "runtime_path": str(runtime.resolve()),
        "runtime_client_sha256": checkpoint_sha256(runtime / "experiments/robot/robot_utils.py"),
        "runtime_inference_sha256": checkpoint_sha256(runtime / "experiments/robot/openvla_utils.py"),
        "action_dim": 7, "max_chunk_horizon": 1,
        "action_space": "openvla_raw_normalize_binarize_then_invert_gripper",
        "model_consumes_proprio": False, "deterministic_decoding": True,
        "learned_policy": True, "uses_privileged_state": False,
    }


def create_native_openvla(config: Mapping[str, Any]) -> NativeOpenVLAAdapter:
    """Factory for ``...vla_adapter:create_native_openvla``; no downloads.

    Required: checkpoint_path, checkpoint_sha256, runtime_path. GPU selection
    checks nvidia-smi and rejects active processes or >5% utilization. The
    default check allows up to 256 MiB of idle driver memory.
    """
    assets = dict(validate_native_openvla_assets(config))
    checkpoint = Path(assets["checkpoint_path"])
    runtime = Path(assets["runtime_path"])
    # Checking metadata and deps above never starts inference or touches a GPU.
    gpu = str(config.get("gpu", "0"))
    try:
        query = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid,utilization.gpu,memory.used",
                                "--format=csv,noheader,nounits"], check=True, capture_output=True,
                               text=True, timeout=10)
        rows = [tuple(part.strip() for part in line.split(",")) for line in query.stdout.splitlines()]
        selected = next((row for row in rows if len(row) == 4 and row[0] == gpu), None)
        if selected is None or float(selected[2]) > 5 or float(selected[3]) > 256:
            raise VLAAdapterUnavailable(f"requested GPU {gpu} is absent or not idle")
        processes = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid",
                                    "--format=csv,noheader,nounits"], check=True, capture_output=True,
                                   text=True, timeout=10)
        if any(line.split(",")[0].strip() == selected[1] for line in processes.stdout.splitlines()):
            raise VLAAdapterUnavailable(f"requested GPU {gpu} has another compute process")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise VLAAdapterUnavailable(f"cannot verify idle GPU: {exc}") from exc
    # get_model uses cuda:0; map the one verified idle physical GPU before Torch
    # is imported. Changing an initialized Torch process is unsafe.
    if "torch" in sys.modules:
        raise VLAAdapterUnavailable("load native VLA in a fresh worker before importing torch")
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    runtime_text = str(runtime.resolve())
    if runtime_text not in sys.path:
        sys.path.insert(0, runtime_text)
    try:
        from libero_experiment_core import ExperimentConfig, load_model_and_processor
        from experiments.robot import robot_utils
        if not Path(robot_utils.__file__).resolve().is_relative_to(runtime.resolve()):
            raise VLAAdapterUnavailable("an already imported OpenVLA client shadows the pinned runtime")
        get_action = robot_utils.get_action
        cfg = ExperimentConfig(checkpoint=str(checkpoint.resolve()),
                               task_suite=str(config.get("task_suite", "libero_10")),
                               unnorm_key=str(config.get("unnorm_key", "libero_10")))
        model, processor, model_config, resolved_key = load_model_and_processor(cfg)
    except (ImportError, OSError, RuntimeError) as exc:
        raise VLAAdapterUnavailable(f"production OpenVLA dependencies unavailable: {exc}") from exc
    return NativeOpenVLAAdapter(model=model, processor=processor, model_config=model_config,
                               get_action=get_action, identity={
        **assets, "runtime_path": runtime_text, "unnorm_key": resolved_key,
    })
