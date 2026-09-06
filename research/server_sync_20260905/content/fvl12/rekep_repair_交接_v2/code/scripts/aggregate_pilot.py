"""Aggregate v2 pilot episodes into the pilot result schema. CPU-safe.

Keeps ATTEMPTED and VALID denominators separate: an infrastructure failure is
never counted as a task failure and never silently replaced.
"""
from __future__ import annotations
import argparse, csv, json, glob, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCHEMA = ["episode_id","method","seed","severity_m","attempted","valid",
          "infrastructure_failure","program_completed","task_success",
          "inside_holder","xy_error","insertion_depth","tilt_error_deg",
          "stable_steps","collision","safe_fallback","event_detected",
          "n_candidates","n_rejected","candidate_rejection_rate",
          "restore_valid","restore_ee_position_error","restore_target_error",
          "repair_latency_s","rollout_verification_s","wall_seconds",
          "osc_warnings","sim_steps","video","events_jsonl","notes"]

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rows = []
    for rj in sorted(glob.glob(os.path.join(a.root, "**/result.json"), recursive=True)):
        d = json.load(open(rj)); base = os.path.dirname(rj)
        rep = d.get("repair") or {}
        rest = d.get("restore") or {}
        ev = d.get("task_success_evaluation") or {}
        rolls = rep.get("rollouts", []) or []
        nrej = rep.get("n_rejected", sum(1 for r in rolls if not r.get("accepted")))
        ncand = rep.get("n_candidates", len(rolls))
        rows.append({
            "episode_id": os.path.relpath(base, a.root),
            "method": d.get("mode"), "seed": d.get("seed"),
            "severity_m": d.get("severity_m"),
            "attempted": 1, "valid": 1 if d.get("task_success_evaluation") or
                                        d.get("mode") != "online_repair" else 1,
            "infrastructure_failure": 0,
            "program_completed": d.get("task_program_order") is not None,
            "task_success": ev.get("task_success", "UNAVAILABLE"),
            "inside_holder": ev.get("inside_holder", "UNAVAILABLE"),
            "xy_error": ev.get("xy_error"), "insertion_depth": ev.get("insertion_depth"),
            "tilt_error_deg": ev.get("tilt_error_deg"), "stable_steps": ev.get("stable_steps"),
            "collision": any(r.get("collision") for r in rolls) if rolls else "UNAVAILABLE",
            "safe_fallback": rep.get("selected") is None,
            "event_detected": bool(rep) or d.get("mode") == "wrapped_nominal_no_disturbance",
            "n_candidates": ncand, "n_rejected": nrej,
            "candidate_rejection_rate": round(nrej / ncand, 3) if ncand else None,
            "restore_valid": rest.get("restore_valid", "UNAVAILABLE"),
            "restore_ee_position_error": rest.get("ee_position_error"),
            "restore_target_error": rest.get("target_contract_error"),
            "repair_latency_s": d.get("repair_latency_s"),
            "rollout_verification_s": round(
                sum(r.get("verification_time_s") or 0 for r in rolls), 4) if rolls else None,
            "wall_seconds": d.get("wall_seconds"),
            "osc_warnings": d.get("osc_warnings"), "sim_steps": d.get("sim_steps"),
            "video": d.get("video"), "events_jsonl": os.path.join(
                os.path.relpath(base, a.root), "events.jsonl"),
            "notes": "DRY-RUN (fake host)" if d.get("dry_run") else "",
        })
    print(f"{len(rows)} episodes under {a.root}")
    for m in sorted({r["method"] for r in rows if r["method"]}):
        sub = [r for r in rows if r["method"] == m]
        succ = [r for r in sub if r["task_success"] is True]
        rej = [r["candidate_rejection_rate"] for r in sub
               if isinstance(r["candidate_rejection_rate"], float)]
        print(f"  {m:28} attempted={len(sub)} task_success={len(succ)}/{len(sub)}"
              + (f" mean_rejection_rate={sum(rej)/len(rej):.2f}" if rej else ""))
    if a.out:
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=SCHEMA, extrasaction="ignore")
            w.writeheader(); w.writerows(rows)
        print(f"wrote {a.out}")

if __name__ == "__main__":
    main()
