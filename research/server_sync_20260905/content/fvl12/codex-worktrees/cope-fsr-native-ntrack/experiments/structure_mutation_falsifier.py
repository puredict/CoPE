#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from cope.decomposed_validator import decomposed_violations
from cope.native_ntrack import derive_post_state, load_manifest, state_without_history, validate_and_compile
from cope.types import canonical_json, stable_hash


ORDER_ONLY_PATHS = {"/commitments", "/entities", "/progress_ledger"}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def pointer(path: tuple[Any, ...]) -> str:
    if not path:
        return "/"
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in path)


def assignments(value: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[str, tuple[Any, ...], Any]]:
    if isinstance(value, dict):
        for key in value:
            yield "delete_field", path, key
        if "__unknown_mutation__" not in value:
            yield "add_unknown_field", path, None
        for key, item in value.items():
            yield from assignments(item, path + (key,))
        return
    if isinstance(value, list):
        for index in range(len(value)):
            yield "drop_list_item", path, index
            yield "duplicate_list_item", path, index
        yield "append_scalar", path, None
        if len(value) >= 2 and value != list(reversed(value)):
            yield "reverse_list", path, None
        for index, item in enumerate(value):
            yield from assignments(item, path + (index,))
        return
    if isinstance(value, bool):
        yield "mutate_bool", path, None
    elif isinstance(value, int):
        yield "mutate_int", path, None
    elif isinstance(value, float):
        yield "mutate_float", path, None
    elif isinstance(value, str):
        yield "mutate_string", path, None
    elif value is None:
        yield "mutate_null", path, None


def node_at(root: Any, path: tuple[Any, ...]) -> Any:
    value = root
    for part in path:
        value = value[part]
    return value


def apply_assignment(root: dict[str, Any], operator: str, path: tuple[Any, ...], argument: Any) -> dict[str, Any]:
    candidate = copy.deepcopy(root)
    node = node_at(candidate, path)
    if operator == "delete_field":
        del node[argument]
    elif operator == "add_unknown_field":
        node["__unknown_mutation__"] = "mutation"
    elif operator == "drop_list_item":
        del node[argument]
    elif operator == "duplicate_list_item":
        node.insert(argument + 1, copy.deepcopy(node[argument]))
    elif operator == "append_scalar":
        node.append("__mutation_scalar__")
    elif operator == "reverse_list":
        node.reverse()
    else:
        if not path:
            raise ValueError("root scalar mutation is unsupported")
        parent = node_at(candidate, path[:-1])
        key = path[-1]
        value = parent[key]
        if operator == "mutate_bool":
            parent[key] = not value
        elif operator == "mutate_int":
            parent[key] = value + 1
        elif operator == "mutate_float":
            parent[key] = value + 0.5
        elif operator == "mutate_string":
            parent[key] = value + "__mutation__"
        elif operator == "mutate_null":
            parent[key] = "__mutation_null__"
        else:
            raise ValueError(operator)
    return candidate


def same_multiset(left: Any, right: Any) -> bool:
    if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
        return False
    return Counter(canonical_json(item) for item in left) == Counter(canonical_json(item) for item in right)


def run_experiment(case_manifest: Path):
    cases = load_manifest(case_manifest)
    clean_rows = []
    mutation_rows = []
    for case in cases:
        caller_before = canonical_json(case.pre_state)
        canonical = state_without_history(derive_post_state(case.pre_state, case.event))
        clean_violations = decomposed_violations(canonical, case.pre_state, case.event)
        clean_exact = True
        try:
            validate_and_compile(canonical, case.pre_state, case.event)
        except Exception:
            clean_exact = False
        clean_rows.append({
            "case_id": case.case_id,
            "canonical_sha256": stable_hash(canonical),
            "exact_accepted": clean_exact,
            "decomposed_accepted": not any(clean_violations.values()),
            "caller_state_unchanged": canonical_json(case.pre_state) == caller_before,
            "pass": clean_exact and not any(clean_violations.values()) and canonical_json(case.pre_state) == caller_before,
        })

        seen: set[str] = set()
        retained_index = 0
        for traversal_index, (operator, path, argument) in enumerate(assignments(canonical), start=1):
            candidate = apply_assignment(canonical, operator, path, argument)
            candidate_hash = stable_hash(candidate)
            if candidate_hash in seen:
                continue
            seen.add(candidate_hash)
            retained_index += 1
            changed = canonical_json(candidate) != canonical_json(canonical)
            exact_accepted = True
            exact_exception = ""
            try:
                validate_and_compile(candidate, case.pre_state, case.event)
            except Exception as exc:
                exact_accepted = False
                exact_exception = f"{type(exc).__name__}:{exc}"
            decomp_crash = False
            decomp_exception = ""
            violations = {}
            try:
                violations = decomposed_violations(candidate, case.pre_state, case.event)
            except Exception as exc:
                decomp_crash = True
                decomp_exception = f"{type(exc).__name__}:{exc}"
            violated_groups = [group for group, codes in violations.items() if codes]
            decomp_accepted = bool(not decomp_crash and not violated_groups)
            path_text = pointer(path)
            original_node = node_at(canonical, path)
            candidate_node = node_at(candidate, path)
            order_only = bool(
                decomp_accepted and not exact_accepted and operator == "reverse_list"
                and path_text in ORDER_ONLY_PATHS
                and same_multiset(original_node, candidate_node)
            )
            dangerous = bool(decomp_accepted and not exact_accepted and not order_only)
            caller_unchanged = canonical_json(case.pre_state) == caller_before
            passed = bool(changed and not exact_accepted and not decomp_crash and not dangerous and caller_unchanged)
            mutation_rows.append({
                "case_id": case.case_id,
                "mutation_id": f"{case.case_id}:S{retained_index:04d}",
                "traversal_index": traversal_index,
                "operator": operator,
                "path": path_text,
                "argument": "" if argument is None else argument,
                "candidate_sha256": candidate_hash,
                "canonical_sha256": stable_hash(canonical),
                "candidate_changed": changed,
                "exact_accepted": exact_accepted,
                "exact_exception": exact_exception,
                "decomposed_accepted": decomp_accepted,
                "violated_groups": ";".join(violated_groups),
                "decomposed_crash": decomp_crash,
                "decomposed_exception": decomp_exception,
                "order_only_divergence": order_only,
                "dangerous_blind_spot": dangerous,
                "caller_state_unchanged": caller_unchanged,
                "pass": passed,
            })
    aggregate = []
    for operator in sorted({row["operator"] for row in mutation_rows}):
        selected = [row for row in mutation_rows if row["operator"] == operator]
        aggregate.append({
            "operator": operator,
            "retained_candidates": len(selected),
            "exact_rejected": sum(not bool(row["exact_accepted"]) for row in selected),
            "decomposed_rejected": sum(not bool(row["decomposed_accepted"]) for row in selected),
            "order_only_divergence": sum(bool(row["order_only_divergence"]) for row in selected),
            "dangerous_blind_spot": sum(bool(row["dangerous_blind_spot"]) for row in selected),
            "decomposed_crash": sum(bool(row["decomposed_crash"]) for row in selected),
            "passed": sum(bool(row["pass"]) for row in selected),
        })
    return clean_rows, mutation_rows, aggregate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    clean, mutations, aggregate = run_experiment(args.case_manifest)
    write_csv(args.output_dir / "02_CLEAN_CONTROLS.csv", clean)
    write_csv(args.output_dir / "03_MUTATION_RESULTS.csv", mutations)
    write_csv(args.output_dir / "04_OPERATOR_AGGREGATE.csv", aggregate)
    total = len(mutations)
    changed = sum(bool(row["candidate_changed"]) for row in mutations)
    exact_rejected = sum(not bool(row["exact_accepted"]) for row in mutations)
    decomp_rejected = sum(not bool(row["decomposed_accepted"]) for row in mutations)
    order_only = sum(bool(row["order_only_divergence"]) for row in mutations)
    dangerous = sum(bool(row["dangerous_blind_spot"]) for row in mutations)
    crashes = sum(bool(row["decomposed_crash"]) for row in mutations)
    caller_mutations = sum(not bool(row["caller_state_unchanged"]) for row in mutations)
    decision = bool(
        len(clean) == 12 and all(row["pass"] for row in clean) and total > 0
        and changed == total and exact_rejected == total and dangerous == 0
        and crashes == 0 and caller_mutations == 0 and all(row["pass"] for row in mutations)
    )
    lines = [
        "schema_version=structure-mutation-falsifier-status-v1",
        f"clean_pass={sum(bool(row['pass']) for row in clean)}/12",
        f"retained_mutations={total}",
        f"candidate_changed={changed}/{total}",
        f"exact_rejected={exact_rejected}/{total}",
        f"decomposed_rejected={decomp_rejected}/{total}",
        f"order_only_divergence={order_only}/{total}",
        f"dangerous_blind_spot={dangerous}/{total}",
        f"decomposed_crash={crashes}/{total}",
        f"caller_state_mutation={caller_mutations}/{total}",
        f"decision={'PASS' if decision else 'FAIL'}",
        "evidence_class=offline_structure_agnostic_single_mutation",
        "learned_provider_calls=0",
        "gpu_llm_robot_simulator_used=false",
        "reserved_states_27_49_read=false",
    ]
    (args.output_dir / "05_STATUS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if decision else 2


if __name__ == "__main__":
    raise SystemExit(main())
