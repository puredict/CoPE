#!/usr/bin/env python3
"""Credential-free cold preflight for the 320-call formal manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import subprocess
from collections import Counter
from pathlib import Path

from cope.providers.openai_compatible import OpenAICompatibleRecoveryProvider
from cope.sequential_prompting import (
    ARMS,
    CONTRACTS,
    MAX_COMPLETION_TOKENS,
    MAX_PROMPT_TOKENS,
    MODEL,
    REASONING_EFFORT,
    TEMPERATURE,
    TIMEOUT_SECONDS,
    build_sequential_recovery_input,
)
from cope.sequential_semantics import (
    build_expected_next_state,
    build_initial_sequence_state,
    build_sequence_event,
)
from cope.types import canonical_json, stable_hash


PROVIDER_ENV_NAMES = (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def validate_manifest(rows: list[dict[str, str]]) -> None:
    if len(rows) != 40 or len({row["sequence_id"] for row in rows}) != 40:
        raise ValueError("formal manifest must contain 40 unique sequences")
    counts = Counter((int(row["state_id"]), row["sequence_type"]) for row in rows)
    expected = {
        (state_id, sequence_type)
        for state_id in range(10, 30)
        for sequence_type in ("replace_then_cancel", "replace_then_replace")
    }
    if set(counts) != expected or any(value != 1 for value in counts.values()):
        raise ValueError("formal state/sequence assignment is noncanonical")
    for row in rows:
        state_id = int(row["state_id"])
        expected_orientation = "forward" if state_id < 20 else "reverse"
        if row["prefix_orientation"] != expected_orientation:
            raise ValueError("prefix orientation assignment is wrong")
        if tuple(row["arm_order"].split(";")) != tuple(dict.fromkeys(row["arm_order"].split(";"))):
            raise ValueError("arm order contains duplicates")
        if set(row["arm_order"].split(";")) != set(ARMS):
            raise ValueError("arm order is incomplete")
        if int(row["provider_calls_per_arm"]) != 2:
            raise ValueError("each sequence must make two calls per arm")
        if row["model"] != MODEL or float(row["temperature"]) != TEMPERATURE:
            raise ValueError("provider configuration drift")


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip():
        raise RuntimeError("formal preflight requires a clean committed worktree")
    runtime_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    populated = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if populated:
        raise RuntimeError("cold preflight refuses credentials: " + ",".join(populated))
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    validate_manifest(rows)
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    requests = []
    for row in rows:
        provider = OpenAICompatibleRecoveryProvider(
            {
                "provider": "openrouter",
                "model": MODEL,
                "reasoning_effort": REASONING_EFFORT,
                "temperature": TEMPERATURE,
                "seed": int(row["seed"]),
                "max_prompt_tokens": MAX_PROMPT_TOKENS,
                "max_completion_tokens": MAX_COMPLETION_TOKENS,
                "max_retries": 0,
                "timeout_seconds": TIMEOUT_SECONDS,
            }
        )
        available = (
            row["done_object"], row["initial_pending_object"],
            row["replacement_c"], "butter_1",
        )
        initial = build_initial_sequence_state(
            sequence_id=row["sequence_id"],
            done_object=row["done_object"],
            pending_object=row["initial_pending_object"],
            available_objects=available,
            world_version=int(row["state_id"]) * 100,
        )
        event1 = build_sequence_event(
            initial, sequence_id=row["sequence_id"], step_index=1,
            done_object=row["done_object"], event_type="replace_pending_goal",
            replacement_object=row["replacement_c"],
            world_version=int(row["state_id"]) * 100 + 1,
        )
        middle = build_expected_next_state(initial, event1)
        event2 = build_sequence_event(
            middle, sequence_id=row["sequence_id"], step_index=2,
            done_object=row["done_object"],
            event_type=("cancel_pending_goal" if row["sequence_type"] == "replace_then_cancel" else "replace_pending_goal"),
            replacement_object=row["replacement_d"] or None,
            world_version=int(row["state_id"]) * 100 + 2,
        )
        for arm in row["arm_order"].split(";"):
            for event_index, (pre_state, event, processed) in enumerate(
                ((initial, event1, ()), (middle, event2, (event1["event_id"],))), start=1
            ):
                recovery_input = build_sequential_recovery_input(
                    sequence_id=row["sequence_id"], task_id=0,
                    state_id=int(row["state_id"]), event=event,
                    pre_state=pre_state,
                    physically_true_objects=(row["done_object"],),
                    processed_event_ids=processed, event_index=event_index,
                )
                mode = "patch" if arm in {"cope", "neutral_patch"} else "regenerate"
                audited = provider.build_audited_request(mode, recovery_input, CONTRACTS[arm])
                requests.append(
                    {
                        "sequence_id": row["sequence_id"],
                        "arm": arm,
                        "event_index": event_index,
                        "input_sha256": recovery_input.input_hash,
                        "normalized_request_sha256": stable_hash({
                            **audited["wire_payload"],
                            "messages": [
                                *audited["wire_payload"]["messages"][:2],
                                {"role": "user", "content": "<ARM_OUTPUT_CONTRACT>"},
                            ],
                        }),
                        "wire_bytes": len(canonical_json(audited["wire_payload"]).encode("utf-8")),
                    }
                )
    if len(requests) != 320:
        raise RuntimeError(f"expected 320 requests, built {len(requests)}")
    common_groups = Counter(
        (row["sequence_id"], row["event_index"], row["normalized_request_sha256"])
        for row in requests
    )
    if len(common_groups) != 80 or set(common_groups.values()) != {4}:
        raise RuntimeError("arm-normalized common requests are not exactly matched")
    with (args.output_dir / "01_REQUESTS.csv").open(
        "x", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(requests[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(requests)
    status = {
        "schema": "cope-sequential-formal-cold-preflight-v1",
        "runtime_git_commit": runtime_commit,
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "sequence_units": 40,
        "arms": 4,
        "events_per_sequence": 2,
        "planned_provider_calls": 320,
        "provider_calls_made": 0,
        "simulator_states_indexed": 0,
        "formal_states_indexed": False,
        "reserve_states_30_49_indexed": False,
        "task1_state33_retried": False,
        "task1_states34_49_indexed": False,
        "gate": "PASS",
    }
    (args.output_dir / "00_STATUS.txt").write_text(
        canonical_json(status) + "\n", encoding="utf-8"
    )
    (args.output_dir / "02_RESULT.md").write_text(
        "# Sequential formal cold preflight\n\n"
        "- Gate: **PASS**\n- Sequence units: **40**\n"
        "- Planned provider calls: **320**\n- Provider calls made: **0**\n"
        "- Simulator/formal states indexed: **0**\n",
        encoding="utf-8",
    )
    artifacts = sorted(args.output_dir.iterdir())
    (args.output_dir / "03_SHA256SUMS.txt").write_text(
        "\n".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in artifacts) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
