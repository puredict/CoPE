#!/usr/bin/env python3
"""Validate an explicit semantic catalog and attach existing measured calibration.

No task semantics, feasibility passes, or policy outcomes are synthesized. The
default source is the source-backed but blocked inventory checked into v2.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope_benchmark.repeated_v2.canonical import canonical_sha256, strict_loads  # noqa: E402
from cope_benchmark.repeated_v2.config import load_config  # noqa: E402
from cope_benchmark.repeated_v2.task_catalog import (  # noqa: E402
    CatalogBlockedError, DEFAULT_CATALOG_PATH, TaskCatalog, load_task_catalog, select_eligible_tasks,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/repeated_interruptions_v2_formal.yaml")
    parser.add_argument("--source-catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--calibration-evidence", type=Path)
    parser.add_argument("--calibration-dir", type=Path, help="Reads calibration_records.json if present; no measurement calls")
    parser.add_argument("--output", type=Path, help="New candidate-catalog path, never overwritten")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.calibration_evidence and args.calibration_dir:
        parser.error("choose --calibration-evidence or --calibration-dir")
    candidate = load_task_catalog(args.source_catalog).to_dict()
    evidence_path = args.calibration_evidence or (args.calibration_dir / "calibration_records.json" if args.calibration_dir else None)
    if evidence_path and evidence_path.is_file():
        records = strict_loads(evidence_path.read_text(encoding="utf-8"))
        if not isinstance(records, list) or any(not isinstance(record, dict) or type(record.get("task_id")) is not int
                                                 or record["task_id"] not in range(10) for record in records):
            raise CatalogBlockedError(("calibration evidence must enumerate explicit known task IDs",))
        for task in candidate["tasks"]:
            task["calibration_records"] = [record for record in records if record["task_id"] == task["task_id"]]
            # Only the independently validated evidence can discharge this gap.
            if task["calibration_records"]:
                task["unresolved_fields"] = [name for name in task["unresolved_fields"] if name != "calibration_records"]
    catalog = TaskCatalog.from_dict(candidate)
    selected, blockers, status = (), (), "CATALOG_VALIDATED"
    try:
        selected = select_eligible_tasks(catalog)
    except CatalogBlockedError as exc:
        status, blockers = exc.status, exc.reasons
    if evidence_path and not evidence_path.is_file():
        blockers = tuple(sorted((*blockers, "BLOCKED_CALIBRATION_EVIDENCE: calibration_records.json is unavailable")))
        if status == "CATALOG_VALIDATED":
            status = "BLOCKED_CALIBRATION_EVIDENCE"
    report = {"status": status, "catalog_sha256": canonical_sha256(catalog.to_dict()),
              "config_sha256": canonical_sha256(config), "enumerated_tasks": len(catalog.tasks),
              "selected_task_ids": [task.task_id for task in selected] if not blockers else [],
              "provider_calls": 0, "vla_calls": 0, "blockers": list(blockers)}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        status_path = args.output.with_name(args.output.name + ".status.json")
        if args.output.exists() or status_path.exists():
            raise FileExistsError("refusing to overwrite a candidate catalog or status report")
        with args.output.open("x", encoding="utf-8") as output:
            output.write(json.dumps(catalog.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        with status_path.open("x", encoding="utf-8") as output:
            output.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
