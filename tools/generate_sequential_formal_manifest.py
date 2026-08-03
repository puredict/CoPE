#!/usr/bin/env python3
"""Generate the deterministic 40-sequence confirmatory manifest."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope.sequential_prompting import ARMS, MAX_COMPLETION_TOKENS, MODEL, SEED_BASE, TEMPERATURE


ARM_ORDERS = tuple(
    ";".join((*ARMS[offset:], *ARMS[:offset])) for offset in range(len(ARMS))
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    rows = []
    for state_id in range(10, 30):
        forward = state_id < 20
        done = "alphabet_soup_1" if forward else "tomato_sauce_1"
        pending = "tomato_sauce_1" if forward else "alphabet_soup_1"
        orientation = "forward" if forward else "reverse"
        for kind_index, sequence_type in enumerate(
            ("replace_then_cancel", "replace_then_replace")
        ):
            sequence_index = (state_id - 10) * 2 + kind_index
            rows.append(
                {
                    "schema_version": "cope-sequential-formal-manifest-v1",
                    "sequence_id": f"formal_t00_s{state_id:02d}_{orientation}_{sequence_type}",
                    "task_suite": "libero_10",
                    "task_id": 0,
                    "state_id": state_id,
                    "prefix_orientation": orientation,
                    "sequence_type": sequence_type,
                    "done_object": done,
                    "initial_pending_object": pending,
                    "replacement_c": "cream_cheese_1",
                    "replacement_d": "" if sequence_type == "replace_then_cancel" else "butter_1",
                    "arm_order": ARM_ORDERS[sequence_index % len(ARM_ORDERS)],
                    "provider_calls_per_arm": 2,
                    "model": MODEL,
                    "temperature": f"{TEMPERATURE:.1f}",
                    "seed": SEED_BASE + sequence_index,
                    "max_completion_tokens": MAX_COMPLETION_TOKENS,
                    "retry_budget": 0,
                    "repair_budget": 0,
                    "controller_config_sha256": "56171aef20a9f60e335259ff10abe7c211f6594a98b52b09864effcc7b1d988a",
                }
            )
    if len(rows) != 40:
        raise RuntimeError("formal manifest must contain 40 sequences")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
