#!/usr/bin/env python3
"""Inspect pre-audited clean-policy evidence; never execute a model or simulator.

The input must be an audited export of referenced terminal artifacts, with their
actual byte SHA256s and policy provenance. Schema/grid validation cannot prove
physical measurement authenticity. The report records validation only, and
never authorizes an experiment without the separate task-catalog gates.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope_benchmark.repeated_v2.task_calibration import (  # noqa: E402
    CalibrationBlockedError, calibration_grid, summarize_calibration,
)
from cope_benchmark.repeated_v2.task_catalog import DEFAULT_CATALOG_PATH, load_task_catalog  # noqa: E402
from cope_benchmark.repeated_v2.config import load_config  # noqa: E402
from cope_benchmark.repeated_v2.canonical import canonical_sha256, strict_loads  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/repeated_interruptions_v2_formal.yaml")
    parser.add_argument("--evidence", type=Path, help="Existing JSON list of measured v2 calibration records")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--output", type=Path, help="New report path; existing paths are never overwritten")
    parser.add_argument("--output-dir", type=Path, help="New report directory; writes calibration_report.json and, only if validated, calibration_records.json")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.output and args.output_dir:
        parser.error("choose --output or --output-dir")
    catalog = load_task_catalog(args.catalog)
    records = strict_loads(args.evidence.read_text(encoding="utf-8")) if args.evidence and args.evidence.is_file() else []
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        raise CalibrationBlockedError(("evidence must be a list of complete calibration records",))
    if any(type(record.get("task_id")) is not int or record["task_id"] not in range(10) for record in records):
        raise CalibrationBlockedError(("evidence contains an unknown task ID",))
    summaries, blockers = [], []
    for task in catalog.tasks:
        try:
            summaries.append(summarize_calibration(
                task.task_id, [record for record in records if record["task_id"] == task.task_id],
                initial_state_digests=task.initial_state_digests,
            ).to_dict())
        except CalibrationBlockedError as exc:
            blockers.extend(f"task {task.task_id}: {reason}" for reason in exc.reasons)
    if len({(summary["policy_id"], summary["checkpoint_sha256"], summary["protocol_sha256"]) for summary in summaries}) > 1:
        blockers.append("all tasks must share one calibration policy/checkpoint/protocol")
    report = {"schema_version": "repeated_v2_offline_calibration_report_v1",
              "status": "BLOCKED_CALIBRATION_EVIDENCE" if blockers else "CALIBRATION_EVIDENCE_VALIDATED",
              "provider_calls": 0, "vla_calls": 0, "expected_cells": len(calibration_grid()),
              "config_sha256": canonical_sha256(config),
              "evidence_records_filename": "calibration_records.json",
              "summaries": summaries, "blockers": sorted(blockers)}
    content = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    destination = args.output or (args.output_dir / "calibration_report.json" if args.output_dir else None)
    if destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if args.output_dir and not blockers and (args.output_dir / "calibration_records.json").exists():
            raise FileExistsError("refusing to overwrite calibration_records.json")
        with destination.open("x", encoding="utf-8") as output:
            output.write(content)
        if args.output_dir and not blockers:
            with (args.output_dir / "calibration_records.json").open("x", encoding="utf-8") as output:
                output.write(json.dumps(records, sort_keys=True, indent=2) + "\n")
    print(content, end="")
    return 2 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
