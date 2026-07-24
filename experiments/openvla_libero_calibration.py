#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from collections import Counter
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Mapping

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope.calibration import (  # noqa: E402
    CalibrationSeedScheme,
    build_calibration_entries,
    canonical_hash,
    validate_openvla_action,
    wilson_interval,
)
from libero_experiment_core import (  # noqa: E402
    ExperimentConfig,
    create_libero_env,
    execute_policy_step,
    frame_from_obs,
    get_benchmark_suite,
    get_dummy_action,
    get_image_resize_size,
    json_safe,
    load_model_and_processor,
    set_seed,
)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required for the calibration config") from exc
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("calibration config root must be a mapping")
    if value.get("schema_version") != "openvla-libero-calibration-v1":
        raise ValueError("unexpected calibration schema_version")
    return value


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(json_safe(dict(value)), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _exclusive_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(json_safe(dict(value)), indent=2, sort_keys=True) + "\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.write(descriptor, payload.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _git_identity() -> dict[str, Any]:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    )
    return {"commit": commit, "clean": not bool(status.strip()), "status": status}


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in ("torch", "transformers", "libero", "robosuite", "mujoco", "numpy"):
        try:
            versions[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _checkpoint_identity(config: Mapping[str, Any]) -> dict[str, Any]:
    checkpoint = dict(config["checkpoint"])
    root = Path(str(checkpoint["path"])).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"checkpoint directory does not exist: {root}")
    model_config_path = root / "config.json"
    statistics_path = root / "dataset_statistics.json"
    index_path = root / "model.safetensors.index.json"
    for required in (model_config_path, statistics_path, index_path):
        if not required.is_file():
            raise FileNotFoundError(f"checkpoint file is missing: {required}")
    model_config = json.loads(model_config_path.read_text(encoding="utf-8"))
    statistics = json.loads(statistics_path.read_text(encoding="utf-8"))
    unnorm_key = str(checkpoint["unnorm_key"])
    if unnorm_key not in statistics or unnorm_key not in model_config.get("norm_stats", {}):
        raise ValueError(f"checkpoint does not provide normalization statistics for {unnorm_key}")
    action_stats = statistics[unnorm_key]["action"]
    expected_dim = int(checkpoint["expected_action_dim"])
    for field in ("mean", "std", "min", "max", "q01", "q99", "mask"):
        if len(action_stats[field]) != expected_dim:
            raise ValueError(f"checkpoint action statistics {field} do not have dim {expected_dim}")
    weights = sorted(root.glob("model-*.safetensors"))
    expected_weights = int(checkpoint["expected_weight_files"])
    if len(weights) != expected_weights:
        raise ValueError(f"expected {expected_weights} weight shards, found {len(weights)}")
    expected_shards = {
        str(name): dict(value)
        for name, value in (checkpoint.get("weight_shards") or {}).items()
    }
    shard_records: list[dict[str, Any]] = []
    for path in weights:
        record = {"name": path.name, "bytes": path.stat().st_size}
        expected = expected_shards.get(path.name)
        if expected:
            if int(expected.get("bytes", -1)) != record["bytes"]:
                raise ValueError(f"weight shard size mismatch for {path.name}")
            expected_sha256 = str(expected.get("sha256", ""))
            actual_sha256 = _sha256_file(path)
            if actual_sha256 != expected_sha256:
                raise ValueError(f"weight shard SHA-256 mismatch for {path.name}")
            record["sha256"] = actual_sha256
        shard_records.append(record)
    return {
        "repository": checkpoint["repository"],
        "revision": checkpoint["revision"],
        "path": str(root),
        "files_manifest_sha256": checkpoint["files_manifest_sha256"],
        "unnorm_key": unnorm_key,
        "action_dim": expected_dim,
        "proprio_dim": int(checkpoint["expected_proprio_dim"]),
        "action_mask": action_stats["mask"],
        "action_q01": action_stats["q01"],
        "action_q99": action_stats["q99"],
        "normalization_statistics_sha256": hashlib.sha256(
            statistics_path.read_bytes()
        ).hexdigest(),
        "model_index_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "weight_shards": shard_records,
    }


def _action_spec(env: Any, expected_dim: int) -> tuple[list[float], list[float], str]:
    for label, candidate in (("env", env), ("env.env", getattr(env, "env", None))):
        if candidate is None or not hasattr(candidate, "action_spec"):
            continue
        value = candidate.action_spec
        if callable(value):
            value = value()
        if isinstance(value, (tuple, list)) and len(value) == 2:
            low = np.asarray(value[0], dtype=float).reshape(-1)
            high = np.asarray(value[1], dtype=float).reshape(-1)
            return low.tolist(), high.tolist(), f"{label}.action_spec"
    return [-1.0] * expected_dim, [1.0] * expected_dim, "openvla_libero_contract"


def _observation_summary(obs: Mapping[str, Any], frame: np.ndarray) -> dict[str, Any]:
    from experiments.robot.libero.libero_utils import quat2axisangle

    state = np.concatenate(
        (
            obs["robot0_eef_pos"],
            quat2axisangle(obs["robot0_eef_quat"]),
            obs["robot0_gripper_qpos"],
        )
    )
    return {
        "keys": sorted(str(key) for key in obs),
        "frame_shape": list(frame.shape),
        "frame_dtype": str(frame.dtype),
        "frame_sha256": hashlib.sha256(np.asarray(frame).tobytes()).hexdigest(),
        "proprio_shape": list(state.shape),
        "proprio_finite": bool(np.isfinite(state).all()),
    }


def _cuda_memory() -> dict[str, Any]:
    import torch

    if not torch.cuda.is_available():
        return {"cuda_available": False}
    index = torch.cuda.current_device()
    properties = torch.cuda.get_device_properties(index)
    return {
        "cuda_available": True,
        "device": f"cuda:{index}",
        "name": properties.name,
        "total_bytes": properties.total_memory,
        "allocated_bytes": torch.cuda.memory_allocated(index),
        "reserved_bytes": torch.cuda.memory_reserved(index),
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(index),
        "peak_reserved_bytes": torch.cuda.max_memory_reserved(index),
    }


def _model_cfg(config: Mapping[str, Any], *, task_id: int, state_id: int, seed: int) -> ExperimentConfig:
    runtime = config["runtime"]
    checkpoint = config["checkpoint"]
    return ExperimentConfig(
        checkpoint=str(checkpoint["path"]),
        task_suite=str(config["task_suite"]),
        unnorm_key=str(checkpoint["unnorm_key"]),
        task_id=task_id,
        trial_id=state_id,
        mode="clean",
        max_steps=int(runtime["policy_step_budget"]),
        num_steps_wait=int(runtime["warmup_simulator_steps"]),
        seed=seed,
        resolution=int(runtime["resolution"]),
    )


def _run_smoke(
    *,
    config: Mapping[str, Any],
    config_hash: str,
    output_dir: Path,
    model: Any,
    processor: Any,
    runtime_model_cfg: Any,
    resolved_unnorm_key: str,
    checkpoint_identity: Mapping[str, Any],
) -> dict[str, Any]:
    from PIL import Image

    seed_scheme = CalibrationSeedScheme.from_mapping(config["seed_scheme"])
    task_id = int(config["task_ids"][0])
    state_id = int(config["initial_state_ids"][0])
    seed = seed_scheme.derive(task_ordinal=0, state_id=state_id)
    cfg = _model_cfg(config, task_id=task_id, state_id=state_id, seed=seed)
    suite = get_benchmark_suite(str(config["task_suite"]))
    task = suite.get_task(task_id)
    initial_state = suite.get_task_init_states(task_id)[state_id]
    env = None
    try:
        set_seed(seed)
        env, prompt = create_libero_env(task, cfg)
        env.reset()
        obs = env.set_init_state(initial_state)
        resize_size = get_image_resize_size(runtime_model_cfg)
        frame = frame_from_obs(obs, resize_size)
        Image.fromarray(frame).save(output_dir / "reset_observation.png")
        observation = _observation_summary(obs, frame)
        low, high, action_spec_source = _action_spec(
            env, int(checkpoint_identity["action_dim"])
        )
        import torch

        torch.cuda.reset_peak_memory_stats()
        step = execute_policy_step(
            cfg=runtime_model_cfg,
            model=model,
            processor=processor,
            env=env,
            obs=obs,
            prompt=prompt,
            resize_size=resize_size,
        )
        action_validation = validate_openvla_action(
            step.raw_action,
            step.env_action,
            expected_dim=int(checkpoint_identity["action_dim"]),
            action_low=low,
            action_high=high,
        )
        gates = {
            "real_libero_reset_observation": bool(observation["keys"]),
            "camera_frame_present": observation["frame_shape"][-1:] == [3],
            "proprio_dimension": observation["proprio_shape"]
            == [int(checkpoint_identity["proprio_dim"])],
            "proprio_finite": observation["proprio_finite"],
            "resolved_unnorm_key": resolved_unnorm_key
            == checkpoint_identity["unnorm_key"],
            "action_validation": action_validation["passed"],
            "one_environment_step_executed": True,
            "model_inference_latency_recorded": step.inference_seconds > 0.0,
            "no_fake_scripted_or_noop_policy": True,
        }
        result = {
            "schema_version": "openvla-libero-smoke-v1",
            "phase": "smoke",
            "complete": True,
            "passed": all(gates.values()),
            "config_hash": config_hash,
            "task_suite": config["task_suite"],
            "task_id": task_id,
            "initial_state_id": state_id,
            "seed": seed,
            "task_prompt": prompt,
            "checkpoint": checkpoint_identity,
            "observation": observation,
            "action_spec_source": action_spec_source,
            "action_validation": action_validation,
            "reward_after_step": step.reward,
            "done_after_step": step.done,
            "info_after_step": step.info,
            "inference_seconds": step.inference_seconds,
            "environment_step_seconds": step.env_step_seconds,
            "gpu": _cuda_memory(),
            "policy_proof": {
                "model_class": f"{type(model).__module__}.{type(model).__name__}",
                "processor_class": f"{type(processor).__module__}.{type(processor).__name__}",
                "checkpoint_path": checkpoint_identity["path"],
                "checkpoint_revision": checkpoint_identity["revision"],
                "inference_function": "libero_experiment_core.execute_policy_step",
                "processor_loader": getattr(
                    runtime_model_cfg, "processor_loader", "unrecorded"
                ),
                "processor_dynamic_load_error": getattr(
                    runtime_model_cfg, "processor_dynamic_load_error", None
                ),
                "dummy_action_used": False,
                "high_level_provider_used": False,
            },
            "gates": gates,
            "artifacts": {
                "reset_observation": str(output_dir / "reset_observation.png"),
                "report": str(output_dir / "smoke_report.json"),
            },
        }
        _atomic_json(output_dir / "smoke_report.json", result)
        return result
    finally:
        if env is not None:
            env.close()


def _completed_episode(
    path: Path, *, config_hash: str, checkpoint_revision: str
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if not record.get("complete"):
        return None
    if record.get("config_hash") != config_hash:
        raise ValueError(f"resume config hash mismatch in {path}")
    if (record.get("checkpoint") or {}).get("revision") != checkpoint_revision:
        raise ValueError(f"resume checkpoint revision mismatch in {path}")
    return record


def _run_clean_episode(
    *,
    entry: Mapping[str, Any],
    config: Mapping[str, Any],
    config_hash: str,
    output_dir: Path,
    model: Any,
    processor: Any,
    runtime_model_cfg: Any,
    resolved_unnorm_key: str,
    checkpoint_identity: Mapping[str, Any],
) -> dict[str, Any]:
    episode_id = str(entry["episode_id"])
    episode_dir = output_dir / "episodes" / episode_id
    episode_dir.mkdir(parents=True, exist_ok=True)
    episode_path = episode_dir / "episode.json"
    existing = _completed_episode(
        episode_path,
        config_hash=config_hash,
        checkpoint_revision=str(checkpoint_identity["revision"]),
    )
    if existing is not None:
        return existing
    attempts = sorted(episode_dir.glob("attempt-*.jsonl"))
    attempt_number = len(attempts) + 1
    trace_path = episode_dir / f"attempt-{attempt_number:03d}.jsonl"
    task_id = int(entry["task_id"])
    state_id = int(entry["initial_state_id"])
    seed = int(entry["seed"])
    cfg = _model_cfg(config, task_id=task_id, state_id=state_id, seed=seed)
    suite = get_benchmark_suite(str(config["task_suite"]))
    task = suite.get_task(task_id)
    initial_state = suite.get_task_init_states(task_id)[state_id]
    initial_state_digest = hashlib.sha256(np.asarray(initial_state).tobytes()).hexdigest()
    runtime = config["runtime"]
    env = None
    started = time.monotonic()
    steps: list[dict[str, Any]] = []
    success = False
    termination_reason = "simulator_error"
    exception_record: dict[str, Any] | None = None
    reward = 0.0
    done = False
    info: dict[str, Any] = {}
    prompt = ""
    observation_initial: dict[str, Any] = {}
    action_spec_source = ""
    try:
        import torch

        torch.cuda.reset_peak_memory_stats()
        set_seed(seed)
        env, prompt = create_libero_env(task, cfg)
        env.reset()
        obs = env.set_init_state(initial_state)
        resize_size = get_image_resize_size(runtime_model_cfg)
        frame = frame_from_obs(obs, resize_size)
        observation_initial = _observation_summary(obs, frame)
        low, high, action_spec_source = _action_spec(
            env, int(checkpoint_identity["action_dim"])
        )
        with trace_path.open("x", encoding="utf-8", buffering=1) as trace:
            for warmup_step in range(int(runtime["warmup_simulator_steps"])):
                obs, reward, done, info = env.step(get_dummy_action("openvla"))
                trace.write(
                    json.dumps(
                        {
                            "record_type": "warmup",
                            "warmup_step": warmup_step,
                            "dummy_action": True,
                            "reward": float(reward),
                            "done": bool(done),
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
            for policy_step in range(int(runtime["policy_step_budget"])):
                step = execute_policy_step(
                    cfg=runtime_model_cfg,
                    model=model,
                    processor=processor,
                    env=env,
                    obs=obs,
                    prompt=prompt,
                    resize_size=resize_size,
                )
                obs = step.next_obs
                reward = step.reward
                done = step.done
                info = dict(step.info)
                validation = validate_openvla_action(
                    step.raw_action,
                    step.env_action,
                    expected_dim=int(checkpoint_identity["action_dim"]),
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
                }
                steps.append(row)
                trace.write(json.dumps(row, sort_keys=True) + "\n")
                if policy_step % 10 == 0:
                    trace.flush()
                    os.fsync(trace.fileno())
                if not validation["passed"]:
                    termination_reason = "action_schema_error"
                    break
                if done or reward >= 1.0:
                    success = True
                    termination_reason = (
                        "libero_done" if done else "libero_sparse_reward_ge_1"
                    )
                    break
            else:
                termination_reason = "policy_step_budget_exhausted"
    except Exception as exc:
        exception_record = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        termination_reason = "simulator_or_runtime_error"
    finally:
        if env is not None:
            env.close()
    result = {
        "schema_version": "openvla-libero-clean-calibration-episode-v1",
        "complete": True,
        "phase": "calibration",
        "evidence_admissibility": "calibration_only_excluded_from_evaluation",
        "episode_id": episode_id,
        "task_suite": config["task_suite"],
        "task_id": task_id,
        "initial_state_id": state_id,
        "initial_state_digest": initial_state_digest,
        "seed": seed,
        "task_prompt": prompt,
        "config_hash": config_hash,
        "checkpoint": {
            "path": checkpoint_identity["path"],
            "revision": checkpoint_identity["revision"],
            "unnorm_key": resolved_unnorm_key,
        },
        "observation_initial": observation_initial,
        "action_spec_source": action_spec_source,
        "warmup_simulator_steps": int(runtime["warmup_simulator_steps"]),
        "policy_step_budget": int(runtime["policy_step_budget"]),
        "policy_steps_consumed": len(steps),
        "success": success,
        "termination_reason": termination_reason,
        "final_reward": float(reward),
        "final_done": bool(done),
        "final_info": info,
        "action_schema_valid": all(
            bool(item["action_validation"]["passed"]) for item in steps
        ),
        "mean_inference_seconds": (
            sum(float(item["inference_seconds"]) for item in steps) / len(steps)
            if steps
            else None
        ),
        "max_inference_seconds": (
            max(float(item["inference_seconds"]) for item in steps) if steps else None
        ),
        "runtime_seconds": time.monotonic() - started,
        "gpu": _cuda_memory(),
        "manual_intervention": False,
        "reset_count": 1,
        "rollback_count": 0,
        "fake_scripted_or_noop_policy": False,
        "attempt_number": attempt_number,
        "exception": exception_record,
        "artifacts": {
            "trace": str(trace_path),
            "episode": str(episode_path),
        },
    }
    _atomic_json(episode_path, result)
    return result


def _summarize_calibration(
    records: list[Mapping[str, Any]], config: Mapping[str, Any]
) -> dict[str, Any]:
    threshold = float(config["selection"]["minimum_clean_success_rate"])
    task_summaries: dict[str, Any] = {}
    selected: list[int] = []
    excluded: list[dict[str, Any]] = []
    for task_id in (int(item) for item in config["task_ids"]):
        rows = [row for row in records if int(row["task_id"]) == task_id]
        successes = sum(bool(row["success"]) for row in rows)
        total = len(rows)
        rate = successes / total if total else 0.0
        interval = wilson_interval(successes, total)
        terminations = Counter(str(row["termination_reason"]) for row in rows)
        task_summaries[str(task_id)] = {
            "n": total,
            "successes": successes,
            "success_rate": rate,
            "wilson_95_ci": list(interval),
            "mean_policy_steps": (
                sum(int(row["policy_steps_consumed"]) for row in rows) / total
                if total
                else None
            ),
            "termination_breakdown": dict(sorted(terminations.items())),
        }
        if total and rate >= threshold:
            selected.append(task_id)
        else:
            excluded.append(
                {
                    "task_id": task_id,
                    "reason": f"clean success rate {rate:.3f} is below {threshold:.3f}",
                }
            )
    expected_count = len(config["task_ids"]) * len(config["initial_state_ids"])
    all_terminal = len(records) == expected_count and all(
        bool(row.get("complete")) for row in records
    )
    return {
        "schema_version": "openvla-libero-clean-calibration-summary-v1",
        "phase": "calibration",
        "complete": all_terminal,
        "episode_count": len(records),
        "expected_episode_count": expected_count,
        "minimum_clean_success_rate": threshold,
        "tasks": task_summaries,
        "selected_task_ids": selected,
        "excluded_tasks": excluded,
        "pilot_authorized_by_calibration": bool(all_terminal and selected),
        "calibration_excluded_from_evaluation": True,
        "no_selective_reruns": all(int(row["attempt_number"]) == 1 for row in records),
    }


def _run_calibration(
    *,
    config: Mapping[str, Any],
    config_hash: str,
    output_dir: Path,
    model: Any,
    processor: Any,
    runtime_model_cfg: Any,
    resolved_unnorm_key: str,
    checkpoint_identity: Mapping[str, Any],
) -> dict[str, Any]:
    seed_scheme = CalibrationSeedScheme.from_mapping(config["seed_scheme"])
    entries = build_calibration_entries(
        task_ids=config["task_ids"],
        state_ids=config["initial_state_ids"],
        seed_scheme=seed_scheme,
    )
    records: list[dict[str, Any]] = []
    for entry in entries:
        record = _run_clean_episode(
            entry=entry,
            config=config,
            config_hash=config_hash,
            output_dir=output_dir,
            model=model,
            processor=processor,
            runtime_model_cfg=runtime_model_cfg,
            resolved_unnorm_key=resolved_unnorm_key,
            checkpoint_identity=checkpoint_identity,
        )
        records.append(record)
        summary = _summarize_calibration(records, config)
        summary["config_hash"] = config_hash
        summary["checkpoint"] = checkpoint_identity
        summary["episodes"] = [row["artifacts"]["episode"] for row in records]
        _atomic_json(output_dir / "calibration_summary.partial.json", summary)
        print(
            json.dumps(
                {
                    "episode_id": record["episode_id"],
                    "success": record["success"],
                    "termination_reason": record["termination_reason"],
                    "completed": len(records),
                    "expected": len(entries),
                },
                sort_keys=True,
            ),
            flush=True,
        )
    summary = _summarize_calibration(records, config)
    summary["config_hash"] = config_hash
    summary["checkpoint"] = checkpoint_identity
    summary["episodes"] = [row["artifacts"]["episode"] for row in records]
    _atomic_json(output_dir / "calibration_summary.json", summary)
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("smoke", "calibration"), required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/openvla_libero_10_calibration_v1.yaml"),
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--smoke-report", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    config = _load_yaml(config_path)
    config_hash = canonical_hash(config)
    git = _git_identity()
    if not git["clean"]:
        raise SystemExit(f"refusing calibration with dirty worktree:\n{git['status']}")
    output_dir = args.out_dir.resolve()
    if output_dir.exists() and not args.resume:
        raise FileExistsError(f"output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_identity = _checkpoint_identity(config)
    seed_scheme = CalibrationSeedScheme.from_mapping(config["seed_scheme"])
    entries = build_calibration_entries(
        task_ids=config["task_ids"],
        state_ids=config["initial_state_ids"],
        seed_scheme=seed_scheme,
    )
    if args.phase == "calibration":
        if args.smoke_report is None:
            raise ValueError("--smoke-report is required before calibration")
        smoke = json.loads(args.smoke_report.read_text(encoding="utf-8"))
        if not smoke.get("passed"):
            raise ValueError("calibration requires a passed smoke report")
        if smoke.get("config_hash") != config_hash:
            raise ValueError("smoke/calibration config hash mismatch")
        if (smoke.get("checkpoint") or {}).get("revision") != checkpoint_identity["revision"]:
            raise ValueError("smoke/calibration checkpoint revision mismatch")
    manifest_path = output_dir / "run_manifest.json"
    manifest = {
        "schema_version": "openvla-libero-calibration-run-v1",
        "phase": args.phase,
        "config_path": str(config_path),
        "config_hash": config_hash,
        "git": git,
        "checkpoint": checkpoint_identity,
        "seed_scheme": config["seed_scheme"],
        "entries": list(entries) if args.phase == "calibration" else list(entries[:1]),
        "environment": {
            "hostname": platform.node(),
            "python": sys.version,
            "platform": platform.platform(),
            "packages": _package_versions(),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        },
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "calibration_excluded_from_evaluation": True,
    }
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = {
            "phase": args.phase,
            "config_hash": config_hash,
            "git": git,
            "checkpoint": checkpoint_identity,
            "entries": manifest["entries"],
        }
        actual = {key: existing.get(key) for key in expected}
        if actual != expected:
            raise ValueError("resume run manifest identity mismatch")
    else:
        _exclusive_json(manifest_path, manifest)
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for real OpenVLA smoke/calibration")
    torch.cuda.reset_peak_memory_stats()
    loader_cfg = _model_cfg(
        config,
        task_id=int(config["task_ids"][0]),
        state_id=int(config["initial_state_ids"][0]),
        seed=int(entries[0]["seed"]),
    )
    load_started = time.monotonic()
    model, processor, runtime_model_cfg, resolved_unnorm_key = load_model_and_processor(
        loader_cfg
    )
    model_load_seconds = time.monotonic() - load_started
    load_report = {
        "model_load_seconds": model_load_seconds,
        "resolved_unnorm_key": resolved_unnorm_key,
        "processor_loader": getattr(runtime_model_cfg, "processor_loader", "unrecorded"),
        "processor_dynamic_load_error": getattr(
            runtime_model_cfg, "processor_dynamic_load_error", None
        ),
        "gpu_after_load": _cuda_memory(),
    }
    _atomic_json(output_dir / "model_load.json", load_report)
    if args.phase == "smoke":
        result = _run_smoke(
            config=config,
            config_hash=config_hash,
            output_dir=output_dir,
            model=model,
            processor=processor,
            runtime_model_cfg=runtime_model_cfg,
            resolved_unnorm_key=resolved_unnorm_key,
            checkpoint_identity=checkpoint_identity,
        )
        print(json.dumps(result, indent=2, sort_keys=True), flush=True)
        return 0 if result["passed"] else 2
    summary = _run_calibration(
        config=config,
        config_hash=config_hash,
        output_dir=output_dir,
        model=model,
        processor=processor,
        runtime_model_cfg=runtime_model_cfg,
        resolved_unnorm_key=resolved_unnorm_key,
        checkpoint_identity=checkpoint_identity,
    )
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0 if summary["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
