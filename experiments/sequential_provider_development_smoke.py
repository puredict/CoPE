#!/usr/bin/env python3
"""Development-only 32-call live provider smoke for sequential contracts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

from cope.providers.openai_compatible import OpenAICompatibleRecoveryProvider
from cope.sequential_prompting import (
    ARMS, CONTRACTS, MAX_COMPLETION_TOKENS, MAX_PROMPT_TOKENS, MODEL,
    REASONING_EFFORT, TEMPERATURE, TIMEOUT_SECONDS,
    build_sequential_recovery_input,
)
from cope.sequential_semantics import (
    build_initial_sequence_state, build_sequence_event,
    initialize_typed_sequence_state,
)
from cope.types import canonical_json, stable_hash
from experiments.sequential_formal_runner import (
    EXPECTED_CONTRACT_HASHES, FormalTransitionError, call_and_transition,
)


EXPECTED_CASES = {
    "task0_forward_replace_cancel", "task0_forward_replace_replace",
    "task0_reverse_replace_cancel", "task0_reverse_replace_replace",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--endpoint", default="https://openrouter.ai/api/v1/chat/completions")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip():
        raise RuntimeError("provider smoke requires a clean committed worktree")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    with args.case_manifest.open(newline="", encoding="utf-8") as handle:
        cases = list(csv.DictReader(handle))
    if len(cases) != 4 or {row["case_id"] for row in cases} != EXPECTED_CASES:
        raise ValueError("development smoke case manifest drift")
    if {arm: stable_hash(CONTRACTS[arm]) for arm in ARMS} != EXPECTED_CONTRACT_HASHES:
        raise RuntimeError("output contract hash drift")
    if not os.environ.get(args.api_key_env):
        args.output_dir.mkdir(parents=True, exist_ok=False)
        status = {
            "gate": "BLOCKED_CREDENTIAL_UNAVAILABLE",
            "credential_env_name": args.api_key_env,
            "credential_logged": False,
            "provider_calls": 0,
            "simulator_states_indexed": 0,
            "runtime_git_commit": commit,
        }
        (args.output_dir / "00_CREDENTIAL_PREFLIGHT.txt").write_text(
            canonical_json(status) + "\n", encoding="utf-8"
        )
        print(canonical_json(status), flush=True)
        return 3
    args.output_dir.mkdir(parents=True, exist_ok=False)
    journal = args.output_dir / "01_JOURNAL.txt"
    rows: list[dict[str, Any]] = []
    for case_index, case in enumerate(cases):
        available = tuple(
            item for item in (
                case["done_object"], case["initial_pending_object"],
                case["replacement_c"], case["replacement_d"], "butter_1",
            ) if item
        )
        initial = build_initial_sequence_state(
            sequence_id=case["case_id"], done_object=case["done_object"],
            pending_object=case["initial_pending_object"],
            available_objects=available, world_version=int(case["world_version"]),
        )
        event1 = build_sequence_event(
            initial, sequence_id=case["case_id"], step_index=1,
            done_object=case["done_object"], event_type="replace_pending_goal",
            replacement_object=case["replacement_c"],
            world_version=int(case["world_version"]) + 1,
        )
        for arm in ARMS:
            provider = OpenAICompatibleRecoveryProvider(
                {
                    "provider": "openrouter", "endpoint": args.endpoint,
                    "api_key_env": args.api_key_env, "model": MODEL,
                    "reasoning_effort": REASONING_EFFORT,
                    "temperature": TEMPERATURE, "seed": 20260804 + case_index,
                    "max_prompt_tokens": MAX_PROMPT_TOKENS,
                    "max_completion_tokens": MAX_COMPLETION_TOKENS,
                    "max_retries": 0, "timeout_seconds": TIMEOUT_SECONDS,
                }
            )
            logical = initial
            typed = (
                initialize_typed_sequence_state(
                    sequence_id=case["case_id"], done_object=case["done_object"],
                    pending_object=case["initial_pending_object"],
                ) if arm == "cope" else None
            )
            event = event1
            event1_failed = False
            for event_index in (1, 2):
                if event_index == 2 and event1_failed:
                    row = {
                        "case_id": case["case_id"], "arm": arm,
                        "event_index": 2, "provider_called": False,
                        "passed": False,
                        "failure_class": "dependency_skip_after_event1_failure",
                        "input_sha256": "", "proposal_sha256": "",
                        "prompt_tokens": 0, "completion_tokens": 0,
                        "latency_seconds": 0.0,
                    }
                    rows.append(row)
                    with journal.open("a", encoding="utf-8") as handle:
                        handle.write(canonical_json(row) + "\n")
                    continue
                recovery = build_sequential_recovery_input(
                    sequence_id=case["case_id"], task_id=0, state_id=0,
                    event=event, pre_state=logical,
                    physically_true_objects=(case["done_object"],),
                    processed_event_ids=(() if event_index == 1 else (event1["event_id"],)),
                    event_index=event_index,
                )
                try:
                    candidate, typed, _, _, diagnostics = call_and_transition(
                        provider=provider, arm=arm, recovery_input=recovery,
                        event=event, logical_state=logical, typed_state=typed,
                        physically_true=(case["done_object"],),
                    )
                    row = {
                        "case_id": case["case_id"], "arm": arm,
                        "event_index": event_index, "provider_called": True,
                        "passed": True, "failure_class": "",
                        "input_sha256": recovery.input_hash,
                        "proposal_sha256": stable_hash(diagnostics["parsed_output"]),
                        "prompt_tokens": diagnostics["prompt_tokens"],
                        "completion_tokens": diagnostics["completion_tokens"],
                        "latency_seconds": diagnostics["latency_seconds"],
                    }
                    logical = candidate
                    if event_index == 1:
                        event = build_sequence_event(
                            logical, sequence_id=case["case_id"], step_index=2,
                            done_object=case["done_object"],
                            event_type=("cancel_pending_goal" if case["sequence_type"] == "replace_then_cancel" else "replace_pending_goal"),
                            replacement_object=case["replacement_d"] or None,
                            world_version=int(case["world_version"]) + 2,
                        )
                except Exception as exc:
                    diagnostics = exc.diagnostics if isinstance(exc, FormalTransitionError) else {}
                    row = {
                        "case_id": case["case_id"], "arm": arm,
                        "event_index": event_index,
                        "provider_called": bool(diagnostics.get("provider_called", False)),
                        "passed": False,
                        "failure_class": f"{type(exc).__name__}:{exc}",
                        "input_sha256": recovery.input_hash,
                        "proposal_sha256": (
                            stable_hash(diagnostics["parsed_output"])
                            if diagnostics.get("parsed_output") is not None else ""
                        ),
                        "prompt_tokens": int(diagnostics.get("prompt_tokens", 0)),
                        "completion_tokens": int(diagnostics.get("completion_tokens", 0)),
                        "latency_seconds": float(diagnostics.get("latency_seconds", 0.0)),
                    }
                    if event_index == 1:
                        event1_failed = True
                rows.append(row)
                with journal.open("a", encoding="utf-8") as handle:
                    handle.write(canonical_json(row) + "\n")
                    handle.flush(); os.fsync(handle.fileno())
                print(canonical_json(row), flush=True)
    with (args.output_dir / "02_RESULTS.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    complete = sum(bool(row["passed"]) for row in rows)
    sequence_pass = {
        (case["case_id"], arm): all(
            bool(row["passed"]) for row in rows
            if row["case_id"] == case["case_id"] and row["arm"] == arm
        )
        for case in cases for arm in ARMS
    }
    gate = all(
        any(sequence_pass[(case["case_id"], arm)] for case in cases if case["sequence_type"] == kind)
        for arm in ARMS for kind in ("replace_then_cancel", "replace_then_replace")
    )
    (args.output_dir / "03_RESULT.md").write_text(
        "# Sequential live-provider development smoke\n\n"
        f"- Gate: **{'PASS' if gate else 'FAIL'}**\n"
        f"- Passed event cells: **{complete}/{len(rows)}**\n"
        f"- Provider calls: **{sum(bool(row['provider_called']) for row in rows)}**\n"
        "- Simulator states indexed: **0**\n",
        encoding="utf-8",
    )
    return 0 if gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
