#!/usr/bin/env python3
"""Build the held-out 40-case occurrence confirmation manifest."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from cope.occurrence_prompting import ARMS
from cope.occurrence_prompting_confirmatory_v3 import EXPECTED_CONTRACT_HASHES_V3
from cope.sequential_prompting import MAX_COMPLETION_TOKENS, MODEL, TEMPERATURE
from cope.types import stable_hash


OBJECTS = (
    "apple_1", "banana_1", "bread_1", "coffee_jar_1", "lemon_1",
    "mug_1", "sugar_box_1",
)


def triples() -> list[tuple[str, str, str]]:
    rows = []
    for index in range(10):
        done = OBJECTS[index % len(OBJECTS)]
        recurring = OBJECTS[(index + 1) % len(OBJECTS)]
        intermediate = OBJECTS[(index + 2 + index // len(OBJECTS)) % len(OBJECTS)]
        if len({done, recurring, intermediate}) != 3:
            raise RuntimeError("v3 triple generator produced duplicate objects")
        rows.append((done, recurring, intermediate))
    if len(set(rows)) != 10:
        raise RuntimeError("v3 triple generator is not unique")
    return rows


def build() -> list[dict[str, object]]:
    rows = []
    index = 0
    family_hash = stable_hash(EXPECTED_CONTRACT_HASHES_V3)
    for triple_index, (done, recurring, intermediate) in enumerate(triples()):
        for depth in range(1, 5):
            rotation = index % len(ARMS)
            order = ARMS[rotation:] + ARMS[:rotation]
            rows.append({
                "schema_version": "occurrence-confirmatory-manifest-v3",
                "case_id": f"occurrence-v3-h{triple_index:02d}-d{depth}",
                "triple_index": triple_index,
                "recurrence_depth": depth,
                "done_object": done,
                "recurring_object": recurring,
                "intermediate_object": intermediate,
                "arm_order": ";".join(order),
                "provider_calls_per_arm": 1,
                "model": MODEL,
                "temperature": TEMPERATURE,
                "seed": 20260910 + index,
                "max_completion_tokens": MAX_COMPLETION_TOKENS,
                "retry_budget": 0,
                "contract_family_sha256": family_hash,
            })
            index += 1
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    rows = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
