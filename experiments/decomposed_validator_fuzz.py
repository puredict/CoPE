#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import json
import random
from pathlib import Path
from typing import Any

from cope.decomposed_validator import PREDICATE_GROUPS, decomposed_violations
from cope.native_ntrack import derive_post_state, load_manifest, state_without_history, validate_and_compile
from cope.types import canonical_json, stable_hash


JsonPath = tuple[Any, ...]


def walk(value: Any, path: JsonPath = ()) -> list[tuple[JsonPath, Any]]:
    rows = [(path, value)]
    if isinstance(value, dict):
        for key in sorted(value):
            rows.extend(walk(value[key], path + (key,)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(walk(item, path + (index,)))
    return rows


def resolve(root: Any, path: JsonPath) -> Any:
    current = root
    for item in path:
        current = current[item]
    return current


def parent(root: Any, path: JsonPath) -> tuple[Any, Any]:
    return resolve(root, path[:-1]), path[-1]


def pointer(path: JsonPath) -> str:
    return "/" + "/".join(str(item).replace("~", "~0").replace("/", "~1") for item in path)


def mutate_scalar(value: Any, rng: random.Random) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + rng.choice((-7, -1, 1, 9))
    if isinstance(value, float):
        return value + rng.choice((-1.0, 1.0))
    if value is None:
        return "__FUZZ_NONE__"
    if isinstance(value, str):
        return value + "__FUZZ__"
    return "__FUZZ_REPLACEMENT__"


def apply_one(candidate: dict[str, Any], rng: random.Random) -> str:
    nodes = walk(candidate)
    scalars = [(path, value) for path, value in nodes if path and not isinstance(value, (dict, list))]
    dicts = [(path, value) for path, value in nodes if isinstance(value, dict) and value]
    lists = [(path, value) for path, value in nodes if isinstance(value, list) and value]
    reorderable = [(path, value) for path, value in lists if len(value) > 1]
    operations = ["scalar_replace", "dict_delete", "dict_add", "list_delete", "list_duplicate"]
    if reorderable:
        operations.append("list_reverse")
    operation = rng.choice(operations)
    if operation == "scalar_replace":
        path, old = rng.choice(scalars)
        container, key = parent(candidate, path)
        container[key] = mutate_scalar(old, rng)
        return f"scalar_replace:{pointer(path)}"
    if operation == "dict_delete":
        path, mapping = rng.choice(dicts)
        key = rng.choice(sorted(mapping))
        del mapping[key]
        return f"dict_delete:{pointer(path + (key,))}"
    if operation == "dict_add":
        path, mapping = rng.choice([(p, v) for p, v in nodes if isinstance(v, dict)])
        key = "__fuzz_extra__"
        suffix = 0
        while key in mapping:
            suffix += 1
            key = f"__fuzz_extra_{suffix}__"
        mapping[key] = rng.choice((0, False, None, "extra"))
        return f"dict_add:{pointer(path + (key,))}"
    if operation == "list_delete":
        path, sequence = rng.choice(lists)
        index = rng.randrange(len(sequence))
        sequence.pop(index)
        return f"list_delete:{pointer(path + (index,))}"
    if operation == "list_duplicate":
        path, sequence = rng.choice(lists)
        index = rng.randrange(len(sequence))
        sequence.insert(index, copy.deepcopy(sequence[index]))
        return f"list_duplicate:{pointer(path + (index,))}"
    path, sequence = rng.choice(reorderable)
    sequence.reverse()
    return f"list_reverse:{pointer(path)}"


def decision(candidate: dict[str, Any], pre_state: dict[str, Any], event: dict[str, Any]):
    exact_accepted = True
    exact_error = ""
    try:
        validate_and_compile(candidate, pre_state, event)
    except Exception as exc:
        exact_accepted = False
        exact_error = f"{type(exc).__name__}:{exc}"
    decomposed_error = ""
    violations = {group: [] for group in PREDICATE_GROUPS}
    try:
        violations = decomposed_violations(candidate, pre_state, event)
        decomposed_accepted = not any(violations.values())
    except Exception as exc:
        decomposed_accepted = False
        decomposed_error = f"{type(exc).__name__}:{exc}"
    groups = [group for group in PREDICATE_GROUPS if violations.get(group)]
    return exact_accepted, decomposed_accepted, exact_error, decomposed_error, groups


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260803)
    parser.add_argument("--samples-per-case", type=int, default=250)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    rng = random.Random(args.seed)
    cases = load_manifest(args.manifest)
    fields = [
        "case_id", "sample_index", "mutation_count", "mutations", "candidate_sha256",
        "candidate_changed", "exact_accepted", "decomposed_accepted", "decision_parity",
        "exact_error", "decomposed_error", "violated_groups", "caller_state_unchanged",
    ]
    rows = []
    clean_rows = []
    for case in cases:
        canonical = state_without_history(derive_post_state(case.pre_state, case.event))
        clean = decision(canonical, case.pre_state, case.event)
        clean_rows.append({
            "case_id": case.case_id,
            "exact_accepted": clean[0],
            "decomposed_accepted": clean[1],
            "decision_parity": clean[0] == clean[1],
            "pass": clean[0] and clean[1],
        })
        caller_before = canonical_json(case.pre_state)
        for sample_index in range(args.samples_per_case):
            candidate = copy.deepcopy(canonical)
            mutation_count = rng.randint(1, 4)
            mutations = [apply_one(candidate, rng) for _ in range(mutation_count)]
            exact, decomposed, exact_error, decomp_error, groups = decision(
                candidate, case.pre_state, case.event
            )
            rows.append({
                "case_id": case.case_id,
                "sample_index": sample_index,
                "mutation_count": mutation_count,
                "mutations": ";".join(mutations),
                "candidate_sha256": stable_hash(candidate),
                "candidate_changed": canonical_json(candidate) != canonical_json(canonical),
                "exact_accepted": exact,
                "decomposed_accepted": decomposed,
                "decision_parity": exact == decomposed,
                "exact_error": exact_error,
                "decomposed_error": decomp_error,
                "violated_groups": ";".join(groups),
                "caller_state_unchanged": canonical_json(case.pre_state) == caller_before,
            })
    with (args.output_dir / "02_CLEAN_CONTROLS.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(clean_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(clean_rows)
    with (args.output_dir / "03_FUZZ_RESULTS.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    parity = sum(bool(row["decision_parity"]) for row in rows)
    changed = sum(bool(row["candidate_changed"]) for row in rows)
    caller_ok = sum(bool(row["caller_state_unchanged"]) for row in rows)
    exact_reject = sum(not bool(row["exact_accepted"]) for row in rows)
    decomp_reject = sum(not bool(row["decomposed_accepted"]) for row in rows)
    clean_pass = sum(bool(row["pass"]) for row in clean_rows)
    passed = clean_pass == len(cases) and parity == len(rows) and changed == len(rows) and caller_ok == len(rows)
    status = [
        "schema_version=decomposed-validator-fuzz-v1",
        f"seed={args.seed}",
        f"cases={len(cases)}",
        f"samples_per_case={args.samples_per_case}",
        f"assigned_mutants={len(rows)}",
        f"clean_accept={clean_pass}/{len(cases)}",
        f"mutants_changed={changed}/{len(rows)}",
        f"exact_rejected={exact_reject}/{len(rows)}",
        f"decomposed_rejected={decomp_reject}/{len(rows)}",
        f"decision_parity={parity}/{len(rows)}",
        f"caller_state_unchanged={caller_ok}/{len(rows)}",
        f"decision={'PASS' if passed else 'FAIL'}",
        "evidence_class=offline_seeded_structure_field_differential_fuzzing",
        "learned_provider_calls=0",
        "gpu_llm_robot_simulator_used=false",
        "reserved_states_27_49_read=false",
    ]
    (args.output_dir / "04_STATUS.txt").write_text("\n".join(status) + "\n", encoding="utf-8")
    (args.output_dir / "05_RUN_CONFIG.txt").write_text(
        json.dumps(vars(args), default=str, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("\n".join(status))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
