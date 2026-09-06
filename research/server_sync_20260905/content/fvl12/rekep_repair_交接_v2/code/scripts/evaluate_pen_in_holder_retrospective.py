"""Retrospectively apply the P0-1 success evaluator to the v1 GPU episodes.

STATUS: locally executed (CPU). Reads `rekep_gpu_execution/` READ-ONLY.

The honest outcome is expected to be mostly UNAVAILABLE: the v1 result JSONs
record only `pen_position`, `pen_orientation`, `holder_position`,
`holder_orientation`. They do NOT record holder bore geometry, pen dimensions,
velocities, or any state history. Insertion depth, containment, tilt-vs-holder-
axis and stability therefore cannot be computed, and are reported UNAVAILABLE
rather than guessed from pixels.

What IS derivable is reported: the radial distance of the pen centre from the
holder axis, and the pen's tilt from world vertical.

Usage:
  python scripts/evaluate_pen_in_holder_retrospective.py \
      --root rekep_gpu_execution --out /tmp/retro.csv
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from rekep_repair.gpu_metrics.geometry import (
    angle_between_deg, body_axis, radial_distance_to_axis,
)

REQUIRED_FOR_FULL_EVAL = [
    "holder_inner_radius", "holder_rim_height", "holder_bore_depth",
    "pen_length", "pen_radius", "pen_linear_velocity", "pen_angular_velocity",
    "state_history",
]


def episodes(root: str):
    out = []
    for p in sorted(glob.glob(os.path.join(
            root, "eight_gpu/eight_gpu_initial8b_*/gpu_*/seed_*/repaired_result.json"))):
        out.append(("online_repair", "initial8b", p))
    for p in sorted(glob.glob(os.path.join(
            root, "eight_gpu/retry_seed7_*/gpu_*/seed_*/repaired_result.json"))):
        out.append(("online_repair", "retry", p))
    for p in sorted(glob.glob(os.path.join(root, "single_gpu/wrapped_parity/*.json"))):
        out.append(("wrapped_nominal", "single_gpu", p))
    for p in sorted(glob.glob(os.path.join(root, "single_gpu/online_repair/*.json"))):
        out.append(("online_repair", "single_gpu", p))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="rekep_gpu_execution")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    rows = []
    for method, batch, path in episodes(args.root):
        d = json.load(open(path))
        rec = {
            "file": os.path.relpath(path, args.root),
            "method": method, "batch": batch, "seed": d.get("seed", ""),
            "runner_completed": d.get("completed"),
        }
        pen, hol = d.get("pen_position"), d.get("holder_position")
        pq, hq = d.get("pen_orientation"), d.get("holder_orientation")
        if not (pen and hol and pq and hq):
            rec.update(task_success="UNAVAILABLE",
                       reason="no pen/holder pose recorded")
            rows.append(rec); continue

        h_axis = body_axis(hq, 2)
        rec["xy_error_centre_m"] = round(
            radial_distance_to_axis(np.asarray(pen, float),
                                    np.asarray(hol, float), h_axis), 5)
        rec["pen_tilt_vs_holder_axis_deg"] = round(
            angle_between_deg(body_axis(pq, 2), h_axis), 2)
        rec["pen_minus_holder_z_m"] = round(float(pen[2] - hol[2]), 5)

        # everything that needs geometry/history we do NOT have:
        for k in ("inside_holder", "insertion_depth", "tilt_error_deg",
                  "stable_steps", "task_success"):
            rec[k] = "UNAVAILABLE"
        rec["attachment_state"] = "UNAVAILABLE"
        rec["missing_state"] = ";".join(REQUIRED_FOR_FULL_EVAL)
        rec["reason"] = ("v1 JSON lacks holder bore geometry, pen dimensions, "
                         "velocities and state history; success NOT inferable")
        rows.append(rec)

    cols = ["file", "method", "batch", "seed", "runner_completed",
            "xy_error_centre_m", "pen_tilt_vs_holder_axis_deg",
            "pen_minus_holder_z_m", "inside_holder", "insertion_depth",
            "tilt_error_deg", "stable_steps", "attachment_state",
            "task_success", "missing_state", "reason"]
    print(f"{'file':52} {'method':16} {'xy(m)':>8} {'tilt°':>7} {'dz(m)':>8} {'success':>12}")
    print("-" * 112)
    for r in rows:
        print(f"{r['file'][-52:]:52} {r['method']:16} "
              f"{str(r.get('xy_error_centre_m','')):>8} "
              f"{str(r.get('pen_tilt_vs_holder_axis_deg','')):>7} "
              f"{str(r.get('pen_minus_holder_z_m','')):>8} "
              f"{str(r.get('task_success')):>12}")
    n_unavail = sum(1 for r in rows if r.get("task_success") == "UNAVAILABLE")
    print(f"\n{len(rows)} episodes; task_success UNAVAILABLE for {n_unavail} "
          f"({n_unavail/max(1,len(rows)):.0%}).")
    print("This is the correct outcome: v1 did not record the state the metric needs.")
    print("Only prospective (v2) episodes can be scored.")

    if args.out:
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader(); w.writerows(rows)
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
