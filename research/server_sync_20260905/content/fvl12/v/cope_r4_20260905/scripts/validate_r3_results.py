#!/usr/bin/env python3
"""Validate an r3 bundle's artifacts, pairing, budgets, and input fairness."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path


REQUIRED = {
    "result.json", "events.jsonl", "model_calls.jsonl",
    "state_snapshots.jsonl", "actions.jsonl", "raw_outputs",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--expected", type=int)
    args = parser.parse_args()
    paths = sorted(args.root.rglob("result.json"))
    problems = []
    if args.expected is not None and len(paths) != args.expected:
        problems.append(f"episode count {len(paths)} != expected {args.expected}")
    grouped = defaultdict(dict)
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "schemas_r3" / "episode.schema.json")
        .read_text(encoding="utf-8")
    )
    for path in paths:
        present = {item.name for item in path.parent.iterdir()}
        missing = REQUIRED - present
        if missing:
            problems.append(f"{path.parent}: missing {sorted(missing)}")
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            problems.append(f"{path}: unreadable result: {exc}")
            continue
        try:
            import jsonschema

            jsonschema.validate(row, schema)
        except ImportError:
            pass
        except Exception as exc:
            problems.append(f"{path}: JSON schema validation failed: {exc}")
        if row.get("schema_version") != "cope-fsrpc-r3-episode-v1":
            problems.append(f"{path}: wrong schema_version")
        calls = row.get("model_calls", [])
        budget = row.get("registered_design", {}).get("max_output_tokens")
        if any(
            call["generation"].get("completion_tokens") is not None
            and int(call["generation"]["completion_tokens"]) > int(budget)
            for call in calls
        ):
            problems.append(f"{path}: completion token budget exceeded")
        grouped[row.get("pairing_key")][row.get("method")] = row

    pairs = 0
    for key, methods in sorted(grouped.items()):
        if {"CoPE", "FSR-PC"} != set(methods):
            problems.append(f"{key}: methods are {sorted(methods)}")
            continue
        pairs += 1
        cope, fsrpc = methods["CoPE"], methods["FSR-PC"]
        fields = ("model", "profile", "seed", "backend")
        for field in fields:
            if cope.get(field) != fsrpc.get(field):
                problems.append(f"{key}: paired {field} differs")
        if cope["registered_design"] != fsrpc["registered_design"]:
            problems.append(f"{key}: registered design differs")
        cope_exo = [event["exogenous_fingerprint"] for event in cope["events"]]
        fsr_exo = [event["exogenous_fingerprint"] for event in fsrpc["events"]]
        common = min(len(cope_exo), len(fsr_exo))
        if cope_exo[:common] != fsr_exo[:common]:
            problems.append(f"{key}: exogenous inputs differ before failure")

    print(f"episodes={len(paths)} pairs={pairs} problems={len(problems)}")
    for problem in problems:
        print(f"FAIL {problem}")
    if not problems:
        print("R3 RESULT VALIDATION: PASS")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
