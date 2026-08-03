#!/usr/bin/env python3
"""Materialize the immutable completed formal segment without new calls."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from cope.semantic_live_runner import LIVE_ARMS
from cope.types import canonical_json


SOURCE_SHA256 = "36f6450761bb01442660f59f8bfaf5977cc961cdb19bb263bcdf53c4170f96eb"
SOURCE_RUNTIME_COMMIT = "3d396fdbdd045602357e4dc5530c732c83b67ed0"
STATE_IDS = frozenset(range(27, 33))


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise RuntimeError("refusing to write empty retained evidence")
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def truth(value: Any) -> bool:
    return value is True or str(value).strip().lower() == "true"


def exact_mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1)) / (2**n)
    return min(1.0, 2.0 * tail)


def main() -> int:
    args = arguments()
    if os.environ.get("OPENROUTER_API_KEY"):
        raise RuntimeError("retained materialization forbids provider credentials")
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = args.output_dir.resolve()
    if (repo_root / "research").resolve() not in output_dir.parents:
        raise RuntimeError("output must be under research/")
    if output_dir.exists():
        raise FileExistsError(output_dir)
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise RuntimeError("materialization requires a clean committed worktree")
    runtime_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if sha256(args.journal) != SOURCE_SHA256:
        raise RuntimeError("source journal hash mismatch")
    records = [json.loads(line) for line in args.journal.read_text().splitlines()]
    semantic_records = [row for row in records if row.get("record_type") == "semantic"]
    embodied_records = [row for row in records if row.get("record_type") == "embodied"]
    semantic_rows = [dict(row) for record in semantic_records for row in record["rows"]]
    embodied_rows = [dict(record["row"]) for record in embodied_records]
    if len(records) != 60 or len(semantic_rows) != 48 or len(embodied_rows) != 48:
        raise RuntimeError("source journal shape mismatch")
    if {int(row["state_id"]) for row in semantic_rows + embodied_rows} != STATE_IDS:
        raise RuntimeError("source state set mismatch")
    case_ids = {row["case_id"] for row in semantic_rows}
    if len(case_ids) != 12:
        raise RuntimeError("source case count mismatch")
    for case_id in case_ids:
        srows = [row for row in semantic_rows if row["case_id"] == case_id]
        erows = [row for row in embodied_rows if row["case_id"] == case_id]
        if {row["arm"] for row in srows} != set(LIVE_ARMS) or {
            row["arm"] for row in erows
        } != set(LIVE_ARMS):
            raise RuntimeError("source arm assignment mismatch")
    if any(
        row["provider_status"] != "ok"
        or int(row["retry_count"]) != 0
        or row["runtime_git_commit"] != SOURCE_RUNTIME_COMMIT
        for row in semantic_rows
    ):
        raise RuntimeError("source provider or provenance mismatch")

    outcomes = []
    for row in embodied_rows:
        outcomes.append(
            {
                "case_id": row["case_id"],
                "state_id": row["state_id"],
                "event_type": row["event_type"],
                "arm": row["arm"],
                "endpoint_success": truth(row["semantic_correct"])
                and truth(row["execution_attempted"])
                and truth(row["matched_prefix_pass"])
                and truth(row["terminal_goal_success"]),
                "semantic_correct": row["semantic_correct"],
                "execution_attempted": row["execution_attempted"],
                "terminal_goal_success": row["terminal_goal_success"],
                "post_event_action_count": row["post_event_action_count"],
                "post_event_action_sha256": row["post_event_action_sha256"],
            }
        )

    comparisons = []
    by_case_arm = {
        (row["case_id"], row["arm"]): truth(row["endpoint_success"])
        for row in outcomes
    }
    for control in ("fsr_pc", "compact_tx", "neutral_patch"):
        b = sum(by_case_arm[(case, "cope")] and not by_case_arm[(case, control)] for case in case_ids)
        c = sum(not by_case_arm[(case, "cope")] and by_case_arm[(case, control)] for case in case_ids)
        comparisons.append(
            {
                "comparison": f"cope_vs_{control}",
                "cases": len(case_ids),
                "cope_only_success": b,
                "control_only_success": c,
                "exact_mcnemar_p": f"{exact_mcnemar(b, c):.12g}",
                "confirmatory_valid": False,
                "qualification": "descriptive_interrupted_segment",
            }
        )

    output_dir.mkdir(parents=True, exist_ok=False)
    write_csv(output_dir / "01_RETAINED_SEMANTIC_ROWS.csv", semantic_rows)
    write_csv(output_dir / "02_RETAINED_EMBODIED_ROWS.csv", embodied_rows)
    write_csv(output_dir / "03_RETAINED_ENDPOINTS.csv", outcomes)
    write_csv(output_dir / "04_DESCRIPTIVE_COMPARISONS.csv", comparisons)
    summary = {
        "source_journal_sha256": SOURCE_SHA256,
        "source_runtime_commit": SOURCE_RUNTIME_COMMIT,
        "materializer_runtime_commit": runtime_commit,
        "provider_calls_during_materialization": 0,
        "simulator_calls_during_materialization": 0,
        "states": sorted(STATE_IDS),
        "cases": len(case_ids),
        "semantic_rows": len(semantic_rows),
        "embodied_rows": len(embodied_rows),
        "endpoint_success_by_arm": {
            arm: sum(
                truth(row["endpoint_success"]) for row in outcomes if row["arm"] == arm
            )
            for arm in LIVE_ARMS
        },
        "confirmatory_valid": False,
        "qualification": "formal_run_interrupted_at_common_prefix_state33",
        "credential_logged": False,
    }
    (output_dir / "05_STATUS.txt").write_text(canonical_json(summary) + "\n")
    print(canonical_json(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
