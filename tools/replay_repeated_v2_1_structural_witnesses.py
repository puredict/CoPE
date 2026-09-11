#!/usr/bin/env python3
"""Replay sealed calibration actions to recover exact per-goal witnesses.

The original action bytes and outcome remain authoritative.  This zero-model,
zero-provider replay adds only task-progress observations for calibration shards
whose frozen source predated the all-task predicate registry.  Any divergence in
terminal success fails closed; no trajectory is retried or reclassified.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope_benchmark.task_progress import (  # noqa: E402
    LiberoStateView,
    ProgressTracker,
    get_task_definition,
)


_WORKER_SUITE: Any | None = None


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _encoded(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def _csv(rows: Sequence[Mapping[str, Any]]) -> bytes:
    rows = list(rows)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]) if rows else ())
    writer.writeheader(); writer.writerows(rows)
    return output.getvalue().encode()


def _episode_dirs(inputs: Sequence[Path]) -> list[Path]:
    result = []
    for root in inputs:
        if not (root / "COMPLETED_SUBSET.txt").is_file() or (root / "INFRASTRUCTURE_STOP.txt").exists():
            raise ValueError(f"incomplete calibration shard: {root}")
        result.extend(sorted(root.glob("task_*_state_*_seed_*")))
    if len(result) != 100:
        raise ValueError(f"expected 100 sealed calibration episodes, found {len(result)}")
    return result


def _sealed_success(env: Any) -> bool:
    for candidate, name in ((env, "check_success"), (env, "_check_success"),
                            (getattr(env, "env", None), "check_success"),
                            (getattr(env, "env", None), "_check_success")):
        if candidate is not None and hasattr(candidate, name):
            return bool(getattr(candidate, name)())
    raise RuntimeError("LIBERO exact success reader unavailable")


def _replay_episode(suite: Any, episode: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from libero_experiment_core import ExperimentConfig, create_libero_env, set_seed
    record_path, trace_path = episode / "CALIBRATION_RECORD.txt", episode / "ACTION_TRACE.txt"
    record = json.loads(record_path.read_text())
    if _sha(trace_path) != record["full_trace_sha256"]:
        raise ValueError(f"trace hash differs: {episode}")
    task_id, state_id, seed = (record[key] for key in ("task_id", "initial_state_id", "policy_seed"))
    definition = get_task_definition("libero_10", task_id)
    state = np.asarray(suite.get_task_init_states(task_id)[state_id]).copy()
    if hashlib.sha256(state.tobytes()).hexdigest() != record["initial_state_sha256"]:
        raise ValueError(f"initial state hash differs: {episode}")
    cfg = ExperimentConfig(
        checkpoint="zero-model-action-replay", task_suite="libero_10", unnorm_key="libero_10",
        task_id=task_id, trial_id=state_id, mode="clean", max_steps=520,
        num_steps_wait=10, seed=seed, resolution=64, enable_auto_disturbance=False,
    )
    set_seed(seed)
    env, prompt = create_libero_env(suite.get_task(task_id), cfg)
    samples = []
    try:
        if prompt != definition.language:
            raise ValueError("replay task instruction differs")
        env.reset(); env.set_init_state(state)
        tracker, view = ProgressTracker(definition), LiberoStateView(env)
        initial = tracker.sample(view, 0).to_dict()
        samples.append({"environment_control": 0, "policy_step": 0,
                        "record_type": "initial", "progress": initial})
        controls = 0
        with trace_path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                source = json.loads(line)
                if source.get("record_type") not in {"settling_intent", "environment_intent"}:
                    continue
                action = np.asarray(source["environment_action"], dtype=float)
                if action.shape != (7,) or not np.isfinite(action).all():
                    raise ValueError(f"invalid sealed action at {episode}:{line_number}")
                _, _, _, _ = env.step(action)
                controls += 1
                policy_step = int(source.get("policy_step", 0))
                sample = tracker.sample(view, policy_step).to_dict()
                samples.append({
                    "environment_control": controls, "policy_step": policy_step,
                    "source_trace_line": line_number, "record_type": source["record_type"],
                    "progress": sample,
                })
        success = _sealed_success(env)
        if success is not record["success"]:
            raise ValueError(
                f"replay terminal success diverged for task={task_id},state={state_id}: "
                f"sealed={record['success']} replay={success}"
            )
        expected_controls = record["policy_steps_consumed"] + 10
        if controls != expected_controls:
            raise ValueError(f"replay control count differs for {episode}: {controls}!={expected_controls}")
        return {
            "task_id": task_id, "initial_state_id": state_id, "policy_seed": seed,
            "sealed_record_sha256": _sha(record_path), "sealed_trace_sha256": _sha(trace_path),
            "sealed_success": record["success"], "replay_success": success,
            "environment_controls_replayed": controls,
            "progress_source_sha256": _sha(ROOT / "cope_benchmark/task_progress.py"),
        }, samples
    finally:
        env.close()


def _replay_episode_worker(episode: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load one process-local benchmark suite and replay an isolated episode."""
    global _WORKER_SUITE
    if _WORKER_SUITE is None:
        from libero_experiment_core import get_benchmark_suite
        _WORKER_SUITE = get_benchmark_suite("libero_10")
    return _replay_episode(_WORKER_SUITE, Path(episode))


def _witnesses(meta: Mapping[str, Any], samples: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    definition = get_task_definition("libero_10", int(meta["task_id"]))
    commitments = [predicate.name for predicate in definition.predicates if predicate.commitment]
    rows = []
    for name in commitments:
        truth = [sample["progress"]["current"][name] for sample in samples]
        first_true = next((index for index, value in enumerate(truth) if value), None)
        intervals = []
        for index in range(len(samples) - 1):
            current = samples[index]["progress"]["current"]
            following = samples[index + 1]["progress"]["current"]
            if current[name] and following[name] and any(
                    not current[other] for other in commitments if other != name):
                intervals.append({
                    "start_control": samples[index]["environment_control"],
                    "end_control": samples[index + 1]["environment_control"],
                    "start_policy_step": samples[index]["policy_step"],
                    "end_policy_step": samples[index + 1]["policy_step"],
                    "source_trace_line": samples[index].get("source_trace_line"),
                })
        regression = any(truth[index] and not truth[index + 1]
                         for index in range(len(truth) - 1))
        rows.append({
            "task_id": meta["task_id"], "initial_state_id": meta["initial_state_id"],
            "policy_seed": meta["policy_seed"], "milestone": name,
            "observed_true": first_true is not None,
            "first_true_environment_control": "" if first_true is None else samples[first_true]["environment_control"],
            "terminally_satisfied": bool(truth[-1]),
            "preserved_while_another_goal_pending": bool(intervals),
            "first_preservation_witness": json.dumps(intervals[0], separators=(",", ":")) if intervals else "",
            "observed_regression": regression,
            "sealed_trace_sha256": meta["sealed_trace_sha256"],
        })
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    if os.environ.get("COPE_ALLOW_FORMAL_RUN"):
        raise ValueError("structural replay requires formal launch authorization absent")
    if not 1 <= args.workers <= 16:
        raise ValueError("workers must be in 1..16")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    episodes = _episode_dirs([path.resolve() for path in args.input])
    episode_rows, witness_rows = [], []
    if args.workers == 1:
        from libero_experiment_core import get_benchmark_suite
        suite = get_benchmark_suite("libero_10")
        results = (_replay_episode(suite, episode) for episode in episodes)
        executor = None
    else:
        executor = ProcessPoolExecutor(max_workers=args.workers)
        results = executor.map(_replay_episode_worker, map(str, episodes), chunksize=1)
    try:
        for meta, samples in results:
            episode_rows.append(meta)
            witness_rows.extend(_witnesses(meta, samples))
            print(json.dumps({"replayed": [meta["task_id"], meta["initial_state_id"]],
                              "success": meta["replay_success"]}), flush=True)
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
    episode_rows.sort(key=lambda row: (row["task_id"], row["initial_state_id"]))
    witness_rows.sort(key=lambda row: (row["task_id"], row["initial_state_id"], row["milestone"]))
    summaries = []
    for task_id in range(10):
        task_rows = [row for row in witness_rows if row["task_id"] == task_id]
        names = sorted({row["milestone"] for row in task_rows})
        summaries.append({
            "task_id": task_id, "replayed_episodes": sum(row["task_id"] == task_id for row in episode_rows),
            "commitment_predicate_count": len(names),
            "two_independently_verifiable_milestones": len(names) >= 2,
            "milestones_observed_true": sum(any(row["observed_true"] for row in task_rows
                                                 if row["milestone"] == name) for name in names),
            "completed_milestone_preservable": any(
                row["preserved_while_another_goal_pending"] for row in task_rows),
            "preservation_witness_count": sum(
                row["preserved_while_another_goal_pending"] for row in task_rows),
            "all_sealed_outcomes_reproduced": all(
                row["sealed_success"] is row["replay_success"] for row in episode_rows
                if row["task_id"] == task_id),
        })
    _write(output / "REPLAY_EPISODE_ADMISSION.csv", _csv(episode_rows))
    _write(output / "REPLAY_MILESTONE_WITNESSES.csv", _csv(witness_rows))
    _write(output / "REPLAY_STRUCTURAL_WITNESS_SUMMARY.csv", _csv(summaries))
    receipt = {
        "schema_version": "repeated_v2_1_structural_replay_receipt_v1",
        "episodes_replayed": len(episode_rows),
        "all_sealed_outcomes_reproduced": all(row["sealed_success"] is row["replay_success"]
                                                for row in episode_rows),
        "provider_calls": 0, "vla_calls": 0, "formal_trajectories": 0,
        "artifact_sha256": {path.name: _sha(path) for path in output.iterdir()},
    }
    _write(output / "RECEIPT.json", _encoded(receipt))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
