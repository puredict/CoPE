from __future__ import annotations

import base64
import hashlib
import io
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from cope.config import ComparisonConfig
from cope.detector import DetectorFactory, RecoveryEventDetector
from cope.methods.base import MethodExecutionError, RecoveryMethod
from cope.pairing import PairSpec
from cope.providers.base import HighLevelRecoveryProvider, provider_call_record
from cope.runner import RunContext
from cope.types import MethodDecision, RecoveryInput, stable_hash


PROMPT_TEMPLATE_BUNDLE = {
    "reactive_disturbed": "{original_task}",
    "structured_relocalize_prompt": (
        "relocalize the {affected_object} at its current position, then complete the original task: {original_task}"
    ),
    "stage_backtrack_subgoal": (
        "pick up the {affected_object} from its current position and place it on {goal}"
    ),
    "history_augmented_full_regeneration": "provider full-state schema -> controller_prompt",
    "cope_patch": "provider typed patch -> engine compiled controller prompt",
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _array_digest(value: Any) -> str:
    return hashlib.sha256(np.asarray(value, dtype=np.float64).tobytes()).hexdigest()


def _simulator_state_hash(env: Any) -> str:
    from libero_experiment_core import sim_from_env

    sim = sim_from_env(env)
    payload = np.concatenate(
        [
            np.asarray(sim.data.qpos, dtype=np.float64).ravel(),
            np.asarray(sim.data.qvel, dtype=np.float64).ravel(),
        ]
    )
    return _array_digest(payload)


def _public_history(actions: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "policy_step": action["policy_step"],
            "raw_action": action["raw_action"],
            "env_action": action["env_action"],
            "reward": action["reward"],
            "done": action["done"],
            "task_progress": action["task_progress"],
        }
        for action in actions
    )


def _png_payload(frame: np.ndarray) -> tuple[bytes, str]:
    from PIL import Image

    buffer = io.BytesIO()
    Image.fromarray(np.asarray(frame, dtype=np.uint8)).save(buffer, format="PNG")
    payload = buffer.getvalue()
    return payload, _sha256_bytes(payload)


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n")


def _save_video(frames: list[np.ndarray], path: Path) -> None:
    import imageio.v2 as imageio

    writer = imageio.get_writer(path, fps=30)
    try:
        for frame in frames:
            writer.append_data(np.asarray(frame, dtype=np.uint8))
    finally:
        writer.close()


class LiberoComparisonBackend:
    name = "libero_openvla_shared_rollout_v1"
    formal_capable = True

    def __init__(
        self,
        *,
        config: ComparisonConfig,
        provider: HighLevelRecoveryProvider,
        detector_factory: DetectorFactory | None = None,
        detector_config: dict[str, Any] | None = None,
    ) -> None:
        self.config = config
        self.provider = provider
        self.detector_factory = detector_factory
        self.detector_config = detector_config or {}
        self.model: Any = None
        self.processor: Any = None
        self.model_cfg: Any = None
        self.resolved_unnorm_key = ""
        self.task_suite: Any = None

    def readiness_errors(self, config: ComparisonConfig, *, formal: bool) -> list[str]:
        errors: list[str] = []
        for module in ("libero", "torch", "transformers", "imageio", "PIL"):
            try:
                __import__(module)
            except Exception as exc:
                errors.append(f"missing runtime dependency {module}: {type(exc).__name__}")
        try:
            import torch

            if formal and not torch.cuda.is_available():
                errors.append("CUDA GPU is unavailable")
        except Exception:
            pass
        if formal and not Path(config.checkpoint_path).exists():
            errors.append(f"checkpoint path does not exist: {config.checkpoint_path}")
        if config.event_source == "detected" and self.detector_factory is None:
            errors.append("detected sensitivity requires a detector factory")
        elif config.event_source == "detected" and self.detector_factory is not None:
            try:
                detector = self._make_detector()
                metadata = detector.metadata if detector is not None else {}
                if formal and metadata.get("is_fake") is not False:
                    errors.append("formal detected sensitivity forbids a fake detector")
                if formal and not metadata.get("detector_commit"):
                    errors.append("formal detected sensitivity requires detector_commit")
            except Exception as exc:
                errors.append(f"detector readiness failed: {type(exc).__name__}: {exc}")
        return errors

    def _load(self) -> None:
        if self.model is not None:
            return
        from libero_experiment_core import (
            ExperimentConfig,
            get_benchmark_suite,
            load_model_and_processor,
        )

        cfg = ExperimentConfig(
            checkpoint=self.config.checkpoint_path,
            task_suite=self.config.task_suite,
            mode="reactive_disturbed",
            max_steps=self.config.max_policy_steps,
            num_steps_wait=self.config.warmup_env_steps,
            resolution=self.config.resolution,
        )
        self.model, self.processor, self.model_cfg, self.resolved_unnorm_key = load_model_and_processor(cfg)
        self.task_suite = get_benchmark_suite(self.config.task_suite)

    def _make_detector(self) -> RecoveryEventDetector | None:
        return self.detector_factory(self.detector_config) if self.detector_factory else None

    def run_episode(
        self,
        *,
        pair: PairSpec,
        method: RecoveryMethod,
        method_name: str,
        context: RunContext,
        episode_dir: Path,
    ) -> dict[str, Any]:
        from libero_experiment_core import (
            ExperimentConfig,
            create_libero_env,
            execute_policy_step,
            extract_episode_status,
            frame_from_obs,
            get_dummy_action,
            get_image_resize_size,
            json_safe,
            move_free_joint_xy,
            refresh_observation_after_sim_change,
            set_seed,
            unload_torch_model_refs,
        )

        self._load()
        episode_dir.mkdir(parents=True, exist_ok=False)
        actions_path = episode_dir / "actions.jsonl"
        events_path = episode_dir / "events.jsonl"
        raw_video_path = episode_dir / "raw.mp4"
        episode_path = episode_dir / "episode.json"
        event_observation_path = episode_dir / "event_observation.png"
        detector = self._make_detector()
        set_seed(pair.seed)
        task = self.task_suite.get_task(pair.task_id)
        initial_states = list(self.task_suite.get_task_init_states(pair.task_id))
        if pair.initial_state_id >= len(initial_states):
            raise ValueError(f"initial state {pair.initial_state_id} unavailable for task {pair.task_id}")
        init_state = initial_states[pair.initial_state_id]
        actual_init_digest = _array_digest(init_state)
        if actual_init_digest != pair.initial_state_digest:
            raise ValueError(
                f"atlas initial state digest mismatch: {actual_init_digest} != {pair.initial_state_digest}"
            )
        env_cfg = ExperimentConfig(
            checkpoint=self.config.checkpoint_path,
            task_suite=self.config.task_suite,
            task_id=pair.task_id,
            trial_id=pair.initial_state_id,
            mode="reactive_disturbed",
            max_steps=self.config.max_policy_steps,
            num_steps_wait=self.config.warmup_env_steps,
            disturbance_step=pair.disturbance.policy_step,
            target_joint=pair.disturbance.target_joint,
            dx=pair.disturbance.delta_xyz[0],
            dy=pair.disturbance.delta_xyz[1],
            seed=pair.seed,
            resolution=self.config.resolution,
            out_dir=str(episode_dir),
        )
        env, original_prompt = create_libero_env(task, env_cfg)
        resize_size = get_image_resize_size(self.model_cfg)
        actions: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        frames: list[np.ndarray] = []
        reward = 0.0
        done = False
        info: dict[str, Any] = {}
        current_prompt = original_prompt
        physical_disturbance_applied = False
        recovery_triggered = False
        event_step: int | None = None
        event_packet: dict[str, Any] | None = None
        event_observation_hash: str | None = None
        recovery_input: RecoveryInput | None = None
        decision: MethodDecision | None = None
        method_error: MethodExecutionError | None = None
        disturbance_actual: dict[str, Any] | None = None
        detector_record: dict[str, Any] | None = None
        detector_trace: list[dict[str, Any]] = []
        initial_state_hash = ""
        pre_event_action_digest = ""
        start_time = time.monotonic()
        high_level_termination: str | None = None

        try:
            env.reset()
            obs = env.set_init_state(init_state)
            initial_state_hash = _simulator_state_hash(env)
            method.prepare(
                original_prompt,
                {
                    "pair_key": pair.pair_key,
                    "task_id": pair.task_id,
                    "initial_state_id": pair.initial_state_id,
                    "seed": pair.seed,
                    "engine_commit": context.engine_commit,
                },
            )
            for _ in range(self.config.warmup_env_steps):
                obs, reward, done, info = env.step(get_dummy_action("openvla"))
            events.append(
                {
                    "event": "warmup_complete",
                    "policy_step": 0,
                    "warmup_env_steps": self.config.warmup_env_steps,
                }
            )

            for policy_step in range(self.config.max_policy_steps):
                if method_name != "clean" and policy_step == pair.disturbance.policy_step:
                    if abs(pair.disturbance.delta_xyz[2]) > 1e-12:
                        raise ValueError("current LIBERO adapter only supports zero-z free-joint displacement")
                    disturbance_actual = move_free_joint_xy(
                        env,
                        pair.disturbance.target_joint,
                        pair.disturbance.delta_xyz[0],
                        pair.disturbance.delta_xyz[1],
                    )
                    obs, refresh = refresh_observation_after_sim_change(env, self.model_cfg)
                    if refresh.get("consumed_noop_env_step"):
                        raise RuntimeError("formal observation refresh consumed a hidden noop environment step")
                    disturbance_actual["refresh"] = refresh
                    physical_disturbance_applied = True
                    events.append(
                        {
                            "event": "physical_disturbance",
                            "policy_step": policy_step,
                            "payload": json_safe(disturbance_actual),
                        }
                    )

                should_trigger = False
                candidate_packet: dict[str, Any] | None = None
                if method_name != "clean" and not recovery_triggered:
                    if context.event_source == "oracle":
                        if physical_disturbance_applied:
                            should_trigger = policy_step == pair.disturbance.policy_step
                            candidate_packet = pair.disturbance.oracle_event_packet()
                    elif detector is not None:
                        detector_output = detector.detect(
                            observation=json_safe(obs),
                            public_action_history=_public_history(actions),
                            policy_step=policy_step,
                        )
                        trace_record = {
                            "policy_step": policy_step,
                            "ground_truth_event_active": physical_disturbance_applied,
                            "metadata": detector.metadata,
                            "detected": detector_output.detected,
                            "event_packet": detector_output.event_packet,
                            "confidence": detector_output.confidence,
                            "latency_steps": detector_output.latency_steps,
                            "raw_output": detector_output.raw_output,
                        }
                        detector_trace.append(trace_record)
                        should_trigger = detector_output.detected
                        candidate_packet = detector_output.event_packet

                if should_trigger:
                    if not isinstance(candidate_packet, dict):
                        raise RuntimeError("event source triggered without a structured event packet")
                    extra_event_fields = set(candidate_packet) - set(
                        self.config.information_budget.event_fields
                    )
                    if extra_event_fields:
                        raise RuntimeError(
                            f"event packet exceeds information budget: {sorted(extra_event_fields)}"
                        )
                    recovery_triggered = True
                    event_step = policy_step
                    event_packet = candidate_packet
                    pre_event_action_digest = stable_hash(
                        [{"raw_action": action["raw_action"], "env_action": action["env_action"]} for action in actions]
                    )
                    frame = frame_from_obs(obs, resize_size)
                    png, event_observation_hash = _png_payload(frame)
                    event_observation_path.write_bytes(png)
                    observation_packet = {
                        "encoding": "image/png;base64",
                        "rgb": base64.b64encode(png).decode("ascii"),
                        "sha256": event_observation_hash,
                        "width": int(frame.shape[1]),
                        "height": int(frame.shape[0]),
                        "fresh": True,
                    }
                    task_progress = {
                        "source": "libero_sparse_reward",
                        "latest_reward": float(reward),
                        "completed": bool(done or reward >= 1.0),
                    }
                    recovery_input = RecoveryInput(
                        schema_version="recovery-input-v1",
                        pair_key=pair.pair_key,
                        original_task=original_prompt,
                        observation=observation_packet,
                        event=event_packet,
                        public_action_history=_public_history(actions),
                        task_progress=task_progress,
                        information_budget=self.config.information_budget,
                    )
                    try:
                        decision = method.on_event(
                            original_prompt=original_prompt,
                            target_joint=pair.disturbance.target_joint,
                            recovery_input=recovery_input,
                        )
                        current_prompt = decision.controller_prompt
                    except MethodExecutionError as exc:
                        method_error = exc
                        calls = exc.provider_calls
                        if exc.kind == "timeout" or (calls and calls[0].timeout):
                            high_level_termination = "high_level_timeout"
                        elif exc.kind == "parse_failure" or (calls and calls[0].parse_failure):
                            high_level_termination = "high_level_parse_failure"
                        elif exc.kind in {
                            "validation_failure",
                            "engine_or_schema_validation_failure",
                        } or (calls and calls[0].validation_failure):
                            high_level_termination = "high_level_validation_failure"
                        else:
                            high_level_termination = "high_level_method_error"
                    events.append(
                        {
                            "event": "recovery_decision",
                            "policy_step": policy_step,
                            "event_packet": event_packet,
                            "recovery_input_hash": recovery_input.input_hash,
                            "controller_prompt": current_prompt if decision else None,
                            "error": method_error.reason if method_error else None,
                        }
                    )
                    if high_level_termination:
                        break

                if method_name == "clean" and policy_step == pair.disturbance.policy_step:
                    pre_event_action_digest = stable_hash(
                        [{"raw_action": action["raw_action"], "env_action": action["env_action"]} for action in actions]
                    )
                    event_step = policy_step

                step_result = execute_policy_step(
                    cfg=self.model_cfg,
                    model=self.model,
                    processor=self.processor,
                    env=env,
                    obs=obs,
                    prompt=current_prompt,
                    resize_size=resize_size,
                )
                obs = step_result.next_obs
                reward = step_result.reward
                done = step_result.done
                info = dict(step_result.info)
                action_record = {
                    "policy_step": policy_step,
                    "video_frame_index": len(frames),
                    "prompt": current_prompt,
                    "raw_action": step_result.raw_action,
                    "env_action": step_result.env_action,
                    "reward": reward,
                    "done": done,
                    "task_progress": {
                        "source": "libero_sparse_reward",
                        "reward": reward,
                        "completed": bool(done or reward >= 1.0),
                    },
                    "uses_fresh_post_event_observation": bool(
                        recovery_triggered and event_step == policy_step
                    ),
                    "inference_seconds": step_result.inference_seconds,
                    "env_step_seconds": step_result.env_step_seconds,
                }
                actions.append(action_record)
                frames.append(step_result.raw_frame)
                if done:
                    break

            if not pre_event_action_digest:
                cutoff = min(pair.disturbance.policy_step, len(actions))
                pre_event_action_digest = stable_hash(
                    [
                        {"raw_action": action["raw_action"], "env_action": action["env_action"]}
                        for action in actions[:cutoff]
                    ]
                )
            if high_level_termination:
                termination_reason = high_level_termination
                success = False
                status = "failure"
            else:
                episode_status = extract_episode_status(
                    reward,
                    done,
                    info,
                    len(actions),
                    self.config.max_policy_steps,
                )
                termination_reason = episode_status.status
                success = episode_status.success
                status = episode_status.status

            split_step = min(event_step if event_step is not None else pair.disturbance.policy_step, len(actions))
            provider_invocations = ()
            if decision:
                provider_invocations = decision.provider_calls
            elif method_error:
                provider_invocations = method_error.provider_calls
            provider_calls = [provider_call_record(call, self.provider.metadata) for call in provider_invocations]
            constraint_before = decision.constraint_state_before if decision else (
                method_error.constraint_state_before if method_error else None
            )
            if context.event_source == "detected":
                tp = sum(
                    int(item["detected"] and item["ground_truth_event_active"])
                    for item in detector_trace
                )
                fp = sum(
                    int(item["detected"] and not item["ground_truth_event_active"])
                    for item in detector_trace
                )
                fn = int(physical_disturbance_applied and tp == 0)
                detector_record = {
                    "metadata": detector.metadata if detector is not None else None,
                    "trace": detector_trace,
                    "confusion_counts": {"tp": tp, "fp": fp, "fn": fn},
                    "event_latency_steps": (
                        event_step - pair.disturbance.policy_step
                        if event_step is not None and event_step >= pair.disturbance.policy_step
                        else None
                    ),
                }
            record: dict[str, Any] = {
                "schema_version": "cope-main-episode-v1",
                "run_id": context.run_id,
                "pair_key": pair.pair_key,
                "task_id": pair.task_id,
                "initial_state_id": pair.initial_state_id,
                "seed": pair.seed,
                "method": method_name,
                "event_source": context.event_source,
                "information_budget": asdict(self.config.information_budget),
                "event": event_packet,
                "disturbance_actual": json_safe(disturbance_actual),
                "disturbance_step": pair.disturbance.policy_step,
                "detector": json_safe(detector_record),
                "policy_step_budget": self.config.max_policy_steps,
                "post_event_policy_step_budget": self.config.max_policy_steps - (
                    event_step if event_step is not None else pair.disturbance.policy_step
                ),
                "steps_before_event": split_step,
                "steps_after_event": len(actions) - split_step,
                "policy_steps": len(actions),
                "high_level_call_count": len(provider_invocations),
                "prompt_tokens": sum(call.usage.prompt_tokens for call in provider_invocations),
                "completion_tokens": sum(call.usage.completion_tokens for call in provider_invocations),
                "provider_calls": provider_calls,
                "high_level_error": (
                    {"kind": method_error.kind, "reason": method_error.reason}
                    if method_error
                    else None
                ),
                "provider_metadata": asdict(self.provider.metadata),
                "provider_fairness_fingerprint": self.provider.metadata.fairness_fingerprint,
                "recovery_input_hash": recovery_input.input_hash if recovery_input else None,
                "constraint_state_before": constraint_before,
                "constraint_state_after": decision.constraint_state_after if decision else None,
                "patch_operations": list(decision.patch_operations) if decision else [],
                "revalidation_result": list(decision.revalidation_result) if decision else [],
                "unaffected_slot_preservation": decision.unaffected_slot_preservation if decision else None,
                "regenerated_state": decision.regenerated_state if decision else None,
                "task_progress": {
                    "source": "libero_sparse_reward",
                    "pre_event_reward": (
                        actions[split_step - 1]["reward"] if split_step > 0 else 0.0
                    ),
                    "final_reward": reward,
                    "success": success,
                },
                "success": success,
                "status": status,
                "termination_reason": termination_reason,
                "safety_violation": False,
                "manual_intervention": False,
                "reset_count": 0,
                "rollback_count": 0,
                "git_commit": context.git_commit,
                "config_hash": context.config_hash,
                "atlas_commit": context.atlas_commit,
                "engine_commit": context.engine_commit,
                "checkpoint_id": self.config.checkpoint_id,
                "test_only": False,
                "checkpoint_sha256": self.config.checkpoint_sha256,
                "checkpoint_path": self.config.checkpoint_path,
                "task_suite": self.config.task_suite,
                "resolved_unnorm_key": self.resolved_unnorm_key,
                "initial_state_hash": initial_state_hash,
                "atlas_initial_state_digest": pair.initial_state_digest,
                "pre_event_action_digest": pre_event_action_digest,
                "fresh_observation_hash": event_observation_hash,
                "downstream_controller": {
                    "name": "OpenVLA",
                    "checkpoint_id": self.config.checkpoint_id,
                    "action_normalization": "normalize+binarize+invert_openvla_gripper",
                },
                "success_definition": "LIBERO sparse reward/done audited in EXPERIMENT_PROTOCOL",
                "termination_definition": "success|timeout|failure|high_level_*|simulator_error",
                "original_prompt": original_prompt,
                "final_prompt": current_prompt,
                "prompt_trace": [action["prompt"] for action in actions],
                "prompt_template_version": self.config.prompt_template_version,
                "prompt_template_hash": stable_hash(
                    {
                        "version": self.config.prompt_template_version,
                        "templates": PROMPT_TEMPLATE_BUNDLE,
                    }
                ),
                "wall_time_seconds": time.monotonic() - start_time,
                "actions": actions,
                "artifact_paths": {
                    "episode": str(episode_path),
                    "actions": str(actions_path),
                    "events": str(events_path),
                    "raw_video": str(raw_video_path),
                    "event_observation": str(event_observation_path) if event_observation_path.exists() else None,
                },
                "artifact_alignment": {
                    "action_records": len(actions),
                    "video_frames": len(frames),
                    "aligned": len(actions) == len(frames),
                },
            }
            safe_record = json_safe(record)
            _write_jsonl(actions_path, safe_record["actions"])
            _write_jsonl(events_path, events)
            _save_video(frames, raw_video_path)
            episode_path.write_text(
                json.dumps(safe_record, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
            return safe_record
        finally:
            try:
                env.close()
            except Exception:
                pass

    def close(self) -> None:
        from libero_experiment_core import unload_torch_model_refs

        self.model = None
        self.processor = None
        self.model_cfg = None
        self.task_suite = None
        unload_torch_model_refs()
