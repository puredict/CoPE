#!/usr/bin/env python3
"""Build the frozen 40-case occurrence-sensitive formal manifest."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope.occurrence_prompting import ARMS, CONTRACTS
from cope.sequential_prompting import MAX_COMPLETION_TOKENS, MODEL, TEMPERATURE
from cope.types import stable_hash


OBJECTS = (
    "alphabet_soup_1", "butter_1", "cream_cheese_1", "ketchup_1",
    "milk_1", "orange_juice_1", "tomato_sauce_1",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def triples() -> list[tuple[str, str, str]]:
    rows = []
    for index in range(10):
        done = OBJECTS[index % len(OBJECTS)]
        recurring = OBJECTS[(index + 1) % len(OBJECTS)]
        intermediate = OBJECTS[(index + 2 + index // len(OBJECTS)) % len(OBJECTS)]
        if len({done, recurring, intermediate}) != 3:
            raise RuntimeError("triple generator produced duplicate objects")
        rows.append((done, recurring, intermediate))
    if len(set(rows)) != 10:
        raise RuntimeError("triple generator is not unique")
    return rows


def build() -> list[dict[str, object]]:
    rows = []
    index = 0
    hashes = {arm: stable_hash(CONTRACTS[arm]) for arm in ARMS}
    for triple_index, (done, recurring, intermediate) in enumerate(triples()):
        for depth in range(1, 5):
            rotation = index % len(ARMS)
            order = ARMS[rotation:] + ARMS[:rotation]
            rows.append({
                "schema_version": "occurrence-learned-formal-manifest-v1",
                "case_id": f"occurrence-t{triple_index:02d}-d{depth}",
                "triple_index": triple_index, "recurrence_depth": depth,
                "done_object": done, "recurring_object": recurring,
                "intermediate_object": intermediate,
                "arm_order": ";".join(order), "provider_calls_per_arm": 1,
                "model": MODEL, "temperature": TEMPERATURE,
                "seed": 20260850 + index,
                "max_completion_tokens": MAX_COMPLETION_TOKENS,
                "retry_budget": 0, "contract_family_sha256": stable_hash(hashes),
            })
            index += 1
    return rows


def main() -> int:
    args = parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    rows = build()
    with args.output.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
