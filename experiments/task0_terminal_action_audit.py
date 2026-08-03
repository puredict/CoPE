#!/usr/bin/env python3
"""Development-only terminal butter placement audit for both task-0 prefixes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import subprocess
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cope.semantic_replacement import RECEPTACLE
from cope.types import canonical_json, stable_hash
from experiments.multitask_prefix_audit import CONTROLLER_CONFIG
from experiments.sequential_formal_runner import create_prefixed_env, predicate_snapshot, simulator_hash
from libero_experiment_core import get_benchmark_suite


STATE_IDS = tuple(range(10))
SPECS = (
    {
        "prefix_orientation": "forward",
        "done_object": "alphabet_soup_1",
        "initial_pending_object": "tomato_sauce_1",
        "replacement_c": "cream_cheese_1",
        "replacement_d": "butter_1",
    },
    {
        "prefix_orientation": "reverse",
        "done_object": "tomato_sauce_1",
        "initial_pending_object": "alphabet_soup_1",
        "replacement_c": "cream_cheese_1",
        "replacement_d": "butter_1",
    },
)
EXPECTED_CONFIG_HASH = "56171aef20a9f60e335259ff10abe7c211f6594a98b52b09864effcc7b1d988a"
PROVIDER_ENV_NAMES = (
    "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=64)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip():
        raise RuntimeError("terminal-action audit requires a clean committed worktree")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if stable_hash(asdict(CONTROLLER_CONFIG)) != EXPECTED_CONFIG_HASH:
        raise RuntimeError("controller configuration hash drift")
    credentials = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if credentials:
        raise RuntimeError("development audit refuses credentials: " + ",".join(credentials))
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "schema": "cope-task0-terminal-action-audit-v1",
        "runtime_git_commit": commit,
        "authorized_task_id": 0,
        "authorized_state_ids": STATE_IDS,
        "specs": SPECS,
        "controller_config_sha256": EXPECTED_CONFIG_HASH,
        "provider_calls": 0,
        "formal_states_indexed": False,
    }
    (args.output_dir / "00_METADATA.txt").write_text(
        canonical_json(metadata) + "\n", encoding="utf-8"
    )
    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(0)
    states = suite.get_task_init_states(0)
    journal = args.output_dir / "01_JOURNAL.txt"
    rows: list[dict[str, Any]] = []
    for spec in SPECS:
        for state_id in STATE_IDS:
            row: dict[str, Any] = {
                "task_id": 0,
                "state_id": state_id,
                "prefix_orientation": spec["prefix_orientation"],
                "done_object": spec["done_object"],
                "b_object": spec["initial_pending_object"],
                "c_object": spec["replacement_c"],
                "d_object": spec["replacement_d"],
                "prefix_success": False,
                "terminal_placement_success": False,
                "terminal_stability_success": False,
                "cell_success": False,
                "failure_class": "",
                "prefix_action_sha256": "",
                "final_action_sha256": "",
                "simulator_sha256": "",
                "action_count": 0,
                "prefix_trace": "",
                "terminal_trace": "",
                "regrasp_activated": False,
            }
            env = None
            try:
                env, controller, view, prefix = create_prefixed_env(
                    task, states[state_id], spec, args.resolution
                )
                row["prefix_success"] = prefix["eligible"]
                row["prefix_action_sha256"] = prefix["action_sha256"]
                row["prefix_trace"] = canonical_json(prefix["trace"])
                if not prefix["eligible"]:
                    row["failure_class"] = "prefix_ineligible"
                else:
                    placement = controller.pick_and_place("butter_1", RECEPTACLE)
                    row["terminal_placement_success"] = placement.success
                    trace = []
                    for index in range(5):
                        controller.hold(f"terminal_audit_stability_{index + 1}", 1, gripper=-1.0)
                        trace.append(predicate_snapshot(view, spec))
                    row["terminal_trace"] = canonical_json(trace)
                    expected = {"done": True, "b": False, "c": False, "d": True}
                    stable = len(trace) == 5 and all(item == expected for item in trace)
                    row["terminal_stability_success"] = stable
                    row["cell_success"] = bool(placement.success and stable)
                    if not placement.success:
                        row["failure_class"] = f"terminal_skill:{placement.failure_reason}"
                    elif not stable:
                        row["failure_class"] = "terminal_predicate_stability_failure"
                    row["regrasp_activated"] = any(
                        phase.phase.startswith("regrasp_") for phase in placement.phases
                    )
                row["final_action_sha256"] = controller.action_prefix_sha256()
                row["action_count"] = controller.total_steps
                row["simulator_sha256"] = simulator_hash(env)
            except Exception as exc:
                row["failure_class"] = f"exception:{type(exc).__name__}:{exc}"
            finally:
                if env is not None:
                    env.close()
            rows.append(row)
            with journal.open("a", encoding="utf-8") as handle:
                handle.write(canonical_json(row) + "\n")
            print(canonical_json(row), flush=True)
    with (args.output_dir / "02_RESULTS.csv").open(
        "x", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    successes = sum(bool(row["cell_success"]) for row in rows)
    failures = Counter(row["failure_class"] for row in rows if not row["cell_success"])
    passed = successes == len(rows)
    (args.output_dir / "03_RESULT.md").write_text(
        "# Task-0 terminal-action audit result\n\n"
        f"- Gate: **{'PASS' if passed else 'FAIL'}**\n"
        f"- Passed cells: **{successes}/{len(rows)}**\n"
        f"- Failures: `{canonical_json(dict(sorted(failures.items())))}`\n"
        f"- Regrasp activations: **{sum(bool(row['regrasp_activated']) for row in rows)}/{len(rows)}**\n"
        "- Provider calls: **0**\n- Formal states indexed: **0**\n",
        encoding="utf-8",
    )
    artifacts = sorted(args.output_dir.iterdir())
    (args.output_dir / "04_SHA256SUMS.txt").write_text(
        "\n".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in artifacts) + "\n",
        encoding="utf-8",
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
