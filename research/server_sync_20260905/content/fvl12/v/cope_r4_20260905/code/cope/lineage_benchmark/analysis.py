"""Paired primary and diagnostic analyses for completed r3 result bundles."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


def wilson(k: int, n: int, z: float = 1.959963984540054) -> List[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    den = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [max(0.0, centre - half), min(1.0, centre + half)]


def mcnemar_exact(a: Sequence[bool], b: Sequence[bool]) -> Dict[str, Any]:
    cope_only = sum(x and not y for x, y in zip(a, b))
    fsrpc_only = sum(y and not x for x, y in zip(a, b))
    discordant = cope_only + fsrpc_only
    if discordant == 0:
        p = 1.0
    else:
        smaller = min(cope_only, fsrpc_only)
        tail = sum(math.comb(discordant, i) for i in range(smaller + 1)) / (2 ** discordant)
        p = min(1.0, 2.0 * tail)
    return {
        "discordant_CoPE_only": cope_only,
        "discordant_FSRPC_only": fsrpc_only,
        "mcnemar_exact_p": p,
    }


def paired_bootstrap_difference(
    a: Sequence[bool], b: Sequence[bool], *, seed: int = 1701, draws: int = 10000
) -> List[float]:
    if not a:
        return [0.0, 0.0, 0.0]
    diffs = [float(x) - float(y) for x, y in zip(a, b)]
    observed = sum(diffs) / len(diffs)
    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        samples.append(sum(diffs[rng.randrange(len(diffs))] for _ in diffs) / len(diffs))
    samples.sort()
    lo = samples[int(0.025 * (draws - 1))]
    hi = samples[int(0.975 * (draws - 1))]
    return [observed, lo, hi]


def _rate(rows: Sequence[Mapping[str, Any]], field: str) -> Dict[str, Any]:
    vals = [bool(row["metrics"][field]) for row in rows]
    k, n = sum(vals), len(vals)
    return {"success": k, "n": n, "rate": (k / n if n else None), "wilson95": wilson(k, n)}


def analyse(rows: Sequence[Mapping[str, Any]], primary_profile: str) -> Dict[str, Any]:
    grouped: Dict[Tuple[str, int], Dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        grouped[(str(row["profile"]), int(row["seed"]))][str(row["method"])] = row

    profiles: Dict[str, Any] = {}
    for profile in sorted({str(row["profile"]) for row in rows}):
        profile_rows = [row for row in rows if row["profile"] == profile]
        methods = {
            method: [row for row in profile_rows if row["method"] == method]
            for method in ("CoPE", "FSR-PC")
        }
        pairs = [
            pair for (name, _), pair in sorted(grouped.items())
            if name == profile and {"CoPE", "FSR-PC"}.issubset(pair)
        ]
        cope = [bool(pair["CoPE"]["metrics"]["task_completion"]) for pair in pairs]
        fsrpc = [bool(pair["FSR-PC"]["metrics"]["task_completion"]) for pair in pairs]
        both_valid_pairs = [
            pair for pair in pairs
            if pair["CoPE"]["metrics"]["all_generations_valid"]
            and pair["FSR-PC"]["metrics"]["all_generations_valid"]
        ]
        conditional_cope = [
            bool(pair["CoPE"]["metrics"]["task_completion"])
            for pair in both_valid_pairs
        ]
        conditional_fsrpc = [
            bool(pair["FSR-PC"]["metrics"]["task_completion"])
            for pair in both_valid_pairs
        ]
        def exogenous_prefix_equal(pair):
            left = [event["exogenous_fingerprint"] for event in pair["CoPE"]["events"]]
            right = [event["exogenous_fingerprint"] for event in pair["FSR-PC"]["events"]]
            common = min(len(left), len(right))
            return left[:common] == right[:common]

        exogenous_equal = all(exogenous_prefix_equal(pair) for pair in pairs)
        profiles[profile] = {
            "task_completion": {
                method: _rate(method_rows, "task_completion")
                for method, method_rows in methods.items()
            },
            "generation_validity": {
                method: _rate(method_rows, "all_generations_valid")
                for method, method_rows in methods.items()
            },
            "paired_task_completion": {
                **mcnemar_exact(cope, fsrpc),
                "difference_CoPE_minus_FSRPC_bootstrap95": paired_bootstrap_difference(
                    cope, fsrpc
                ),
                "n_pairs": len(pairs),
            },
            "conditional_on_both_generating_valid_states": {
                "n_pairs": len(both_valid_pairs),
                "CoPE": {
                    "success": sum(conditional_cope),
                    "rate": (
                        sum(conditional_cope) / len(conditional_cope)
                        if conditional_cope else None
                    ),
                },
                "FSR-PC": {
                    "success": sum(conditional_fsrpc),
                    "rate": (
                        sum(conditional_fsrpc) / len(conditional_fsrpc)
                        if conditional_fsrpc else None
                    ),
                },
                "paired": mcnemar_exact(conditional_cope, conditional_fsrpc),
                "note": (
                    "diagnostic only; primary task completion retains timeout, "
                    "truncation, parse, and schema failures"
                ),
            },
            "all_paired_exogenous_fingerprints_equal_until_first_failure": exogenous_equal,
            "failure_status_counts": {
                method: dict(Counter(
                    row["metrics"].get("first_failure") or "none"
                    for row in method_rows
                ))
                for method, method_rows in methods.items()
            },
            "mean_completion_tokens": {
                method: (
                    sum(row["metrics"]["total_completion_tokens"] for row in method_rows)
                    / len(method_rows)
                    if method_rows else None
                )
                for method, method_rows in methods.items()
            },
        }

    return {
        "schema_version": "cope-fsrpc-r3-analysis-v1",
        "primary_profile": primary_profile,
        "primary": profiles.get(primary_profile, {}),
        "profiles": profiles,
        "interpretation_boundary": (
            "The primary endpoint is end-to-end task completion under an equal "
            "per-call model/output/time budget. The experiment does not claim "
            "that an unlimited perfect full-state regenerator is logically unable "
            "to reconstruct the state."
        ),
    }


def load_results(root: str | Path) -> List[Dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(Path(root).rglob("result.json"))
    ]
