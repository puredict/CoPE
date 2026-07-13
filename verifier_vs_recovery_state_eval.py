from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from statistics import mean


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--summary", default="/home/lijingsu/vla/disturbance_outputs/full_spatial/2026_07_07-23_57_40/summary.json")
    p.add_argument("--out-dir", default="/home/lijingsu/vla/second_necessity_outputs")
    p.add_argument("--disturbance-step", type=int, default=None)
    return p.parse_args()


def tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if t and t not in {"the", "and", "to", "in", "on", "of", "a", "an", "up"}}


def object_from_joint(joint: str) -> str:
    return joint.replace("_joint0", "").replace("_", " ")


def task_objects(task_description: str) -> list[str]:
    # Lightweight noun-ish extraction for LIBERO task text. Good enough for diagnosis, not a semantic parser.
    candidates = []
    patterns = [
        r"pick up the (.*?) and place it",
        r"pick up the (.*?) between",
        r"pick up the (.*?) from",
        r"put the (.*?) on",
        r"put the (.*?) in",
        r"place the (.*?) on",
        r"place the (.*?) in",
    ]
    for pat in patterns:
        m = re.search(pat, task_description.lower())
        if m:
            candidates.append(m.group(1).strip())
    # Also keep common object phrase after articles.
    for m in re.finditer(r"(?:the|a|an) ([a-z0-9 ]+?)(?: between| from| in| on| and|$)", task_description.lower()):
        phrase = m.group(1).strip()
        if len(phrase) > 2:
            candidates.append(phrase)
    uniq = []
    for c in candidates:
        if c not in uniq:
            uniq.append(c)
    return uniq


def disturbed_records(records):
    return [r for r in records if r["condition"] == "disturbed"]


def clean_record_map(records):
    return {(r["task_id"], r["trial_id"]): r for r in records if r["condition"] == "clean"}


def verifier_only_policy(record: dict, disturbance_step: int) -> dict:
    # Oracle verifier knows target displacement happened and old continuation is invalid.
    # But it has no persistent subgoal / validity state, so it can only choose generic safety action.
    detected = bool(record.get("disturbance"))
    return {
        "diagnostic_assumption": "oracle disturbance event is known by code",
        "not_empirical_model_measurement": True,
        "detects_invalid_continuation": detected,
        "decision": "stop_or_full_replan" if detected else "continue",
        "can_identify_affected_object": False,
        "can_identify_invalid_state": False,
        "can_preserve_completed_subgoals": False,
        "selective_recovery_action": None,
        "recovery_type_correct": False,
        "expected_task_outcome_without_extra_state": "safe_but_not_selectively_recovered" if detected else "continue",
    }


def structured_state_policy(record: dict, clean: dict | None, disturbance_step: int) -> dict:
    disturbance = record.get("disturbance") or {}
    joint = disturbance.get("joint", record.get("target_joint", "unknown_joint"))
    affected = object_from_joint(joint)
    task_desc = record["task_description"]
    affected_toks = tokens(affected)
    desc_toks = tokens(task_desc)
    task_relevant = bool(affected_toks & desc_toks)
    clean_success_step = clean.get("num_policy_steps") if clean else None
    clean_completed_before_disturbance = bool(clean and clean.get("success") and clean_success_step <= disturbance_step)
    state = {
        "diagnostic_assumption": "minimal structured state is generated from summary fields by code",
        "not_empirical_model_measurement": True,
        "phase": "disturbed_execution",
        "task_id": record["task_id"],
        "task_description": task_desc,
        "affected_object": affected,
        "affected_joint": joint,
        "target_object_pose_valid": False,
        "must_revalidate": ["affected_object_pose", "goal_region_pose", "grasp_validity"],
        "completed_subgoals": [] if not clean_completed_before_disturbance else ["task_completed_before_disturbance_in_clean_reference"],
        "paused_goal": "complete_original_instruction",
        "task_relevant_disturbance": task_relevant,
    }
    if task_relevant:
        recovery = "relocalize_affected_object_then_continue"
    else:
        recovery = "ignore_or_monitor_unrelated_object_then_continue"
    return {
        "diagnostic_assumption": "capability fields are prescribed by this diagnostic script",
        "not_empirical_model_measurement": True,
        "state": state,
        "detects_invalid_continuation": True,
        "decision": recovery,
        "can_identify_affected_object": affected != "unknown joint",
        "can_identify_invalid_state": True,
        "can_preserve_completed_subgoals": True,
        "selective_recovery_action": recovery,
        "recovery_type_correct": True,
        "expected_task_outcome_without_extra_state": "selective_recovery_possible_but_not_implemented",
    }


def main():
    args = parse_args()
    summary_path = Path(args.summary)
    summary = json.loads(summary_path.read_text())
    records = summary["records"]
    disturbance_step = args.disturbance_step
    if disturbance_step is None:
        disturbance_step = int(summary.get("args", {}).get("disturbance_step", 70))
    clean_map = clean_record_map(records)

    rows = []
    for r in disturbed_records(records):
        clean = clean_map.get((r["task_id"], r["trial_id"]))
        verifier = verifier_only_policy(r, disturbance_step)
        structured = structured_state_policy(r, clean, disturbance_step)
        row = {
            "task_id": r["task_id"],
            "trial_id": r["trial_id"],
            "task_description": r["task_description"],
            "target_joint": r.get("target_joint"),
            "disturbance": r.get("disturbance"),
            "clean_success": bool(clean and clean.get("success")),
            "disturbed_success": bool(r.get("success")),
            "clean_steps": clean.get("num_policy_steps") if clean else None,
            "disturbed_steps": r.get("num_policy_steps"),
            "oracle_verifier_only": verifier,
            "minimal_structured_recovery_state": structured,
        }
        rows.append(row)

    def rate(key: str, branch: str) -> float:
        return mean(1.0 if row[branch][key] else 0.0 for row in rows) if rows else 0.0

    metrics = {
        "source_summary": str(summary_path),
        "diagnostic_assumption": "This file compares programmed diagnostic labels, not model/verifier measurements.",
        "not_empirical_model_measurement": True,
        "exclude_from_formal_success_summaries": True,
        "num_disturbed_episodes": len(rows),
        "clean_success_rate_reference": summary.get("clean_success_rate"),
        "disturbed_success_rate_reactive_vla": summary.get("disturbed_success_rate"),
        "oracle_verifier_only": {
            "invalid_continuation_detection_rate": rate("detects_invalid_continuation", "oracle_verifier_only"),
            "affected_object_identification_rate": rate("can_identify_affected_object", "oracle_verifier_only"),
            "invalid_state_identification_rate": rate("can_identify_invalid_state", "oracle_verifier_only"),
            "completed_subgoal_preservation_rate": rate("can_preserve_completed_subgoals", "oracle_verifier_only"),
            "selective_recovery_rate": rate("recovery_type_correct", "oracle_verifier_only"),
        },
        "minimal_structured_recovery_state": {
            "invalid_continuation_detection_rate": rate("detects_invalid_continuation", "minimal_structured_recovery_state"),
            "affected_object_identification_rate": rate("can_identify_affected_object", "minimal_structured_recovery_state"),
            "invalid_state_identification_rate": rate("can_identify_invalid_state", "minimal_structured_recovery_state"),
            "completed_subgoal_preservation_rate": rate("can_preserve_completed_subgoals", "minimal_structured_recovery_state"),
            "selective_recovery_rate": rate("recovery_type_correct", "minimal_structured_recovery_state"),
        },
        "interpretation": "Diagnostic only: oracle verifier and structured-state capability fields are programmed assumptions. They must not be reported as empirical model measurements.",
    }

    out_dir = Path(args.out_dir) / time.strftime("%Y_%m_%d-%H_%M_%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "second_necessity_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (out_dir / "second_necessity_rows.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    md = out_dir / "README.md"
    md.write_text(
        "# Verifier Is Not Recovery Test\n\n"
        "**diagnostic_assumption**: capability fields are generated by this script from prior summaries.\n\n"
        "**not_empirical_model_measurement**: true\n\n"
        "**exclude_from_formal_success_summaries**: true\n\n"
        f"Source: `{summary_path}`\n\n"
        "## Metrics\n\n"
        "```json\n" + json.dumps(metrics, indent=2) + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps(metrics, indent=2))
    print("out_dir", out_dir)


if __name__ == "__main__":
    main()
