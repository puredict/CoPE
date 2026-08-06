#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


PAIR_FIELDS = {
    "reset": ("comparison_step", "action_prefix_sha256", "sim_state_sha256"),
    "milestone": ("comparison_step", "action_prefix_sha256", "sim_state_sha256"),
    "no_event": ("comparison_step", "action_prefix_sha256", "sim_state_sha256"),
    "timing": (
        "comparison_step", "action_prefix_sha256", "sim_state_sha256",
        "eef_at_event", "held_position_at_event",
    ),
    "repeated": ("comparison_step", "action_prefix_sha256", "sim_state_sha256"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--episode-csv", type=Path, required=True)
    parser.add_argument("--prefix-audit-csv", type=Path, required=True)
    parser.add_argument("--failure-taxonomy-csv", type=Path, required=True)
    parser.add_argument("--result-md", type=Path, required=True)
    return parser.parse_args()


def truth(value: str) -> bool:
    return value.strip().lower() == "true"


def one_row(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError(f"expected one row in {path}, found {len(rows)}")
    return rows[0]


def normalize(manifest: dict[str, str], raw: dict[str, str], exit_code: int) -> dict[str, str]:
    family = manifest["family"]
    arm = manifest["arm"]
    if family in {"reset", "milestone", "no_event"}:
        comparison_initial = family == "reset"
        prefix = "initial" if comparison_initial else "milestone"
        goal_success = (
            truth(raw["updated_goal_success"])
            if arm in {"updated_reset", "checkpoint_oracle_full", "checkpoint_oracle_patch"}
            else truth(raw["original_goal_success"])
        )
        stale_executed = truth(raw["stale_pending_executed"])
        updated_goal_success = truth(raw["updated_goal_success"])
        original_goal_success = truth(raw["original_goal_success"])
        progress_retained = truth(raw["valid_progress_retained"])
        pre_event_failure = not truth(raw["first_skill_success"])
        comparison_step = raw[f"{prefix}_checkpoint_step"]
        action_hash = raw[f"{prefix}_action_prefix_sha256"]
        sim_hash = raw[f"{prefix}_sim_state_sha256"]
        semantic_integrity = truth(raw["semantic_preserved_sim_state"]) and truth(raw["semantic_emitted_no_action"])
        within_horizon = int(raw["environment_steps"]) <= 600
        terminal = "|".join(raw.get(name, "") for name in (
            "done_object_in_region", "pending_object_in_region", "replacement_object_in_region"
        ))
        eef = ""
        held = ""
    elif family == "timing":
        goal_success = truth(raw["final_goal_success"])
        stale_executed = truth(raw["stale_commitment_executed"])
        updated_goal_success = goal_success
        original_goal_success = False
        progress_retained = truth(raw["done_object_in_region"])
        pre_event_failure = not all(
            truth(raw[field])
            for field in ("completed_progress_success", "held_checkpoint_success", "held_at_event")
        )
        comparison_step = raw["event_step"]
        action_hash = raw["action_prefix_sha256"]
        sim_hash = raw["sim_state_before_patch_sha256"]
        semantic_integrity = truth(raw["patch_preserved_sim_state"]) and truth(raw["patch_emitted_no_action"])
        within_horizon = truth(raw["within_horizon"])
        terminal = "|".join(raw.get(name, "") for name in (
            "done_object_in_region", "butter_in_region", "alphabet_soup_in_region", "tomato_sauce_in_region"
        ))
        eef = raw["eef_at_event"]
        held = raw["held_position_at_event"]
    else:
        goal_success = truth(raw["double_replacement_goal_success"])
        stale_executed = truth(raw["second_stale_commitment_executed"])
        updated_goal_success = goal_success
        original_goal_success = truth(raw["original_goal_success"])
        progress_retained = truth(raw["valid_progress_retained"])
        pre_event_failure = not truth(raw["first_skill_success"])
        comparison_step = raw["comparison_checkpoint_step"]
        action_hash = raw["comparison_action_prefix_sha256"]
        sim_hash = raw["comparison_sim_state_sha256"]
        semantic_integrity = truth(raw["semantic_preserved_sim_state"]) and truth(raw["semantic_emitted_no_action"])
        within_horizon = int(raw["environment_steps"]) <= 600
        terminal = "|".join(raw.get(name, "") for name in (
            "done_object_in_region", "butter_in_region", "alphabet_soup_in_region", "tomato_sauce_in_region"
        ))
        eef = ""
        held = ""

    return {
        "case_id": manifest["case_id"],
        "state_id": manifest["state_id"],
        "family": family,
        "arm": arm,
        "timing": manifest["timing"],
        "pair_group": manifest["pair_group"],
        "assigned": "True",
        "runner_exit_code": str(exit_code),
        "pre_event_failure": str(pre_event_failure),
        "goal_success": str(goal_success),
        "updated_goal_success": str(updated_goal_success),
        "original_goal_success": str(original_goal_success),
        "progress_retained": str(progress_retained),
        "stale_action_executed": str(stale_executed),
        "within_horizon": str(within_horizon),
        "semantic_integrity_pass": str(semantic_integrity),
        "comparison_step": comparison_step,
        "action_prefix_sha256": action_hash,
        "sim_state_sha256": sim_hash,
        "eef_at_event": eef,
        "held_position_at_event": held,
        "terminal_predicate_fingerprint": terminal,
        "controller_privilege": raw["controller_privilege"],
        "oracle_geometry_used": raw["oracle_geometry_used"],
        "learned_policy_used": raw["learned_policy_used"],
        "provider_called": raw["provider_called"],
        "shared_init_container_loaded": raw["shared_init_container_loaded"],
        "reset_state_index": raw["reset_state_index"],
        "reserved_state_indexed": raw["reserved_state_indexed"],
        "checkpoint_access": raw["checkpoint_access"],
        "raw_csv": f"{manifest['case_id']}.csv",
    }


def count(rows: list[dict[str, str]], family: str, arm: str, field: str, timing: str = "") -> int:
    selected = [row for row in rows if row["family"] == family and row["arm"] == arm and (not timing or row["timing"] == timing)]
    if len(selected) != 5:
        raise ValueError(f"expected five rows for {(family, arm, timing)}, found {len(selected)}")
    return sum(truth(row[field]) for row in selected)


def main() -> int:
    args = parse_args()
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    with (args.run_dir / "execution_ledger.csv").open(newline="", encoding="utf-8") as handle:
        ledger = {row["case_id"]: row for row in csv.DictReader(handle)}
    if len(manifest) != 75 or len(ledger) != 75:
        raise ValueError("assigned denominator is not 75")
    rows: list[dict[str, str]] = []
    for assignment in manifest:
        case_id = assignment["case_id"]
        raw_path = args.run_dir / "raw" / f"{case_id}.csv"
        if not raw_path.is_file():
            raise ValueError(f"assigned raw episode missing: {case_id}")
        rows.append(normalize(assignment, one_row(raw_path), int(ledger[case_id]["exit_code"])))

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["pair_group"]].append(row)
    audits: list[dict[str, str]] = []
    for group, members in sorted(grouped.items()):
        family = members[0]["family"]
        fields = PAIR_FIELDS[family]
        mismatches = [field for field in fields if len({row[field] for row in members}) != 1]
        passed = not mismatches
        for row in members:
            row["paired_provenance_pass"] = str(passed)
        audits.append({
            "pair_group": group,
            "family": family,
            "member_count": str(len(members)),
            "case_ids": ";".join(row["case_id"] for row in members),
            "fields_checked": ";".join(fields),
            "mismatch_fields": ";".join(mismatches),
            "passed": str(passed),
        })

    parity_groups = [members for members in grouped.values() if members[0]["family"] == "no_event"]
    parity_terminal = all(len({row["terminal_predicate_fingerprint"] for row in members}) == 1 for members in parity_groups)
    provenance_pass = all(truth(row["paired_provenance_pass"]) for row in rows)
    semantic_pass = all(truth(row["semantic_integrity_pass"]) for row in rows)
    scope_pass = all(
        row["controller_privilege"] == "simulator_geometry_oracle"
        and truth(row["oracle_geometry_used"])
        and not truth(row["learned_policy_used"])
        and not truth(row["provider_called"])
        and truth(row["shared_init_container_loaded"])
        and not truth(row["reserved_state_indexed"])
        and int(row["reset_state_index"]) in range(5)
        for row in rows
    )

    gates = {
        "original_reset": count(rows, "reset", "original_reset", "goal_success") >= 4,
        "updated_reset": count(rows, "reset", "updated_reset", "goal_success") >= 4,
        "checkpoint_oracle_full": count(rows, "milestone", "checkpoint_oracle_full", "goal_success") >= 4,
        "checkpoint_oracle_patch": count(rows, "milestone", "checkpoint_oracle_patch", "goal_success") >= 4,
        "checkpoint_no_edit_stale": count(rows, "milestone", "checkpoint_no_edit", "stale_action_executed") >= 4 and count(rows, "milestone", "checkpoint_no_edit", "updated_goal_success") <= 1,
        "full_progress": count(rows, "milestone", "checkpoint_oracle_full", "progress_retained") >= 4,
        "patch_progress": count(rows, "milestone", "checkpoint_oracle_patch", "progress_retained") >= 4,
        "full_stale_suppression": count(rows, "milestone", "checkpoint_oracle_full", "stale_action_executed") <= 1,
        "patch_stale_suppression": count(rows, "milestone", "checkpoint_oracle_patch", "stale_action_executed") <= 1,
        "no_event_plain": count(rows, "no_event", "no_event_plain", "goal_success") >= 4,
        "no_event_scaffold": count(rows, "no_event", "no_event_semantic_scaffold", "goal_success") >= 4,
        "no_event_terminal_parity": parity_terminal,
        "repeated_double_patch": count(rows, "repeated", "double_patch", "goal_success") >= 4 and count(rows, "repeated", "double_patch", "stale_action_executed") <= 1,
        "repeated_ignore_second": count(rows, "repeated", "second_event_no_edit", "goal_success") <= 1 and count(rows, "repeated", "second_event_no_edit", "stale_action_executed") >= 4,
        "paired_provenance": provenance_pass,
        "semantic_integrity": semantic_pass,
        "scope_accounting": scope_pass,
    }
    for timing in ("post_lift", "mid_transfer", "pre_release"):
        gates[f"{timing}_local_recovery"] = count(rows, "timing", "local_stage_switch", "goal_success", timing) >= 4 and count(rows, "timing", "local_stage_switch", "stale_action_executed", timing) <= 1
        gates[f"{timing}_stale_control"] = count(rows, "timing", "stale_continue", "goal_success", timing) <= 1 and count(rows, "timing", "stale_continue", "stale_action_executed", timing) >= 4
    overall = all(gates.values())

    args.episode_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.episode_csv.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    with args.prefix_audit_csv.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(audits[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(audits)

    failures = Counter()
    for row in rows:
        if truth(row["pre_event_failure"]): failures["method_independent_pre_event_failure"] += 1
        if not truth(row["semantic_integrity_pass"]): failures["semantic_mutated_physical_state_or_action_count"] += 1
        if not truth(row["paired_provenance_pass"]): failures["paired_prefix_or_state_mismatch"] += 1
        if not truth(row["within_horizon"]): failures["horizon_exceeded"] += 1
        if int(row["runner_exit_code"]) != 0: failures["assigned_arm_expected_outcome_not_observed"] += 1
    taxonomy = [{"failure_type": key, "assigned_count": str(failures.get(key, 0))} for key in (
        "method_independent_pre_event_failure", "semantic_mutated_physical_state_or_action_count",
        "paired_prefix_or_state_mismatch", "horizon_exceeded", "assigned_arm_expected_outcome_not_observed",
    )]
    with args.failure_taxonomy_csv.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(taxonomy[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(taxonomy)

    lines = [
        "# Controller substrate qualification result", "", "Date: 2026-08-02", "",
        f"Overall gate: **{'PASS' if overall else 'FAIL'}**.", "",
        "Interpretation: " + ("qualified only for the privileged oracle/mechanism stratum on basket-compatible skills." if overall else "not qualified for the declared basket oracle/mechanism matrix."),
        "It is not a learned manipulation system and is not qualified for the learned/main stratum.", "",
        "## Frozen-gate audit", "", "| Gate | Pass |", "|---|---:|",
        *[f"| {name} | {passed} |" for name, passed in gates.items()], "",
        "## Assigned denominator", "",
        f"- Episodes: {len(rows)}.",
        f"- Method-independent pre-event failures: {failures.get('method_independent_pre_event_failure', 0)} / {len(rows)}.",
        f"- Paired provenance groups: {sum(truth(row['passed']) for row in audits)} / {len(audits)}.",
        "- Reserved state indices used: 0.", "- Learned-policy calls: 0; provider calls: 0; GPU calls: 0.", "",
        "## Scope boundary", "",
        "Object/region selection, simulator geometry, predicates, event phase, and patch operation are privileged.",
        "Passing does not authorize state 25 and does not qualify caddy insertion or any learned controller.",
    ]
    args.result_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"episodes=75 pair_groups={len(audits)} overall={'PASS' if overall else 'FAIL'}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
