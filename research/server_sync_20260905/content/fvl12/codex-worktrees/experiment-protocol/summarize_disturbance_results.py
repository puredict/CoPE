from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def summarize_run(label: str, run_dir: Path) -> list[dict]:
    rows = read_rows(run_dir / "episodes.jsonl")
    out = []
    for condition in ("clean", "disturbed"):
        xs = [r for r in rows if r.get("condition") == condition]
        successes = sum(bool(r.get("success")) for r in xs)
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
