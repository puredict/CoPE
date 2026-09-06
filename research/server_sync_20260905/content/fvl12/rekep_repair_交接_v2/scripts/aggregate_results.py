"""Aggregate episode traces into a compact summary. CPU-safe, no GPU imports."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="runs", help="directory containing traces")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    root = Path(a.root)
    if not root.exists():
        print(f"no such directory: {root}", file=sys.stderr); sys.exit(1)
    traces = sorted(root.rglob("trace.json"))
    print(f"found {len(traces)} trace(s) under {root}")
    rows = []
    for t in traces:
        try: d = json.loads(t.read_text())
        except Exception as e: print(f"  skip {t}: {e}"); continue
        rows.append({
            "path": str(t.relative_to(root)),
            "task": d.get("task"), "mode": d.get("mode"), "seed": d.get("seed"),
            "dry_run": d.get("dry_run"), "steps": len(d.get("steps", [])),
            "n_repairs": len(d.get("repair_traces", [])),
            "program_len": len(d.get("program", [])),
            "wall_seconds": d.get("wall_seconds"),
        })
    for r in rows:
        print(f"  {r['mode'] or '?':8} seed={r['seed']} steps={r['steps']:4} "
              f"repairs={r['n_repairs']} program={r['program_len']}")
    if a.out:
        Path(a.out).write_text(json.dumps(rows, indent=2))
        print(f"wrote {a.out}")

if __name__ == "__main__":
    main()
