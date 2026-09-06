#!/usr/bin/env python3
"""End-to-end pipeline trace --- the gate before any GPU experiment.

Prints, for one paired (condition, seed), the full sequence actually executed by
both arms and checks it against the required marker list:

    EVENT
    PATCH | REGENERATION
    CONTINUATION_CAPTURED
    REPAIR_GOAL_COMPILED
    CANDIDATES_GENERATED
    ROLLOUT_RESULTS
    CANDIDATE_SELECTED
    GRAPH_SPLICED
    RESTORE_VALIDATED
    STAGE_RESUMED

Exit status is non-zero if any interruption fails to produce the complete
pipeline, so this can gate a run rather than merely describe one.

    python3 scripts/cope_pipeline_trace.py --condition I4 --seed 0
    python3 scripts/cope_pipeline_trace.py --all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "code", ROOT):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from cope.benchmark import BasketTaskSpec  # noqa: E402
from cope.benchmark.physical_episode import run_physical_episode  # noqa: E402
from cope.repair_bridge import assert_complete  # noqa: E402

CONDITIONS = ("I1", "I2", "I3", "I4")
ARMS = ("CoPE", "FSR-PC")


def trace_one(condition: str, seed: int, out) -> bool:
    print(f"\n{'=' * 78}\n  condition={condition}  seed={seed}\n{'=' * 78}",
          file=out)
    results = {m: run_physical_episode(BasketTaskSpec(seed=seed,
                                                      condition=condition,
                                                      method=m))
               for m in ARMS}
    all_ok = True

    for m, r in results.items():
        print(f"\n-- {m} --", file=out)
        if not r.pipeline_markers:
            print("   NO REPAIR PIPELINE RAN", file=out)
            all_ok = False
            continue
        for i, (markers, o) in enumerate(zip(r.pipeline_markers,
                                             r.repair_outcomes), 1):
            ok, problems = assert_complete(markers)
            all_ok = all_ok and ok
            print(f"   interruption {i}  [{o['event_id']}]  "
                  f"{'COMPLETE' if ok else 'INCOMPLETE: ' + str(problems)}",
                  file=out)
            req = o["requirements"] or {}
            for mk in markers:
                detail = ""
                if mk == "REPAIR_GOAL_COMPILED":
                    detail = (f"required_true={req.get('required_true')} "
                              f"required_false={req.get('required_false')}")
                elif mk == "CANDIDATES_GENERATED":
                    detail = (f"n={o['n_candidates']} "
                              f"planner_nodes={o['planner_expanded']} "
                              f"{o['candidate_names']}")
                elif mk == "ROLLOUT_RESULTS":
                    detail = f"{len(o['rollouts'])} verified"
                elif mk == "CANDIDATE_SELECTED":
                    detail = (f"{o['selected']} score={o['selected_score']:.3f} "
                              f"rejected={o['n_rejected']}")
                elif mk == "GRAPH_SPLICED":
                    detail = (f"{o['spliced_stage_ids']}  "
                              f"stages {o['program_size_before']} -> "
                              f"{o['program_size_after']}")
                elif mk == "RESTORE_VALIDATED":
                    detail = (f"validated={o['restore_validated']} "
                              f"handoff_error={o['restore_handoff_error']}")
                elif mk == "CONTINUATION_CAPTURED":
                    detail = "captured before physical adaptation"
                print(f"        {mk:24s} {detail}", file=out)
            for name, report in o["rollouts"]:
                print(f"          rollout  {name}: {report}", file=out)
            for name, reason in o["rejections"]:
                print(f"          REJECTED {name}: {reason}", file=out)
            print("        why (requirement -> source):", file=out)
            for s in req.get("sources", []):
                print(f"          {s['requirement']:28s} <- {s['slot_id']} "
                      f"[{s['transition']}]", file=out)

    a, b = results["CoPE"], results["FSR-PC"]
    same_inputs = (a.adaptation_input_fingerprints ==
                   b.adaptation_input_fingerprints)
    same_reqs = a.requirement_fingerprints == b.requirement_fingerprints
    print(f"\n-- shared-stack checks --", file=out)
    print(f"   identical adaptation inputs      : {same_inputs}", file=out)
    print(f"   identical compiled repair goals  : {same_reqs}", file=out)
    print(f"   same candidates generated        : "
          f"{a.metrics.candidates_generated == b.metrics.candidates_generated}",
          file=out)
    print(f"   same splices / resumes           : "
          f"{a.metrics.splices == b.metrics.splices and a.metrics.stages_resumed == b.metrics.stages_resumed}",
          file=out)
    print(f"   differ only in state semantics   : "
          f"regenerated {a.metrics.slots_regenerated} vs "
          f"{b.metrics.slots_regenerated}; identity preserved "
          f"{a.metrics.identity_preserved} vs {b.metrics.identity_preserved}",
          file=out)
    return all_ok and same_inputs and same_reqs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--condition", default="I4", choices=list(CONDITIONS))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--all", action="store_true",
                    help="trace every interruption condition")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    streams = [sys.stdout]
    fh = None
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        fh = open(args.out, "w")
        streams.append(fh)

    conds = CONDITIONS if args.all else (args.condition,)
    ok = True
    for out in streams:
        print("CoPE / FSR-PC end-to-end repair pipeline trace", file=out)
        print("Both arms enter the SAME frozen repair engine after producing "
              "their state update.", file=out)
        run_ok = True
        for c in conds:
            run_ok = trace_one(c, args.seed, out) and run_ok
        print(f"\n{'=' * 78}", file=out)
        print(f"PIPELINE GATE: {'PASS' if run_ok else 'FAIL'}", file=out)
        if not run_ok:
            print("Do not run GPU experiments until this passes.", file=out)
        ok = run_ok
    if fh:
        fh.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
