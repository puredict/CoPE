#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope.calibration import canonical_hash, validate_openvla_action  # noqa: E402
from cope.calibration_v2 import (  # noqa: E402
    load_v2_config,
    validate_runtime_task_identity,
    validate_static_manifest,
)
from cope.semantic_replacement import (  # noqa: E402
    ALLOWED_OBJECTS,
    ORIGINAL_OBJECTS,
    RECEPTACLE,
    REPLACEMENT_OBJECT,
    StableFirstMilestoneDetector,
    build_oracle_full_state,
    build_replacement_event,
    compile_controller_prompt,
    current_goal_success,
    validate_oracle_full_state,
)
from cope_benchmark.task_progress import LiberoStateView  # noqa: E402
from experiments.openvla_libero_calibration import (  # noqa: E402
    _action_spec,
    _atomic_json,
    _cuda_memory,
    _model_cfg,
)
from libero_experiment_core import (  # noqa: E402
    create_libero_env,
    execute_policy_step,
    get_benchmark_suite,
    get_dummy_action,
    get_image_resize_size,
    load_model_and_processor,
    set_seed,
    unload_torch_model_refs,
)


DEFAULT_CONFIG = ROOT / "configs/openvla_libero_10_calibration_v2.yaml"
DEFAULT_MANIFEST = ROOT / "manifests/openvla_libero_10_calibration_v2.jsonl"
MODES = ("no_edit", "oracle_full")
PROMPT_VARIANTS = (
    "shared_compiler",
    "single_object",
    "progress_explicit",
    "pick_place",
    "task0_exact_diagnostic",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--state-id", type=int, required=True)
    parser.add_argument("--modes", default=",".join(MODES))
    parser.add_argument("--prompt-variant", choices=PROMPT_VARIANTS, default="shared_compiler")
    parser.add_argument("--prefix-trace", type=Path)
    parser.add_argument("--stable-steps", type=int, default=5)
    parser.add_argument("--event-deadline", type=int, default=300)
    parser.add_argument("--policy-budget", type=int, default=520)
    return parser.parse_args()


def _git_identity() -> dict[str, Any]:
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--short"], text=True
    ).strip()
    return {"commit": commit, "clean": not bool(status), "status": status}


def _write_trace(handle: Any, record: Mapping[str, Any]) -> None:
    handle.write(json.dumps(dict(record), sort_keys=True) + "\n")
    handle.flush()


def _predicates(view: LiberoStateView) -> dict[str, bool]:
    return {
        name: view.libero_predicate("in", (name, RECEPTACLE))
        for name in sorted(ALLOWED_OBJECTS)
    }


def _find_entry(
    entries: tuple[dict[str, Any], ...], state_id: int
) -> dict[str, Any]:
    matched = [
        dict(entry)
        for entry in entries
        if int(entry["task_id"]) == 1 and int(entry["initial_state_id"]) == state_id
    ]
    if len(matched) != 1:
        raise ValueError(f"expected one task-1 entry for state {state_id}, got {len(matched)}")
    return matched[0]


def _load_prefix_records(path: Path | None) -> tuple[dict[str, Any], ...]:
    if path is None:
        return ()
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    policy = [dict(row) for row in rows if row.get("record_type") == "policy_step"]
    steps = [int(row.get("policy_step", -1)) for row in policy]
    if steps != list(range(len(policy))):
        raise ValueError("prefix trace policy steps are not contiguous from zero")
    if not all(isinstance(row.get("environment_action"), list) for row in policy):
        raise ValueError("prefix trace is missing environment actions")
    return tuple(policy)


def _prompt_for_variant(variant: str, full_state: Mapping[str, Any]) -> str:
    if variant == "shared_compiler":
        return compile_controller_prompt(full_state)
    if variant == "single_object":
        return "put the alphabet soup in the basket"
    if variant == "progress_explicit":
        return (
            "the cream cheese box is already in the basket; "
            "now put the alphabet soup in the basket"
        )
    if variant == "pick_place":
        return "pick up the alphabet soup and place it in the basket"
    if variant == "task0_exact_diagnostic":
        # This exact task-0 instruction is diagnostic only: it includes an
        # extra tomato-sauce goal and cannot be a fair main method.
        return "put both the alphabet soup and the tomato sauce in the basket"
    raise ValueError(f"unknown prompt variant {variant!r}")


def run_episode(
    *,
    mode: str,
    entry: Mapping[str, Any],
    config: Mapping[str, Any],
    model: Any,
    processor: Any,
    runtime_model_cfg: Any,
    resolved_unnorm_key: str,
    output_dir: Path,
    stable_steps: int,
    event_deadline: int,
    policy_budget: int,
    git: Mapping[str, Any],
    prompt_variant: str,
    prefix_records: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    output_dir.mkdir(parents=True, exist_ok=False)
    trace_path = output_dir / "trace.jsonl"
    episode_path = output_dir / "episode.json"
    task_id = int(entry["task_id"])
    state_id = int(entry["initial_state_id"])
    seed = int(entry["seed"])
    cfg = _model_cfg(config, task_id=task_id, state_id=state_id, seed=seed)
    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(task_id)
    initial_state = suite.get_task_init_states(task_id)[state_id]
    initial_state_sha256 = hashlib.sha256(np.asarray(initial_state).tobytes()).hexdigest()
    if initial_state_sha256 != entry["initial_state_sha256"]:
        raise ValueError("initial state hash differs from the frozen calibration manifest")
    detector = StableFirstMilestoneDetector(
        required_stable_steps=stable_steps,
        deadline=event_deadline,
    )
    env = None
    started = time.monotonic()
    event: dict[str, Any] | None = None
    full_state: dict[str, Any] | None = None
    original_prompt = ""
    current_prompt = ""
    final_predicates: dict[str, bool] = {}
    final_reward = 0.0
    final_done = False
    policy_steps = 0
    prefix_policy_steps_replayed = 0
    custom_success = False
    termination = "policy_step_budget_exhausted"
    action_schema_valid = True
    try:
        set_seed(seed)
        env, original_prompt = create_libero_env(task, cfg)
        if original_prompt != entry["description"]:
            raise ValueError("runtime prompt differs from the frozen calibration manifest")
        current_prompt = original_prompt
        env.reset()
        obs = env.set_init_state(initial_state)
        for warmup_step in range(10):
            obs, final_reward, final_done, _ = env.step(get_dummy_action("openvla"))
        resize_size = get_image_resize_size(runtime_model_cfg)
        action_low, action_high, action_spec_source = _action_spec(
            env, int(config["checkpoint"]["expected_action_dim"])
        )
        view = LiberoStateView(env)
        pair_key = f"task01:state{state_id:02d}:seed{seed}"
        with trace_path.open("x", encoding="utf-8", buffering=1) as trace:
            _write_trace(
                trace,
                {
                    "record_type": "start",
                    "mode": mode,
                    "pair_key": pair_key,
                    "seed": seed,
                    "state_id": state_id,
                    "initial_state_sha256": initial_state_sha256,
                    "original_prompt": original_prompt,
                    "policy_budget": policy_budget,
                    "stable_steps": stable_steps,
                    "event_deadline": event_deadline,
                    "prompt_variant": prompt_variant,
                    "prefix_trace_steps_available": len(prefix_records),
                    "action_spec_source": action_spec_source,
                },
            )
            for policy_step in range(policy_budget):
                prefix = (
                    prefix_records[policy_step]
                    if event is None and policy_step < len(prefix_records)
                    else None
                )
                if prefix is not None:
                    replay_started = time.monotonic()
                    obs, reward, done, _ = env.step(prefix["environment_action"])
                    environment_step_seconds = time.monotonic() - replay_started
                    raw_action = prefix.get("raw_action", [])
                    environment_action = prefix["environment_action"]
                    prefix_policy_steps_replayed += 1
                    inference_seconds = 0.0
                    prefix_replayed = True
                    expected_reward = float(prefix.get("reward", reward))
                    expected_done = bool(prefix.get("done", done))
                    if float(reward) != expected_reward or bool(done) != expected_done:
                        raise RuntimeError(
                            "prefix replay diverged from the frozen calibration trace"
                        )
                else:
                    step = execute_policy_step(
                        cfg=runtime_model_cfg,
                        model=model,
                        processor=processor,
                        env=env,
                        obs=obs,
                        prompt=current_prompt,
                        resize_size=resize_size,
                    )
                    obs = step.next_obs
                    reward = step.reward
                    done = step.done
                    raw_action = step.raw_action
                    environment_action = step.env_action
                    inference_seconds = step.inference_seconds
                    environment_step_seconds = step.env_step_seconds
                    prefix_replayed = False
                policy_steps = policy_step + 1
                final_reward = float(reward)
                final_done = bool(done)
                final_predicates = _predicates(view)
                validation = validate_openvla_action(
                    raw_action,
                    environment_action,
                    expected_dim=int(config["checkpoint"]["expected_action_dim"]),
                    action_low=action_low,
                    action_high=action_high,
                )
                action_schema_valid = action_schema_valid and bool(validation["passed"])
                _write_trace(
                    trace,
                    {
                        "record_type": "policy_step",
                        "policy_step": policy_step,
                        "mode": mode,
                        "prompt": current_prompt,
                        "raw_action": raw_action,
                        "environment_action": environment_action,
                        "reward": final_reward,
                        "done": final_done,
                        "predicates": final_predicates,
                        "inference_seconds": inference_seconds,
                        "environment_step_seconds": environment_step_seconds,
                        "prefix_replayed": prefix_replayed,
                        "action_schema_valid": validation["passed"],
                    },
                )
                if not validation["passed"]:
                    raise RuntimeError("OpenVLA action contract failed")

                if event is None:
                    milestone = detector.observe(policy_step, final_predicates)
                    if milestone is not None:
                        event = build_replacement_event(
                            milestone,
                            pair_key=pair_key,
                            previous_state_version=0,
                            replacement_object=REPLACEMENT_OBJECT,
                        )
                        full_state = build_oracle_full_state(
                            event, previous_state_version=0
                        )
                        validate_oracle_full_state(
                            full_state,
                            event,
                            previous_state_version=0,
                            physically_true_objects=tuple(
                                name for name in ORIGINAL_OBJECTS if final_predicates[name]
                            ),
                        )
                        compiled_prompt = _prompt_for_variant(prompt_variant, full_state)
                        if mode == "oracle_full":
                            current_prompt = compiled_prompt
                        _write_trace(
                            trace,
                            {
                                "record_type": "semantic_event",
                                "policy_step": policy_step,
                                "mode": mode,
                                "event": event,
                                "accepted_full_state": full_state,
                                "compiled_prompt": compiled_prompt,
                                "prompt_variant": prompt_variant,
                                "prompt_applied": mode == "oracle_full",
                                "predicates": final_predicates,
                            },
                        )

                if event is not None and full_state is not None:
                    custom_success = current_goal_success(full_state, final_predicates)
                    if custom_success:
                        termination = "current_goal_satisfied"
                        break
                    if final_done or final_reward >= 1.0:
                        termination = "original_task_terminal_before_current_goal"
                        break
                elif final_done or final_reward >= 1.0:
                    termination = "original_task_terminal_without_stable_event"
                    break
            else:
                termination = "policy_step_budget_exhausted"
    finally:
        if env is not None:
            env.close()

    event_reached = event is not None
    done_object = str(event["done_object"]) if event else None
    pending_object = str(event["pending_object"]) if event else None
    retained_progress = bool(done_object and final_predicates.get(done_object, False))
    result = {
        "schema_version": "semantic-replacement-canary-v1",
        "complete": True,
        "mode": mode,
        "task_suite": "libero_10",
        "task_id": task_id,
        "state_id": state_id,
        "seed": seed,
        "initial_state_sha256": initial_state_sha256,
        "git": dict(git),
        "config_hash": canonical_hash(config),
        "checkpoint": {
            "repository": config["checkpoint"]["repository"],
            "revision": config["checkpoint"]["revision"],
            "path": config["checkpoint"]["path"],
            "resolved_unnorm_key": resolved_unnorm_key,
        },
        "original_prompt": original_prompt,
        "final_prompt": current_prompt,
        "event_reached": event_reached,
        "event": event,
        "accepted_full_state": full_state,
        "done_object": done_object,
        "pending_object": pending_object,
        "replacement_object": REPLACEMENT_OBJECT,
        "current_goal_success": custom_success,
        "valid_progress_retained": retained_progress,
        "final_predicates": final_predicates,
        "original_task_success": bool(final_done or final_reward >= 1.0),
        "termination_reason": termination,
        "policy_step_budget": policy_budget,
        "policy_steps_consumed": policy_steps,
        "warmup_steps_consumed": 10,
        "prompt_variant": prompt_variant,
        "prefix_policy_steps_replayed": prefix_policy_steps_replayed,
        "action_schema_valid": action_schema_valid,
        "manual_intervention": False,
        "reset_after_start": False,
        "rollback": False,
        "runtime_seconds": time.monotonic() - started,
        "gpu": _cuda_memory(),
        "artifacts": {
            "trace": str(trace_path.resolve()),
            "episode": str(episode_path.resolve()),
        },
    }
    _atomic_json(episode_path, result)
    return result


def main() -> None:
    args = parse_args()
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if not visible or "," in visible:
        raise RuntimeError("semantic replacement canary requires exactly one visible GPU")
    modes = tuple(item.strip() for item in args.modes.split(",") if item.strip())
    if not modes or any(mode not in MODES for mode in modes):
        raise ValueError(f"modes must be a nonempty subset of {MODES}")
    config = load_v2_config(args.config)
    if args.policy_budget != int(config["runtime"]["policy_step_budget"]):
        raise ValueError("canary must use the frozen 520-step policy budget")
    git = _git_identity()
    if not git["clean"]:
        raise RuntimeError(f"canary requires a clean committed worktree: {git['status']}")
    runtime_identity = validate_runtime_task_identity(config)
    entries = validate_static_manifest(config, args.manifest)
    entry = _find_entry(entries, args.state_id)
    if runtime_identity["task_identity"]["1"]["state_sha256"][str(args.state_id)] != entry[
        "initial_state_sha256"
    ]:
        raise ValueError("runtime task identity does not match the frozen entry")
    prefix_records = _load_prefix_records(args.prefix_trace)
    args.output_root.mkdir(parents=True, exist_ok=True)
    worker_root = args.output_root / f"state{args.state_id:02d}"
    worker_root.mkdir(exist_ok=False)
    cfg = _model_cfg(
        config,
        task_id=1,
        state_id=args.state_id,
        seed=int(entry["seed"]),
    )
    model = processor = runtime_model_cfg = None
    try:
        model, processor, runtime_model_cfg, resolved_unnorm_key = load_model_and_processor(cfg)
        results = []
        for mode in modes:
            results.append(
                run_episode(
                    mode=mode,
                    entry=entry,
                    config=config,
                    model=model,
                    processor=processor,
                    runtime_model_cfg=runtime_model_cfg,
                    resolved_unnorm_key=resolved_unnorm_key,
                    output_dir=worker_root / mode,
                    stable_steps=args.stable_steps,
                    event_deadline=args.event_deadline,
                    policy_budget=args.policy_budget,
                    git=git,
                    prompt_variant=args.prompt_variant,
                    prefix_records=prefix_records,
                )
            )
        summary = {
            "schema_version": "semantic-replacement-canary-worker-summary-v1",
            "physical_gpu": visible,
            "state_id": args.state_id,
            "modes": list(modes),
            "results": [
                {
                    "mode": item["mode"],
                    "prompt_variant": item["prompt_variant"],
                    "event_reached": item["event_reached"],
                    "event_step": (item["event"] or {}).get("world_version"),
                    "current_goal_success": item["current_goal_success"],
                    "valid_progress_retained": item["valid_progress_retained"],
                    "termination_reason": item["termination_reason"],
                    "policy_steps_consumed": item["policy_steps_consumed"],
                    "runtime_seconds": item["runtime_seconds"],
                }
                for item in results
            ],
        }
        _atomic_json(worker_root / "summary.json", summary)
        print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    finally:
        # The shared helper only performs GC/CUDA cache cleanup.  Drop the
        # strong references here before invoking it.
        model = processor = runtime_model_cfg = None
        unload_torch_model_refs()


if __name__ == "__main__":
    main()
