#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
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
from cope.semantic_cancellation import (  # noqa: E402
    build_cancellation_event,
    build_oracle_cancellation_state,
    cancellation_compliance,
    compile_execution_directive,
    validate_oracle_cancellation_state,
)
from cope.semantic_replacement import (  # noqa: E402
    ALLOWED_OBJECTS,
    ORIGINAL_OBJECTS,
    RECEPTACLE,
    StableFirstMilestoneDetector,
)
from cope_benchmark.task_progress import LiberoStateView  # noqa: E402
from experiments.openvla_libero_calibration import (  # noqa: E402
    _action_spec,
    _atomic_json,
    _model_cfg,
)
from experiments.semantic_replacement_canary import (  # noqa: E402
    _git_identity,
    _load_prefix_records,
    _write_trace,
)
from libero_experiment_core import (  # noqa: E402
    create_libero_env,
    get_benchmark_suite,
    get_dummy_action,
    set_seed,
)


DEFAULT_CONFIG = ROOT / "configs/openvla_libero_10_calibration_v2.yaml"
DEFAULT_MANIFEST = ROOT / "manifests/openvla_libero_10_calibration_v2.jsonl"
MODES = ("no_edit", "oracle_cancel_halt")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--state-id", type=int, required=True)
    parser.add_argument("--modes", default=",".join(MODES))
    parser.add_argument("--stable-steps", type=int, default=5)
    parser.add_argument("--event-deadline", type=int, default=300)
    parser.add_argument("--verification-hold-steps", type=int, default=30)
    return parser.parse_args()


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


def _predicates(view: LiberoStateView) -> dict[str, bool]:
    return {
        name: view.libero_predicate("in", (name, RECEPTACLE))
        for name in sorted(ALLOWED_OBJECTS)
    }


def run_episode(
    *,
    mode: str,
    entry: Mapping[str, Any],
    config: Mapping[str, Any],
    prefix_records: tuple[dict[str, Any], ...],
    output_dir: Path,
    stable_steps: int,
    event_deadline: int,
    verification_hold_steps: int,
    git: Mapping[str, Any],
) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    output_dir.mkdir(parents=True, exist_ok=False)
    trace_path = output_dir / "trace.jsonl"
    episode_path = output_dir / "episode.json"
    state_id = int(entry["initial_state_id"])
    seed = int(entry["seed"])
    cfg = _model_cfg(config, task_id=1, state_id=state_id, seed=seed)
    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(1)
    initial_state = suite.get_task_init_states(1)[state_id]
    initial_state_sha256 = hashlib.sha256(np.asarray(initial_state).tobytes()).hexdigest()
    if initial_state_sha256 != entry["initial_state_sha256"]:
        raise ValueError("initial state hash differs from the frozen calibration manifest")
    if not prefix_records:
        raise ValueError("cancellation canary requires a frozen successful prefix trace")

    env = None
    started = time.monotonic()
    detector = StableFirstMilestoneDetector(
        required_stable_steps=stable_steps,
        deadline=event_deadline,
    )
    event: dict[str, Any] | None = None
    full_state: dict[str, Any] | None = None
    final_predicates: dict[str, bool] = {}
    policy_steps = 0
    post_event_policy_actions = 0
    verification_steps = 0
    cancelled_goal_violated = False
    action_schema_valid = True
    termination = "trace_exhausted_without_event"
    try:
        set_seed(seed)
        env, prompt = create_libero_env(task, cfg)
        if prompt != entry["description"]:
            raise ValueError("runtime prompt differs from the frozen calibration manifest")
        env.reset()
        obs = env.set_init_state(initial_state)
        for _ in range(10):
            obs, _, _, _ = env.step(get_dummy_action("openvla"))
        view = LiberoStateView(env)
        action_low, action_high, action_spec_source = _action_spec(
            env, int(config["checkpoint"]["expected_action_dim"])
        )
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
                    "source_trace": str(Path(str(prefix_records[0]["_source_trace"]))),
                    "stable_steps": stable_steps,
                    "event_deadline": event_deadline,
                    "verification_hold_steps": verification_hold_steps,
                    "action_spec_source": action_spec_source,
                },
            )
            for policy_step, prior in enumerate(prefix_records):
                obs, reward, done, _ = env.step(prior["environment_action"])
                policy_steps = policy_step + 1
                final_predicates = _predicates(view)
                validation = validate_openvla_action(
                    prior.get("raw_action", []),
                    prior["environment_action"],
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
                        "environment_action": prior["environment_action"],
                        "reward": float(reward),
                        "done": bool(done),
                        "predicates": final_predicates,
                        "source_action_replayed": True,
                        "post_event": event is not None,
                        "action_schema_valid": validation["passed"],
                    },
                )
                if not validation["passed"]:
                    raise RuntimeError("replayed OpenVLA action contract failed")
                if bool(done) != bool(prior.get("done", done)) or abs(
                    float(reward) - float(prior.get("reward", reward))
                ) > 1e-9:
                    raise RuntimeError("frozen trace replay diverged")

                if event is None:
                    milestone = detector.observe(policy_step, final_predicates)
                    if milestone is not None:
                        event = build_cancellation_event(milestone, pair_key=pair_key)
                        full_state = build_oracle_cancellation_state(event)
                        validate_oracle_cancellation_state(
                            full_state,
                            event,
                            previous_state_version=0,
                            physically_true_objects=tuple(
                                name
                                for name in ORIGINAL_OBJECTS
                                if final_predicates[name]
                            ),
                        )
                        directive = compile_execution_directive(full_state)
                        _write_trace(
                            trace,
                            {
                                "record_type": "semantic_event",
                                "policy_step": policy_step,
                                "mode": mode,
                                "event": event,
                                "accepted_full_state": full_state,
                                "execution_directive": directive,
                                "directive_applied": mode == "oracle_cancel_halt",
                                "predicates": final_predicates,
                            },
                        )
                        if mode == "oracle_cancel_halt":
                            termination = "halted_after_authorized_cancellation"
                            break
                else:
                    post_event_policy_actions += 1

                if event is not None and bool(
                    final_predicates.get(str(event["pending_object"]), False)
                ):
                    cancelled_goal_violated = True
                    termination = "cancelled_goal_executed"
                    break
                if done or reward >= 1.0:
                    termination = "original_task_terminal_after_cancellation"
                    break
            else:
                termination = (
                    "trace_exhausted_without_event"
                    if event is None
                    else "trace_exhausted_without_cancelled_goal_violation"
                )

            if mode == "oracle_cancel_halt" and event is not None:
                for verification_step in range(verification_hold_steps):
                    obs, reward, done, _ = env.step(get_dummy_action("openvla"))
                    verification_steps += 1
                    final_predicates = _predicates(view)
                    _write_trace(
                        trace,
                        {
                            "record_type": "verification_hold_step",
                            "verification_step": verification_step,
                            "mode": mode,
                            "environment_action": get_dummy_action("openvla"),
                            "reward": float(reward),
                            "done": bool(done),
                            "predicates": final_predicates,
                            "excluded_from_policy_action_budget": True,
                        },
                    )
                    if not cancellation_compliance(event, final_predicates):
                        termination = "halt_verification_failed"
                        break
    finally:
        if env is not None:
            env.close()

    cancellation_success = bool(
        event is not None
        and cancellation_compliance(event, final_predicates)
        and not cancelled_goal_violated
        and (
            mode != "oracle_cancel_halt"
            or (
                termination == "halted_after_authorized_cancellation"
                and verification_steps == verification_hold_steps
            )
        )
    )
    result = {
        "schema_version": "semantic-cancellation-canary-v1",
        "complete": True,
        "mode": mode,
        "task_suite": "libero_10",
        "task_id": 1,
        "state_id": state_id,
        "seed": seed,
        "initial_state_sha256": initial_state_sha256,
        "git": dict(git),
        "config_hash": canonical_hash(config),
        "event_reached": event is not None,
        "event": event,
        "accepted_full_state": full_state,
        "cancellation_success": cancellation_success,
        "cancelled_goal_violated": cancelled_goal_violated,
        "valid_progress_retained": bool(
            event
            and final_predicates.get(str(event["done_object"]), False)
        ),
        "final_predicates": final_predicates,
        "termination_reason": termination,
        "policy_steps_consumed": policy_steps,
        "post_event_policy_actions": post_event_policy_actions,
        "verification_hold_steps": verification_steps,
        "verification_steps_excluded_from_policy_budget": True,
        "action_schema_valid": action_schema_valid,
        "manual_intervention": False,
        "reset_after_start": False,
        "rollback": False,
        "runtime_seconds": time.monotonic() - started,
        "artifacts": {
            "trace": str(trace_path.resolve()),
            "episode": str(episode_path.resolve()),
        },
    }
    _atomic_json(episode_path, result)
    return result


def main() -> None:
    args = parse_args()
    modes = tuple(item.strip() for item in args.modes.split(",") if item.strip())
    if not modes or any(mode not in MODES for mode in modes):
        raise ValueError(f"modes must be a nonempty subset of {MODES}")
    config = load_v2_config(args.config)
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
    prefix_records = tuple(
        {**row, "_source_trace": str(args.trace.resolve())}
        for row in _load_prefix_records(args.trace)
    )
    args.output_root.mkdir(parents=True, exist_ok=True)
    worker_root = args.output_root / f"state{args.state_id:02d}"
    worker_root.mkdir(exist_ok=False)
    results = [
        run_episode(
            mode=mode,
            entry=entry,
            config=config,
            prefix_records=prefix_records,
            output_dir=worker_root / mode,
            stable_steps=args.stable_steps,
            event_deadline=args.event_deadline,
            verification_hold_steps=args.verification_hold_steps,
            git=git,
        )
        for mode in modes
    ]
    summary = {
        "schema_version": "semantic-cancellation-worker-summary-v1",
        "state_id": args.state_id,
        "modes": list(modes),
        "gpu_inference_used": False,
        "results": [
            {
                "mode": item["mode"],
                "event_reached": item["event_reached"],
                "event_step": (item["event"] or {}).get("world_version"),
                "cancellation_success": item["cancellation_success"],
                "cancelled_goal_violated": item["cancelled_goal_violated"],
                "valid_progress_retained": item["valid_progress_retained"],
                "post_event_policy_actions": item["post_event_policy_actions"],
                "termination_reason": item["termination_reason"],
                "runtime_seconds": item["runtime_seconds"],
            }
            for item in results
        ],
    }
    _atomic_json(worker_root / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
