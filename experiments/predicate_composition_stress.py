#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import itertools
from pathlib import Path
from typing import Any

from cope.decomposed_validator import PREDICATE_GROUPS, decomposed_violations
from cope.native_ntrack import derive_post_state, load_manifest, state_without_history, validate_and_compile
from cope.types import canonical_json, stable_hash


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_mutations(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 8 or tuple(row["predicate_group"] for row in rows) != PREDICATE_GROUPS:
        raise ValueError("mutation manifest must match the eight frozen predicate groups in order")
    return rows


def apply_mutation(candidate: dict[str, Any], mutation_id: str) -> None:
    if mutation_id == "M01":
        candidate["evidence_versions"]["event_id"] = "unauthorized:fake-evidence"
    elif mutation_id == "M02":
        candidate["state_version"] += 1
    elif mutation_id == "M03":
        next(row for row in candidate["commitments"] if row["id"] == "deliver:b")["lifecycle_status"] = "active"
    elif mutation_id == "M04":
        candidate["current_goal"]["all"].append({"predicate": "inspect", "arguments": ["package_a"]})
    elif mutation_id == "M05":
        candidate["progress_ledger"] = []
    elif mutation_id == "M06":
        candidate["plan"] = []
    elif mutation_id == "M07":
        candidate["entities"] = [row for row in candidate["entities"] if row["id"] != "package_c"]
    elif mutation_id == "M08":
        next(row for row in candidate["commitments"] if row["id"] == "deliver:a")["lifecycle_status"] = "cancelled"
    else:
        raise ValueError(mutation_id)


def evaluate_candidate(
    candidate_id: str,
    case,
    canonical: dict[str, Any],
    candidate: dict[str, Any],
    mutation_rows: list[dict[str, str]],
) -> dict[str, Any]:
    caller_before = canonical_json(case.pre_state)
    expected_groups = [row["predicate_group"] for row in mutation_rows]
    violations = decomposed_violations(candidate, case.pre_state, case.event)
    observed_groups = [group for group in PREDICATE_GROUPS if violations[group]]
    exact_accepted = True
    exact_exception = ""
    try:
        validate_and_compile(candidate, case.pre_state, case.event)
    except Exception as exc:
        exact_accepted = False
        exact_exception = f"{type(exc).__name__}:{exc}"
    decomposed_accepted = not observed_groups
    candidate_changed = canonical_json(candidate) != canonical_json(canonical)
    attribution_exact = observed_groups == expected_groups
    caller_unchanged = canonical_json(case.pre_state) == caller_before
    passed = bool(
        candidate_changed and not exact_accepted and not decomposed_accepted
        and attribution_exact and caller_unchanged
    )
    return {
        "candidate_id": candidate_id,
        "case_id": case.case_id,
        "combination_size": len(mutation_rows),
        "mutation_ids": ";".join(row["mutation_id"] for row in mutation_rows),
        "expected_groups": ";".join(expected_groups),
        "observed_groups": ";".join(observed_groups),
        "violation_codes": ";".join(
            f"{group}:{code}" for group in observed_groups for code in violations[group]
        ),
        "candidate_sha256": stable_hash(candidate),
        "canonical_sha256": stable_hash(canonical),
        "candidate_changed": candidate_changed,
        "exact_validator_accepted": exact_accepted,
        "exact_exception": exact_exception,
        "decomposed_validator_accepted": decomposed_accepted,
        "attribution_exact": attribution_exact,
        "caller_state_unchanged": caller_unchanged,
        "pass": passed,
    }


def run_experiment(case_manifest: Path, mutation_manifest: Path):
    cases = load_manifest(case_manifest)
    by_id = {case.case_id: case for case in cases}
    mutations = load_mutations(mutation_manifest)
    clean_rows = []
    for case in cases:
        candidate = state_without_history(derive_post_state(case.pre_state, case.event))
        violations = decomposed_violations(candidate, case.pre_state, case.event)
        exact_accepted = True
        try:
            validate_and_compile(candidate, case.pre_state, case.event)
        except Exception:
            exact_accepted = False
        clean_rows.append({
            "case_id": case.case_id,
            "candidate_sha256": stable_hash(candidate),
            "violated_groups": ";".join(group for group in PREDICATE_GROUPS if violations[group]),
            "exact_validator_accepted": exact_accepted,
            "decomposed_validator_accepted": not any(violations.values()),
            "pass": exact_accepted and not any(violations.values()),
        })

    fault_rows = []
    auth = mutations[0]
    auth_case = by_id[auth["source_case"]]
    auth_canonical = state_without_history(derive_post_state(auth_case.pre_state, auth_case.event))
    auth_candidate = copy.deepcopy(auth_canonical)
    apply_mutation(auth_candidate, auth["mutation_id"])
    fault_rows.append(evaluate_candidate("AUTH_SINGLE", auth_case, auth_canonical, auth_candidate, [auth]))

    replacement_case = by_id["replace_pending_target"]
    canonical = state_without_history(derive_post_state(replacement_case.pre_state, replacement_case.event))
    composable = mutations[1:]
    for size in (1, 2, 3):
        for index, combination in enumerate(itertools.combinations(composable, size), start=1):
            candidate = copy.deepcopy(canonical)
            for mutation in combination:
                apply_mutation(candidate, mutation["mutation_id"])
            candidate_id = f"K{size}_{index:02d}"
            fault_rows.append(evaluate_candidate(
                candidate_id, replacement_case, canonical, candidate, list(combination)
            ))

    ablation = []
    for mutation in mutations:
        singleton = next(row for row in fault_rows if row["mutation_ids"] == mutation["mutation_id"])
        observed = {item for item in singleton["observed_groups"].split(";") if item}
        remaining = observed - {mutation["predicate_group"]}
        ablation.append({
            "mutation_id": mutation["mutation_id"],
            "predicate_group": mutation["predicate_group"],
            "singleton_candidate_id": singleton["candidate_id"],
            "singleton_observed_groups": singleton["observed_groups"],
            "violations_after_removing_group": ";".join(sorted(remaining)),
            "would_fail_open_if_group_removed": not remaining,
            "pass": observed == {mutation["predicate_group"]} and not remaining,
        })
    return clean_rows, fault_rows, ablation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--mutation-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    clean, faults, ablation = run_experiment(args.case_manifest, args.mutation_manifest)
    write_csv(args.output_dir / "02_CLEAN_CONTROLS.csv", clean)
    write_csv(args.output_dir / "03_COMPOSITION_RESULTS.csv", faults)
    write_csv(args.output_dir / "04_SINGLETON_ABLATION.csv", ablation)
    size_counts = {size: sum(int(row["combination_size"]) == size for row in faults) for size in (1, 2, 3)}
    decision = bool(
        len(clean) == 12 and all(row["pass"] for row in clean)
        and len(faults) == 64 and all(row["pass"] for row in faults)
        and size_counts == {1: 8, 2: 21, 3: 35}
        and len(ablation) == 8 and all(row["pass"] for row in ablation)
    )
    lines = [
        "schema_version=predicate-composition-status-v1",
        f"clean_pass={sum(bool(row['pass']) for row in clean)}/12",
        f"fault_candidates_changed={sum(bool(row['candidate_changed']) for row in faults)}/64",
        f"decomposed_rejected={sum(not bool(row['decomposed_validator_accepted']) for row in faults)}/64",
        f"exact_rejected={sum(not bool(row['exact_validator_accepted']) for row in faults)}/64",
        f"exact_attribution={sum(bool(row['attribution_exact']) for row in faults)}/64",
        f"size1_candidates={size_counts[1]}/8",
        f"size2_candidates={size_counts[2]}/21",
        f"size3_candidates={size_counts[3]}/35",
        f"singleton_ablation_fail_open={sum(bool(row['would_fail_open_if_group_removed']) for row in ablation)}/8",
        f"decision={'PASS' if decision else 'FAIL'}",
        "evidence_class=offline_white_box_predicate_composition",
        "learned_provider_calls=0",
        "gpu_llm_robot_simulator_used=false",
        "reserved_states_27_49_read=false",
    ]
    (args.output_dir / "05_STATUS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if decision else 2


if __name__ == "__main__":
    raise SystemExit(main())
