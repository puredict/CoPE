from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def summarize_run(label: str, run_dir: Path) -> list[dict]:
    summary_path = run_dir / "summary.json"
    if not summary_path.exists() and (run_dir / "episode_summary.json").exists():
        summary_path = run_dir / "episode_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        reasons = formal_skip_reasons(summary)
        if reasons:
            warn_skipped(label, run_dir, summary_path.name, 1, reasons)
            return [
                {
                    "label": label,
                    "run_dir": str(run_dir),
                    "condition": "diagnostic_skipped",
                    "n": 0,
                    "successes": 0,
                    "success_rate": "",
                    "disturbance_applied": 0,
                }
            ]
    rows = read_rows(run_dir / "episodes.jsonl")
    filtered_rows = []
    skipped: dict[tuple[str, ...], int] = {}
    for row in rows:
        reasons = formal_skip_reasons(row)
        if reasons:
            skipped[tuple(reasons)] = skipped.get(tuple(reasons), 0) + 1
        else:
            filtered_rows.append(row)
    for reasons, count in sorted(skipped.items()):
        warn_skipped(label, run_dir, "episodes.jsonl", count, list(reasons))
    rows = filtered_rows
    out = []
    for condition in ("clean", "disturbed"):
        xs = [r for r in rows if r.get("condition") == condition]
        successes = sum(bool(r.get("success_within_original_budget", r.get("success"))) for r in xs)
        disturbed_applied = sum(1 for r in xs if r.get("disturbance") is not None)
        out.append(
            {
                "label": label,
                "run_dir": str(run_dir),
                "condition": condition,
                "n": len(xs),
                "successes": successes,
                "success_rate": successes / len(xs) if xs else "",
                "disturbance_applied": disturbed_applied,
            }
        )
    return out


def should_skip_formal(row: dict) -> bool:
    return bool(formal_skip_reasons(row))


def formal_skip_reasons(row: dict) -> list[str]:
    reasons = []
    if row.get("not_empirical_model_measurement"):
        reasons.append("not_empirical_model_measurement")
    if row.get("exclude_from_formal_success_summaries"):
        reasons.append("exclude_from_formal_success_summaries")
    if row.get("interactive"):
        reasons.append("interactive")
    if row.get("manual_intervention"):
        reasons.append("manual_intervention")
    if row.get("human_intervention"):
        reasons.append("human_intervention")
    if row.get("formal_run") is False:
        reasons.append("formal_run=false")
    if row.get("eligible_for_official_metrics") is False:
        reasons.append("eligible_for_official_metrics=false")
    return reasons


def warn_skipped(label: str, run_dir: Path, source: str, count: int, reasons: list[str]) -> None:
    reason_text = ", ".join(reasons)
    print(
        f"WARNING: excluding {count} interactive/non-formal record(s) from formal summary "
        f"for {label} at {run_dir} ({source}; reasons: {reason_text})",
        file=sys.stderr,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+", help="label=path entries")
    parser.add_argument("--csv", default="summary_table.csv")
    parser.add_argument("--json", default="summary_table.json")
    args = parser.parse_args()

    summary = []
    for item in args.runs:
        label, path = item.split("=", 1)
        summary.extend(summarize_run(label, Path(path)))

    csv_path = Path(args.csv)
    json_path = Path(args.json)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "label",
                "condition",
                "n",
                "successes",
                "success_rate",
                "disturbance_applied",
                "run_dir",
            ],
        )
        writer.writeheader()
        writer.writerows(summary)
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
