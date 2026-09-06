#!/usr/bin/env python3
"""Side-by-side dry run: CoPE patches locally, FSR-PC regenerates completely.

Prints one traced episode per arm from the SAME (condition, seed), showing:

  * the identical `AdaptationInput` fingerprint handed to both arms
  * the typed patch (CoPE) vs the regenerated state (FSR-PC)
  * the resulting persistent state, slot by slot
  * the compiled `ExecutorRequest` --- the same interface for both

    python3 scripts/cope_dry_run.py --condition I4 --seed 0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# In the repository the packages sit at ROOT; in the handoff package they sit
# under ROOT/code. Support both so this script runs unmodified in either.
for _p in (ROOT / "code", ROOT):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from cope.benchmark import BasketTaskSpec, run_episode  # noqa: E402


def show(res, out) -> None:
    m = res.spec.method
    print(f"\n{'=' * 74}\n  {m}   condition={res.spec.condition}  "
          f"seed={res.spec.seed}\n{'=' * 74}", file=out)

    print("\n-- adaptation inputs (fingerprints) --", file=out)
    for i, fp in enumerate(res.adaptation_input_fingerprints, 1):
        print(f"   event {i}: {fp}", file=out)

    print("\n-- adaptation output --", file=out)
    for p in getattr(res.policy, "patches", []):
        print(f"   PATCH {p.patch_id}  ({len(p.ops)} ops, "
              f"{len(p.touched_ids)} slots touched)", file=out)
        for o in p.ops:
            tgt = o.target_id or o.new_slot_id
            arrow = f" -> {o.new_slot_id}" if o.new_slot_id and o.target_id else ""
            print(f"      {o.op.value:11s} {tgt}{arrow}   [{o.reason}]", file=out)
    for g in getattr(res.policy, "regenerations", []):
        print(f"   REGENERATED STATE {g.regen_id}  "
              f"({len(g.slots)} slots re-emitted, 0 edits)", file=out)
        for s in g.slots:
            print(f"      {s.mode.value:11s} {s.id:26s} {s.grounding}", file=out)

    print("\n-- persistent state after the episode --", file=out)
    for sid in res.store.state.ids():
        s = res.store.state.get(sid)
        ln = s.lineage
        rel = ""
        if ln.overridden_by:
            rel = f"  overridden_by={ln.overridden_by}"
        elif ln.overrides:
            rel = f"  overrides={list(ln.overrides)}"
        print(f"   {s.mode.value:11s} {s.id:26s} hist={len(s.history)}{rel}",
              file=out)

    print("\n-- compiled ExecutorRequest (identical interface) --", file=out)
    req = res.policy.mgr.compile()
    print(json.dumps(req.to_dict(), indent=6, default=str), file=out)

    x = res.metrics
    print(f"\n-- metrics --\n   revised_task_success   {x.revised_task_success}"
          f"\n   identity_preserved     {x.identity_preserved}"
          f"\n   slots_touched_per_event {x.slots_touched_per_event}"
          f"\n   normalized_edit_dist   {x.normalized_edit_distance}"
          f"\n   audit_coverage         {x.audit_coverage}"
          f"\n   audit_answerable       {x.audit_answerable}", file=out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--condition", default="I4",
                    choices=["nominal", "I1", "I2", "I3", "I4"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=None,
                    help="write the trace to a file as well as stdout")
    args = ap.parse_args()

    results = {m: run_episode(BasketTaskSpec(seed=args.seed,
                                             condition=args.condition, method=m))
               for m in ("CoPE", "FSR-PC")}

    streams = [sys.stdout]
    fh = None
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        fh = open(args.out, "w")
        streams.append(fh)

    for out in streams:
        a, b = results["CoPE"], results["FSR-PC"]
        print(f"CoPE vs FSR-PC dry run --- condition={args.condition} "
              f"seed={args.seed}", file=out)
        same = (a.adaptation_input_fingerprints ==
                b.adaptation_input_fingerprints)
        print(f"identical adaptation inputs at every event: {same}", file=out)
        for r in (a, b):
            show(r, out)
        print(f"\n{'=' * 74}\nSummary\n{'=' * 74}", file=out)
        print(f"  CoPE   touched {a.metrics.slots_touched_per_event} slots/event, "
              f"regenerated {a.metrics.slots_regenerated}, "
              f"identity preserved {a.metrics.identity_preserved}", file=out)
        print(f"  FSR-PC touched {b.metrics.slots_touched_per_event} slots/event, "
              f"regenerated {b.metrics.slots_regenerated}, "
              f"identity preserved {b.metrics.identity_preserved}", file=out)
        print(f"  same final task outcome: "
              f"{a.metrics.revised_task_success == b.metrics.revised_task_success}",
              file=out)
    if fh:
        fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
