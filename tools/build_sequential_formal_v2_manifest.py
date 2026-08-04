#!/usr/bin/env python3
"""Build the five-arm v2 manifest from the immutable v1 sequence assignment."""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

from cope.governance_collision_prompting import GOVERNED_DELTA_CONTRACT
from cope.types import stable_hash


SOURCE_SHA256 = "1fe0b231bb17e9ed0711c76ee440928faccf84696043ac0a84ddd9645bf6b7ec"
ARMS = ("cope", "neutral_patch", "governed_delta", "fsr_pc", "full_replan")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def build(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if len(rows) != 40 or len({row["sequence_id"] for row in rows}) != 40:
        raise RuntimeError("v1 source must contain 40 unique sequences")
    output = []
    contract_hash = stable_hash(GOVERNED_DELTA_CONTRACT)
    for index, row in enumerate(rows):
        rotation = index % len(ARMS)
        order = ARMS[rotation:] + ARMS[:rotation]
        updated = dict(row)
        updated["schema_version"] = "cope-sequential-formal-manifest-v2"
        updated["arm_order"] = ";".join(order)
        updated["governed_contract_sha256"] = contract_hash
        output.append(updated)
    return output


def main() -> int:
    args = parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if hashlib.sha256(args.source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise RuntimeError("v1 source manifest hash mismatch")
    with args.source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    output = build(rows)
    fieldnames = list(output[0])
    with args.output.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader(); writer.writerows(output)
    print(hashlib.sha256(args.output.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

