#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope.calibration import (  # noqa: E402
    atomic_episode_claim,
    canonical_hash,
    partition_entries,
    validate_openvla_action,
)
from cope.calibration_v2 import (  # noqa: E402
    PROTOCOL_LABEL,
    TASK_IDS,
    WORKER_COUNT,
    audit_v2_terminals,
    build_v2_entries,
    ensure_output_separation,
    infrastructure_attempts,
    load_v2_resume_trace,
    read_jsonl,
    sha256_file,
    summarize_v2,
    validate_config_contract,
    validate_runtime_files,
    validate_runtime_task_identity,
    validate_static_manifest,
    validate_v1_integrity,
)
from experiments.openvla_libero_calibration import (  # noqa: E402
    _action_spec,
    _atomic_json,
    _checkpoint_identity,
    _cuda_memory,
    _exclusive_json,
    _git_identity,
    _load_yaml,
    _model_cfg,
    _observation_summary,
)
from libero_experiment_core import (  # noqa: E402
    create_libero_env,
    execute_policy_step,
    frame_from_obs,
    get_benchmark_suite,
    get_dummy_action,
    get_image_resize_size,
    load_model_and_processor,
    set_seed,
)


DEFAULT_CONFIG = ROOT / "configs/openvla_libero_10_calibration_v2.yaml"
DEFAULT_STATIC_MANIFEST = ROOT / "manifests/openvla_libero_10_calibration_v2.jsonl"


def _episode_roots(root: Path) -> list[Path]:
    return [
        root / "workers" / f"gpu{worker_id}" / "episodes"
        for worker_id in range(WORKER_COUNT)
    ]


def _load_run_context(root: Path) -> tuple[dict[str, Any], dict[str, Any], tuple[dict[str, Any], ...]]:
    run_manifest = json.loads(
        (root / "run_manifest_v2.json").read_text(encoding="utf-8")
    )
    config = _load_yaml(Path(str(run_manifest["config_path"])))
    validate_config_contract(config)
    config_hash = canonical_hash(config)
    if config_hash != run_manifest["config_hash"]:
        raise ValueError("calibration v2 config hash mismatch")
    static_manifest_path = Path(str(run_manifest["static_manifest_path"]))
    entries = validate_static_manifest(config, static_manifest_path)
    if sha256_file(static_manifest_path) != run_manifest["static_manifest_sha256"]:
        raise ValueError("calibration v2 static manifest hash mismatch")
    if list(entries) != run_manifest["entries"]:
        raise ValueError("calibration v2 run manifest entries changed")
    return run_manifest, config, entries


def _validate_no_existing_result_corruption(
    *, root: Path, config: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]
) -> set[str]:
    audit = audit_v2_terminals(
        config=config,
        entries=entries,
        episode_roots=_episode_roots(root),
        config_hash=canonical_hash(config),
    )
    non_missing_errors = [
        error
        for error in audit["errors"]
        if not error.startswith("missing terminal episode IDs:")
    ]
    if non_missing_errors:
        raise ValueError(f"existing v2 result corruption: {non_missing_errors}")
    return {str(record["episode_id"]) for record in audit["terminals"]}


def prepare(
    *,
    config_path: Path,
    static_manifest_path: Path,
    output_root: Path,
    resume: bool,
) -> dict[str, Any]:
    config = _load_yaml(config_path)
    validate_config_contract(config)
    config_hash = canonical_hash(config)
    entries = validate_static_manifest(config, static_manifest_path)
    protected_root, output_root = ensure_output_separation(
        v1_root=config["v1_protection"]["path"], v2_root=output_root
    )
    ensure_output_separation(
        v1_root=config["v1_protection"]["parallel_path"], v2_root=output_root
    )
    git = _git_identity()
    if not git["clean"]:
        raise RuntimeError(f"calibration v2 prepare requires a clean worktree:\n{git['status']}")
    v1_before = validate_v1_integrity(config)
    runtime_tasks = validate_runtime_task_identity(config)
    runtime_files = validate_runtime_files(config)
    checkpoint = _checkpoint_identity(config)
    run_manifest_path = output_root / "run_manifest_v2.json"
    launcher_id = "calibration-v2-" + canonical_hash(
        {
            "config_hash": config_hash,
            "static_manifest_sha256": sha256_file(static_manifest_path),
            "git_commit": git["commit"],
            "worker_count": WORKER_COUNT,
        }
    )[:16]
    manifest = {
        "schema_version": "openvla-libero-calibration-v2-run-manifest",
        "protocol_label": PROTOCOL_LABEL,
        "launcher_id": launcher_id,
        "worker_count": WORKER_COUNT,
        "config_path": str(config_path.resolve()),
        "config_hash": config_hash,
        "static_manifest_path": str(static_manifest_path.resolve()),
        "static_manifest_sha256": sha256_file(static_manifest_path),
        "entries": list(entries),
        "partition": {
            str(worker_id): [
                str(entry["episode_id"])
                for entry in partition_entries(
                    entries, worker_id=worker_id, worker_count=WORKER_COUNT
                )
            ]
            for worker_id in range(WORKER_COUNT)
        },
        "git": git,
        "checkpoint": checkpoint,
        "runtime_files": runtime_files,
        "runtime_task_identity": runtime_tasks,
        "v1_protection": {
            "protected_root": str(protected_root),
            "before": v1_before,
            "protocol_label": config["v1_protection"]["protocol_label"],
        },
        "invariants": {
            "task_ids": list(TASK_IDS),
            "initial_state_ids": list(config["initial_state_ids"]),
            "warmup_simulator_steps": 10,
            "policy_step_budget": 520,
            "total_environment_step_budget": 530,
            "atomic_o_excl_claim": True,
            "atomic_terminal_json": True,
            "independent_worker_directories": True,
            "one_model_per_worker": True,
            "shared_inference_server": False,
            "infrastructure_failures_are_not_terminals": True,
            "completed_entries_never_reinferred": True,
            "selective_reruns_forbidden": True,
        },
        "prepared_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if run_manifest_path.exists():
        if not resume:
            raise FileExistsError(f"v2 run manifest already exists: {run_manifest_path}")
        existing = json.loads(run_manifest_path.read_text(encoding="utf-8"))
        identity_fields = (
            "schema_version",
            "protocol_label",
            "launcher_id",
            "worker_count",
            "config_hash",
            "static_manifest_sha256",
            "entries",
            "partition",
            "checkpoint",
        )
        if any(existing.get(field) != manifest[field] for field in identity_fields):
            raise ValueError("calibration v2 prepare resume identity mismatch")
        return existing
    output_root.mkdir(parents=True, exist_ok=False)
    for child in ("claims", "completions", "workers", "logs", "evidence"):
        (output_root / child).mkdir()
    _exclusive_json(run_manifest_path, manifest)
    return manifest


def _tensor_hashes(batch: Mapping[str, Any]) -> dict[str, Any]:
    hashes: dict[str, Any] = {}
    for key, value in batch.items():
        if hasattr(value, "detach"):
            tensor = value.detach().cpu().contiguous()
            raw = tensor.view(__import__("torch").uint8).numpy().tobytes()
            hashes[str(key)] = {
                "shape": list(tensor.shape),
                "dtype": str(tensor.dtype),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        else:
            encoded = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
            hashes[str(key)] = {
                "type": f"{type(value).__module__}.{type(value).__qualname__}",
                "sha256": hashlib.sha256(encoded).hexdigest(),
            }
    return hashes


def _official_processor_input(
    *, processor: Any, frame: np.ndarray, task_description: str
) -> dict[str, Any]:
    import tensorflow as tf
    from PIL import Image
    from experiments.robot.openvla_utils import crop_and_resize

    image: Any = Image.fromarray(frame).convert("RGB")
    tensor = tf.convert_to_tensor(np.array(image))
    original_dtype = tensor.dtype
    tensor = tf.image.convert_image_dtype(tensor, tf.float32)
    tensor = crop_and_resize(tensor, 0.9, 1)
    tensor = tf.clip_by_value(tensor, 0, 1)
    tensor = tf.image.convert_image_dtype(tensor, original_dtype, saturate=True)
    image = Image.fromarray(tensor.numpy()).convert("RGB")
    prompt = (
        f"In: What action should the robot take to {task_description.lower()}?\nOut:"
    )
    batch = processor(prompt, image)
    image_array = np.asarray(image, dtype=np.uint8)
    return {
        "prompt": prompt,
        "image_shape": list(image_array.shape),
        "image_sha256": hashlib.sha256(image_array.tobytes()).hexdigest(),
        "batch": _tensor_hashes(batch),
    }


class _CapturingProcessor:
    def __init__(self, processor: Any):
        self.processor = processor
        self.capture: dict[str, Any] | None = None

    def __call__(self, prompt: str, image: Any) -> Any:
        batch = self.processor(prompt, image)
        image_array = np.asarray(image, dtype=np.uint8)
        self.capture = {
            "prompt": prompt,
            "image_shape": list(image_array.shape),
            "image_sha256": hashlib.sha256(image_array.tobytes()).hexdigest(),
            "batch": _tensor_hashes(batch),
        }
        return batch


def parity(*, output_root: Path) -> dict[str, Any]:
    run_manifest, config, entries = _load_run_context(output_root)
    parity_path = output_root / "parity_report.json"
    if parity_path.exists():
        existing = json.loads(parity_path.read_text(encoding="utf-8"))
        if existing.get("passed") is not True:
            raise ValueError("existing calibration v2 parity report failed")
        return existing
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if not visible or "," in visible:
        raise RuntimeError("parity requires exactly one visible GPU")
    validate_v1_integrity(config)
    runtime_tasks = validate_runtime_task_identity(config)
    validate_runtime_files(config)
    checkpoint = _checkpoint_identity(config)
    if checkpoint != run_manifest["checkpoint"]:
        raise ValueError("parity checkpoint identity differs from prepared manifest")
    entry = dict(entries[0])
    task_id = int(entry["task_id"])
    state_id = int(entry["initial_state_id"])
    seed = int(entry["seed"])
    cfg = _model_cfg(config, task_id=task_id, state_id=state_id, seed=seed)
    model, processor, runtime_model_cfg, resolved_unnorm_key = load_model_and_processor(
        cfg
    )
    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(task_id)
    initial_state = suite.get_task_init_states(task_id)[state_id]
    state_sha256 = hashlib.sha256(np.asarray(initial_state).tobytes()).hexdigest()
    env = None
    try:
        set_seed(seed)
        env, prompt = create_libero_env(task, cfg)
        env.reset()
        obs = env.set_init_state(initial_state)
        reset_frame = np.asarray(obs["agentview_image"], dtype=np.uint8)
        for _ in range(10):
            obs, _, _, _ = env.step(get_dummy_action("openvla"))
        resize_size = get_image_resize_size(runtime_model_cfg)
        from experiments.robot.libero.libero_utils import get_libero_image

        official_frame = np.asarray(
            get_libero_image(obs, resize_size), dtype=np.uint8
        )
        adapter_frame = frame_from_obs(obs, resize_size)
        official_input = _official_processor_input(
            processor=processor, frame=official_frame, task_description=prompt
        )
        capturing_processor = _CapturingProcessor(processor)
        low, high, action_spec_source = _action_spec(
            env, int(checkpoint["action_dim"])
        )
        step = execute_policy_step(
            cfg=runtime_model_cfg,
            model=model,
            processor=capturing_processor,
            env=env,
            obs=obs,
            prompt=prompt,
            resize_size=resize_size,
        )
        action_validation = validate_openvla_action(
            step.raw_action,
            step.env_action,
            expected_dim=int(checkpoint["action_dim"]),
            action_low=low,
            action_high=high,
        )
        adapter_input = capturing_processor.capture or {}
        gates = {
            "runtime_description_exact": prompt == entry["description"],
            "task_name_exact": task.name == entry["task_name"],
            "bddl_identity_exact": (
                runtime_tasks["task_identity"][str(task_id)]["bddl_sha256"]
                == entry["bddl_sha256"]
            ),
            "initial_state_exact": state_sha256 == entry["initial_state_sha256"],
            "camera_is_agentview": "agentview_image" in obs,
            "camera_orientation_and_resize_exact": bool(
                np.array_equal(official_frame, adapter_frame)
            ),
            "official_adapter_frame_hash_exact": (
                hashlib.sha256(official_frame.tobytes()).hexdigest()
                == hashlib.sha256(adapter_frame.tobytes()).hexdigest()
            ),
            "center_crop_exact": official_input.get("image_sha256")
            == adapter_input.get("image_sha256"),
            "processor_prompt_exact": official_input.get("prompt")
            == adapter_input.get("prompt"),
            "processor_tensor_hashes_exact": official_input.get("batch")
            == adapter_input.get("batch"),
            "unnorm_key_exact": resolved_unnorm_key == "libero_10",
            "action_valid": action_validation["passed"],
            "real_inference_and_env_step": (
                step.inference_seconds > 0 and step.env_step_seconds > 0
            ),
            "adapter_state_is_8d": _observation_summary(
                obs, adapter_frame
            )["proprio_shape"]
            == [8],
            "model_proprio_not_consumed": (
                config["runtime"]["model_consumes_proprio"] is False
                and "state" not in (official_input.get("batch") or {})
                and "state" not in (adapter_input.get("batch") or {})
            ),
            "gripper_official_normalize_and_invert": action_validation["gates"][
                "gripper_normalize_binarize_invert"
            ],
            "one_visible_gpu": __import__("torch").cuda.device_count() == 1,
            "no_shared_inference_port": True,
        }
        report = {
            "schema_version": "openvla-libero-calibration-v2-parity-v1",
            "passed": all(gates.values()),
            "protocol_label": PROTOCOL_LABEL,
            "config_hash": run_manifest["config_hash"],
            "entry": entry,
            "runtime_description_supplied_to_model": prompt,
            "warmup_steps_before_inference": 10,
            "reset_agentview_sha256": hashlib.sha256(
                reset_frame.tobytes()
            ).hexdigest(),
            "official_frame_sha256": hashlib.sha256(
                official_frame.tobytes()
            ).hexdigest(),
            "adapter_frame_sha256": hashlib.sha256(
                adapter_frame.tobytes()
            ).hexdigest(),
            "official_processor_input": official_input,
            "adapter_processor_input": adapter_input,
            "action_validation": action_validation,
            "action_spec_source": action_spec_source,
            "reward_after_step": step.reward,
            "done_after_step": step.done,
            "inference_seconds": step.inference_seconds,
            "environment_step_seconds": step.env_step_seconds,
            "checkpoint": checkpoint,
            "processor_loader": getattr(
                runtime_model_cfg, "processor_loader", "unrecorded"
            ),
            "gpu": _cuda_memory(),
            "gates": gates,
        }
        _atomic_json(parity_path, report)
        if not report["passed"]:
            raise RuntimeError(f"calibration v2 parity failed: {gates}")
        return report
    finally:
        if env is not None:
            env.close()


def _next_attempt_number(episode_dir: Path) -> int:
    numbers: set[int] = set()
    for path in episode_dir.glob("attempt-*.*"):
        try:
            numbers.add(int(path.name.split("-", 1)[1].split(".", 1)[0]))
        except (IndexError, ValueError):
            continue
    return max(numbers, default=0) + 1


def _latest_valid_resume_trace(
    episode_dir: Path, *, enabled: bool
) -> dict[str, Any] | None:
    if not enabled:
        return None
    for path in reversed(sorted(episode_dir.glob("attempt-*.jsonl"))):
        try:
            return load_v2_resume_trace(path)
        except (ValueError, json.JSONDecodeError):
            continue
    return None


def _write_trace_line(handle: Any, record: Mapping[str, Any]) -> None:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def _run_episode(
    *,
    entry: Mapping[str, Any],
    config: Mapping[str, Any],
    config_hash: str,
    worker_root: Path,
    model: Any,
    processor: Any,
    runtime_model_cfg: Any,
    resolved_unnorm_key: str,
    checkpoint: Mapping[str, Any],
    attempt_number: int,
    resume_trace: Mapping[str, Any] | None,
) -> dict[str, Any]:
    episode_id = str(entry["episode_id"])
    episode_dir = worker_root / "episodes" / episode_id
    episode_dir.mkdir(parents=True, exist_ok=True)
    episode_path = episode_dir / "episode.json"
    if episode_path.exists():
        raise FileExistsError(f"completed entry cannot be re-inferred: {episode_id}")
    trace_path = episode_dir / f"attempt-{attempt_number:03d}.jsonl"
    task_id = int(entry["task_id"])
    state_id = int(entry["initial_state_id"])
    seed = int(entry["seed"])
    cfg = _model_cfg(config, task_id=task_id, state_id=state_id, seed=seed)
    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(task_id)
    if task.name != entry["task_name"] or task.language != entry["description"]:
        raise ValueError("task mapping changed after manifest preparation")
    initial_state = suite.get_task_init_states(task_id)[state_id]
    state_sha256 = hashlib.sha256(np.asarray(initial_state).tobytes()).hexdigest()
    if state_sha256 != entry["initial_state_sha256"]:
        raise ValueError("initial state changed after manifest preparation")
    runtime = config["runtime"]
    warmup_budget = int(runtime["warmup_simulator_steps"])
    policy_budget = int(runtime["policy_step_budget"])
    env = None
    started = time.monotonic()
    steps: list[dict[str, Any]] = (
        [dict(row) for row in resume_trace["policy_records"]]
        if resume_trace is not None
        else []
    )
    newly_inferred = 0
    success = False
    termination_reason = "policy_step_budget_exhausted"
    reward = 0.0
    done = False
    info: dict[str, Any] = {}
    prompt = ""
    observation_initial: dict[str, Any] = {}
    action_spec_source = ""
    try:
        set_seed(seed)
        env, prompt = create_libero_env(task, cfg)
        if prompt != entry["description"]:
            raise ValueError("runtime prompt differs from canonical task description")
        env.reset()
        obs = env.set_init_state(initial_state)
        resize_size = get_image_resize_size(runtime_model_cfg)
        observation_initial = _observation_summary(
            obs, frame_from_obs(obs, resize_size)
        )
        low, high, action_spec_source = _action_spec(
            env, int(checkpoint["action_dim"])
        )
        with trace_path.open("x", encoding="utf-8", buffering=1) as trace:
            if resume_trace is not None:
                _write_trace_line(
                    trace,
                    {
                        "record_type": "resume_replay",
                        "source_trace": resume_trace["path"],
                        "source_trace_sha256": resume_trace["sha256"],
                        "policy_steps_replayed": resume_trace["policy_steps"],
                        "model_inference_replayed": False,
                    },
                )
            expected_warmup = (
                resume_trace["warmup_records"] if resume_trace is not None else None
            )
            for warmup_step in range(warmup_budget):
                obs, reward, done, info = env.step(get_dummy_action("openvla"))
                if expected_warmup is not None:
                    expected = expected_warmup[warmup_step]
                    if bool(done) != bool(expected["done"]) or abs(
                        float(reward) - float(expected["reward"])
                    ) > 1e-9:
                        raise RuntimeError(
                            f"resume warmup replay diverged at step {warmup_step}"
                        )
                _write_trace_line(
                    trace,
                    {
                        "record_type": "warmup",
                        "warmup_step": warmup_step,
                        "dummy_action": True,
                        "policy_inference": False,
                        "replayed": resume_trace is not None,
                        "reward": float(reward),
                        "done": bool(done),
                    },
                )
            if resume_trace is not None:
                for prior in resume_trace["policy_records"]:
                    obs, replay_reward, replay_done, replay_info = env.step(
                        prior["environment_action"]
                    )
                    policy_step = int(prior["policy_step"])
                    if bool(replay_done) != bool(prior["done"]) or abs(
                        float(replay_reward) - float(prior["reward"])
                    ) > 1e-9:
                        raise RuntimeError(
                            f"resume policy replay diverged at step {policy_step}"
                        )
                    reward = float(replay_reward)
                    done = bool(replay_done)
                    info = dict(replay_info)
                    _write_trace_line(
                        trace,
                        {
                            **prior,
                            "record_type": "policy_step",
                            "replayed": True,
                            "model_inference_replayed": False,
                            "reward": reward,
                            "done": done,
                        },
                    )
                if resume_trace["terminal_success_recorded"]:
                    success = True
                    termination_reason = (
                        "libero_done"
                        if done
                        else "libero_sparse_reward_ge_1"
                    )
            if not success:
                for policy_step in range(len(steps), policy_budget):
                    step = execute_policy_step(
                        cfg=runtime_model_cfg,
                        model=model,
                        processor=processor,
                        env=env,
                        obs=obs,
                        prompt=prompt,
                        resize_size=resize_size,
                    )
                    newly_inferred += 1
                    obs = step.next_obs
                    reward = step.reward
                    done = step.done
                    info = dict(step.info)
                    validation = validate_openvla_action(
                        step.raw_action,
                        step.env_action,
                        expected_dim=int(checkpoint["action_dim"]),
                        action_low=low,
                        action_high=high,
                    )
                    row = {
                        "record_type": "policy_step",
                        "policy_step": policy_step,
                        "raw_action": step.raw_action,
                        "environment_action": step.env_action,
                        "action_validation": validation,
                        "reward": reward,
                        "done": done,
                        "inference_seconds": step.inference_seconds,
                        "environment_step_seconds": step.env_step_seconds,
                        "replayed": False,
                    }
                    steps.append(row)
                    _write_trace_line(trace, row)
                    if not validation["passed"]:
                        raise RuntimeError("OpenVLA action contract failed during v2")
                    if done or reward >= 1.0:
                        success = True
                        termination_reason = (
                            "libero_done"
                            if done
                            else "libero_sparse_reward_ge_1"
                        )
                        break
                else:
                    termination_reason = "policy_step_budget_exhausted"
    finally:
        if env is not None:
            env.close()
    result = {
        "schema_version": "openvla-libero-clean-calibration-v2-episode",
        "complete": True,
        "valid_experimental_terminal": True,
        "infrastructure_failure": False,
        "phase": "calibration",
        "protocol_label": PROTOCOL_LABEL,
        "evidence_admissibility": "feasibility_screening_only_not_cope_evidence",
        "episode_id": episode_id,
        "task_suite": "libero_10",
        "task_id": task_id,
        "task_name": entry["task_name"],
        "description": entry["description"],
        "bddl_file": entry["bddl_file"],
        "bddl_sha256": entry["bddl_sha256"],
        "initial_state_id": state_id,
        "initial_state_sha256": state_sha256,
        "seed": seed,
        "task_prompt_supplied_to_model": prompt,
        "config_hash": config_hash,
        "checkpoint": {
            "path": checkpoint["path"],
            "revision": checkpoint["revision"],
            "unnorm_key": resolved_unnorm_key,
        },
        "observation_initial": observation_initial,
        "action_spec_source": action_spec_source,
        "warmup_steps_consumed": warmup_budget,
        "policy_step_budget": policy_budget,
        "policy_steps_consumed": len(steps),
        "policy_steps_inferred_this_attempt": newly_inferred,
        "environment_steps_consumed": warmup_budget + len(steps),
        "success": success,
        "termination_reason": termination_reason,
        "final_reward": float(reward),
        "final_done": bool(done),
        "final_info": info,
        "action_schema_valid": all(
            bool(item["action_validation"]["passed"]) for item in steps
        ),
        "runtime_seconds": time.monotonic() - started,
        "gpu": _cuda_memory(),
        "adapter_state_dim": 8,
        "model_consumes_proprio": False,
        "manual_intervention": False,
        "selective_rerun": False,
        "resumed_from_interrupted_trace": resume_trace is not None,
        "resume": (
            {
                "source_trace": resume_trace["path"],
                "source_trace_sha256": resume_trace["sha256"],
                "policy_steps_replayed": resume_trace["policy_steps"],
                "model_inference_replayed": False,
            }
            if resume_trace is not None
            else None
        ),
        "attempt_number": attempt_number,
        "artifacts": {
            "trace": str(trace_path.resolve()),
            "episode": str(episode_path.resolve()),
        },
    }
    _atomic_json(episode_path, result)
    return result


def worker(*, output_root: Path, worker_id: int, resume: bool) -> dict[str, Any]:
    run_manifest, config, entries = _load_run_context(output_root)
    if worker_id < 0 or worker_id >= WORKER_COUNT:
        raise ValueError("invalid v2 worker ID")
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if visible != str(worker_id) or "," in visible:
        raise RuntimeError("v2 worker requires an exact one-GPU physical mapping")
    parity_report = json.loads(
        (output_root / "parity_report.json").read_text(encoding="utf-8")
    )
    if (
        parity_report.get("passed") is not True
        or parity_report.get("config_hash") != run_manifest["config_hash"]
        or (parity_report.get("checkpoint") or {}).get("revision")
        != config["checkpoint"]["revision"]
    ):
        raise ValueError("worker refused because parity evidence is missing or stale")
    validate_v1_integrity(config)
    validate_runtime_task_identity(config)
    validate_runtime_files(config)
    terminal_ids = _validate_no_existing_result_corruption(
        root=output_root, config=config, entries=entries
    )
    assigned = partition_entries(
        entries, worker_id=worker_id, worker_count=WORKER_COUNT
    )
    pending = [
        entry for entry in assigned if str(entry["episode_id"]) not in terminal_ids
    ]
    worker_root = output_root / "workers" / f"gpu{worker_id}"
    worker_root.mkdir(parents=True, exist_ok=True)
    summary_path = worker_root / "worker_summary.json"
    if not pending:
        if summary_path.is_file():
            return json.loads(summary_path.read_text(encoding="utf-8"))
        result = {
            "worker_id": worker_id,
            "physical_gpu": visible,
            "model_load_count": 0,
            "processed_episode_ids": [],
            "complete": True,
            "all_entries_already_complete": True,
        }
        _atomic_json(summary_path, result)
        return result
    loader_entry = pending[0]
    loader_cfg = _model_cfg(
        config,
        task_id=int(loader_entry["task_id"]),
        state_id=int(loader_entry["initial_state_id"]),
        seed=int(loader_entry["seed"]),
    )
    load_started = time.monotonic()
    try:
        model, processor, runtime_model_cfg, resolved_unnorm_key = (
            load_model_and_processor(loader_cfg)
        )
    except Exception as exc:
        load_attempts = sorted(worker_root.glob("attempt-load-*.json"))
        attempt_path = worker_root / f"attempt-load-{len(load_attempts) + 1:03d}.json"
        _atomic_json(
            attempt_path,
            {
                "schema_version": "calibration-v2-infrastructure-attempt-v1",
                "attempt_status": "infrastructure_failure",
                "failure_scope": "worker_model_or_processor_load",
                "worker_id": worker_id,
                "physical_gpu": visible,
                "valid_experimental_terminal": False,
                "exception": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            },
        )
        raise
    model_load_seconds = time.monotonic() - load_started
    checkpoint = dict(run_manifest["checkpoint"])
    processed: list[str] = []
    for entry in pending:
        episode_id = str(entry["episode_id"])
        terminal_ids = _validate_no_existing_result_corruption(
            root=output_root, config=config, entries=entries
        )
        if episode_id in terminal_ids:
            continue
        claim = atomic_episode_claim(
            output_root / "claims" / f"{episode_id}.json",
            episode_id=episode_id,
            worker_id=worker_id,
            worker_count=WORKER_COUNT,
            config_hash=run_manifest["config_hash"],
            launcher_id=run_manifest["launcher_id"],
            resume=resume,
        )
        episode_dir = worker_root / "episodes" / episode_id
        episode_dir.mkdir(parents=True, exist_ok=True)
        attempt_number = _next_attempt_number(episode_dir)
        attempt_path = episode_dir / f"attempt-{attempt_number:03d}.json"
        resume_trace = _latest_valid_resume_trace(episode_dir, enabled=resume)
        try:
            record = _run_episode(
                entry=entry,
                config=config,
                config_hash=run_manifest["config_hash"],
                worker_root=worker_root,
                model=model,
                processor=processor,
                runtime_model_cfg=runtime_model_cfg,
                resolved_unnorm_key=resolved_unnorm_key,
                checkpoint=checkpoint,
                attempt_number=attempt_number,
                resume_trace=resume_trace,
            )
        except Exception as exc:
            trace_path = episode_dir / f"attempt-{attempt_number:03d}.jsonl"
            _atomic_json(
                attempt_path,
                {
                    "schema_version": "calibration-v2-infrastructure-attempt-v1",
                    "attempt_status": "infrastructure_failure",
                    "episode_id": episode_id,
                    "worker_id": worker_id,
                    "physical_gpu": visible,
                    "config_hash": run_manifest["config_hash"],
                    "seed": entry["seed"],
                    "valid_experimental_terminal": False,
                    "trace": str(trace_path.resolve()) if trace_path.exists() else None,
                    "resume_source": (
                        resume_trace["path"] if resume_trace is not None else None
                    ),
                    "exception": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                },
            )
            raise
        _atomic_json(
            attempt_path,
            {
                "schema_version": "calibration-v2-valid-attempt-v1",
                "attempt_status": "valid_experimental_terminal",
                "episode_id": episode_id,
                "worker_id": worker_id,
                "physical_gpu": visible,
                "config_hash": run_manifest["config_hash"],
                "seed": entry["seed"],
                "valid_experimental_terminal": True,
                "success": record["success"],
                "termination_reason": record["termination_reason"],
                "trace": record["artifacts"]["trace"],
                "terminal": record["artifacts"]["episode"],
            },
        )
        completion = {
            "schema_version": "openvla-libero-calibration-v2-completion-v1",
            "episode_id": episode_id,
            "worker_id": worker_id,
            "physical_gpu": visible,
            "claim": claim,
            "terminal_path": record["artifacts"]["episode"],
            "attempt_path": str(attempt_path.resolve()),
            "success": record["success"],
            "termination_reason": record["termination_reason"],
        }
        _exclusive_json(
            output_root / "completions" / f"{episode_id}.json", completion
        )
        processed.append(episode_id)
        print(
            json.dumps(
                {
                    "worker_id": worker_id,
                    "physical_gpu": visible,
                    "episode_id": episode_id,
                    "success": record["success"],
                    "termination_reason": record["termination_reason"],
                    "policy_steps": record["policy_steps_consumed"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
    summary = {
        "schema_version": "openvla-libero-calibration-v2-worker-summary-v1",
        "worker_id": worker_id,
        "physical_gpu": visible,
        "model_load_count": 1,
        "model_load_seconds": model_load_seconds,
        "processor_loader": getattr(
            runtime_model_cfg, "processor_loader", "unrecorded"
        ),
        "shared_inference_server": False,
        "shared_inference_port": None,
        "processed_episode_ids": processed,
        "complete": True,
    }
    _atomic_json(summary_path, summary)
    return summary


def _v1_task1_comparison(config: Mapping[str, Any]) -> dict[str, Any]:
    roots = [
        Path(str(config["v1_protection"]["path"])) / "episodes",
        Path(str(config["v1_protection"]["parallel_path"])) / "workers",
    ]
    terminals: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("episode.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            if int(record.get("task_id", -1)) == 1:
                terminals.append(record)
    terminals.sort(key=lambda row: int(row["initial_state_id"]))
    return {
        "protocol_label": "nonstandard_truncated_calibration_horizon_220",
        "task_id": 1,
        "n": len(terminals),
        "successes": sum(bool(row["success"]) for row in terminals),
        "policy_step_budget": 220,
        "results": [
            {
                "initial_state_id": row["initial_state_id"],
                "seed": row["seed"],
                "success": row["success"],
                "termination_reason": row["termination_reason"],
                "policy_steps_consumed": row["policy_steps_consumed"],
            }
            for row in terminals
        ],
        "must_not_be_pooled_with_v2": True,
    }


def audit(*, output_root: Path) -> dict[str, Any]:
    run_manifest, config, entries = _load_run_context(output_root)
    v1_after = validate_v1_integrity(config)
    runtime_tasks = validate_runtime_task_identity(config)
    parity_report = json.loads(
        (output_root / "parity_report.json").read_text(encoding="utf-8")
    )
    terminal_audit = audit_v2_terminals(
        config=config,
        entries=entries,
        episode_roots=_episode_roots(output_root),
        config_hash=run_manifest["config_hash"],
    )
    claim_errors: list[str] = []
    claims: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        episode_id = str(entry["episode_id"])
        claim_path = output_root / "claims" / f"{episode_id}.json"
        if not claim_path.is_file():
            claim_errors.append(f"{episode_id}: missing atomic claim")
            continue
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        if int(claim.get("worker_id", -1)) != index % WORKER_COUNT:
            claim_errors.append(f"{episode_id}: worker partition mismatch")
        if claim.get("config_hash") != run_manifest["config_hash"]:
            claim_errors.append(f"{episode_id}: claim config hash mismatch")
        claims.append(claim)
    worker_errors: list[str] = []
    workers: list[dict[str, Any]] = []
    for worker_id in range(WORKER_COUNT):
        path = (
            output_root / "workers" / f"gpu{worker_id}" / "worker_summary.json"
        )
        if not path.is_file():
            worker_errors.append(f"gpu{worker_id}: missing worker summary")
            continue
        worker = json.loads(path.read_text(encoding="utf-8"))
        workers.append(worker)
        if worker.get("complete") is not True:
            worker_errors.append(f"gpu{worker_id}: worker incomplete")
        if int(worker.get("model_load_count", -1)) != 1:
            worker_errors.append(f"gpu{worker_id}: expected exactly one model load")
        if str(worker.get("physical_gpu")) != str(worker_id):
            worker_errors.append(f"gpu{worker_id}: CUDA mapping mismatch")
        if worker.get("shared_inference_server") is not False:
            worker_errors.append(f"gpu{worker_id}: shared server invariant failed")
    attempts = infrastructure_attempts(output_root)
    summary = summarize_v2(config=config, terminals=terminal_audit["terminals"])
    errors = list(terminal_audit["errors"]) + claim_errors + worker_errors
    if parity_report.get("passed") is not True:
        errors.append("parity report did not pass")
    if run_manifest["v1_protection"]["before"] != v1_after:
        errors.append("protected v1 inventory changed during v2")
    selected = summary["selected_task_ids"]
    result = {
        **summary,
        "schema_version": "openvla-libero-calibration-v2-summary-v1",
        "passed": not errors and summary["complete"],
        "errors": errors,
        "terminal_audit": {
            key: value
            for key, value in terminal_audit.items()
            if key != "terminals"
        },
        "atomic_claim_count": len(claims),
        "worker_count": WORKER_COUNT,
        "worker_summaries": workers,
        "infrastructure_attempt_count": len(attempts),
        "infrastructure_attempts": attempts,
        "runtime_task_identity": runtime_tasks,
        "parity_report": str((output_root / "parity_report.json").resolve()),
        "parity_gates": parity_report.get("gates"),
        "v1_integrity_before": run_manifest["v1_protection"]["before"],
        "v1_integrity_after": v1_after,
        "v1_overlap_comparison": _v1_task1_comparison(config),
        "terminal_paths": {
            str(record["episode_id"]): record["_terminal_path"]
            for record in terminal_audit["terminals"]
        },
        "hard_stop": True,
        "hard_stop_reason": (
            "all_tasks_below_3_of_5"
            if not selected
            else "at_least_one_task_reached_3_of_5_wait_for_explicit_approval"
        ),
        "cope_or_disturbance_started": False,
        "formal_experiment_started": False,
        "next_experiment_authorized": False,
    }
    _atomic_json(output_root / "calibration_summary_v2.json", result)
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("prepare", "parity", "worker", "audit"), required=True
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--static-manifest", type=Path, default=DEFAULT_STATIC_MANIFEST)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--worker-id", type=int)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_root = args.output_root.resolve()
    if args.mode == "prepare":
        result = prepare(
            config_path=args.config.resolve(),
            static_manifest_path=args.static_manifest.resolve(),
            output_root=output_root,
            resume=args.resume,
        )
    elif args.mode == "parity":
        result = parity(output_root=output_root)
    elif args.mode == "worker":
        if args.worker_id is None:
            raise ValueError("worker mode requires --worker-id")
        result = worker(
            output_root=output_root, worker_id=args.worker_id, resume=args.resume
        )
    else:
        result = audit(output_root=output_root)
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    if args.mode in {"parity", "audit"} and result.get("passed") is not True:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
