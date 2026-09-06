"""NUMERICAL SANITY CHECK for Theorem 1 (conflict lower bound). CPU-only.

This is NOT a proof.  The analytic statement and proof (for nonempty target
sets) are in docs/THEOREM.md.  This script checks that the implementation's
numerically-minimized J matches the closed-form floor lam*mu/(lam+mu)*delta^2,
i.e. that the code agrees with the algebra.

Run:  python scripts/validate_theorem1.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from rekep_repair.synthetic import sweep_delta, sweep_ratio, conflict_lower_bound


def main() -> None:
    print("=" * 68)
    print("Theorem 1: inf_x [ lam*d(x,A)^2 + mu*d(x,B)^2 ] >= lam*mu/(lam+mu)*delta^2")
    print("(inf, not min: A,B need not be closed. See docs/THEOREM.md for the proof.)")
    print("=" * 68)

    print("\n[A] Sweep separation delta   (lam=2.0, mu=5.0)")
    print(f"{'delta':>8} {'bound':>12} {'numeric':>12} {'slack':>12}  ok")
    checks = sweep_delta([0.25, 0.5, 1.0, 1.5, 2.0, 3.0], lam=2.0, mu=5.0)
    all_ok = True
    for c in checks:
        ok = c.slack >= -1e-4
        all_ok &= ok
        print(f"{c.delta:8.3f} {c.bound:12.5f} {c.numeric_min:12.5f} {c.slack:12.2e}  {'y' if ok else 'N'}")

    print("\n[B] Sweep weight ratio lam/mu at fixed delta=1.0 (mu=5.0)")
    print(f"{'lam/mu':>8} {'bound':>12} {'numeric':>12} {'slack':>12}  ok")
    checks2 = sweep_ratio([0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0], delta=1.0, mu=5.0)
    for c in checks2:
        ok = c.slack >= -1e-4
        all_ok &= ok
        ratio = c.lam / c.mu
        print(f"{ratio:8.3f} {c.bound:12.5f} {c.numeric_min:12.5f} {c.slack:12.2e}  {'y' if ok else 'N'}")

    print("\n[C] Threshold-failure corollary -- FOR FIXED WEIGHTS")
    lam, mu, delta = 2.0, 5.0, 1.0
    floor = conflict_lower_bound(lam, mu, delta)
    eps = 0.5 * floor
    print(f"  at lam={lam}, mu={mu}: success needs J<=eps={eps:.4f}, floor={floor:.4f}")
    print("  => with THESE weights, a fixed-stage simultaneous optimum cannot")
    print("     reach the success threshold.")
    print("  CAVEAT: the floor is NOT uniform over weights -- lam->0 or mu->0")
    print("     drives it to 0.  Claiming 'no weights can succeed' requires")
    print("     bounding the weights away from 0 (see docs/THEOREM.md).")
    for lam2 in (2.0, 0.2, 0.02):
        print(f"       lam={lam2:<5} mu={mu} -> floor={conflict_lower_bound(lam2, mu, delta):.5f}")
    print("  Ordered repair removes the SIMULTANEOUS-conflict term (per-window")
    print("  floor 0).  It does NOT make total trajectory cost zero: an")
    print("  A -> B -> A_restore trace still pays motion, switching and is")
    print("  subject to reachability/collision feasibility.")

    print("\nRESULT:", "ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
