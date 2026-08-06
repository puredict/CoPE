from __future__ import annotations

from tools.analyze_repeated_interruptions import analyze


def _formal_records():
    records = []
    for task_id in (0, 1, 4, 8):
        for count in range(4):
            pair_key = f"task{task_id}-count{count}"
            for method in ("history_augmented_full_regeneration", "cope_patch"):
                records.append(
                    {
                        "pair_key": pair_key,
                        "pair_fields": {
                            "task_suite": "libero_10",
                            "task_id": task_id,
                            "interruption_count": count,
                        },
                        "method": method,
                        "provider": "real_openvla_adapter",
                        "evidence_admissibility": "formal",
                        "manual_intervention": False,
                        "timeout": False,
                        "success": (
                            count == 0
                            or (method == "cope_patch" and count <= 2)
                        ),
                        "event_schedule_hash": f"schedule-{pair_key}",
                        "provenance": {
                            "runtime_commit": "a" * 40,
                            "checkpoint": "openvla/checkpoint",
                        },
                        "metrics": {
                            "progress_preservation": 0.9 if method == "cope_patch" else 0.7,
                            "unaffected_constraint_survival": 0.98,
                            "preference_violation_rate": 0.0,
                            "safety_violation_rate": 0.0,
                            "silent_commitment_loss_rate": (
                                0.05 if method == "cope_patch" else 0.2
                            ),
                        },
                    }
                )
    return records


def test_analysis_computes_curves_bootstrap_and_paired_tests_for_valid_formal_records() -> None:
    summary = analyze(_formal_records(), bootstrap_replicates=20)
    assert summary["status"] == "complete"
    assert summary["episodes"] == 32
    assert summary["pairs"] == 16
    assert summary["success_curves"]["cope_patch"]["auc"] > summary["success_curves"][
        "history_augmented_full_regeneration"
    ]["auc"]
    assert summary["task_clustered_bootstrap"]["replicates"] == 20
    assert summary["paired_success_test"]["cope_only_success"] > 0


def test_analysis_rejects_correctness_noop_records() -> None:
    record = _formal_records()[0]
    record["evidence_admissibility"] = "benchmark_correctness_only_not_policy_evidence"
    record["provider"] = "scripted_noop_correctness_only"
    summary = analyze([record], bootstrap_replicates=5)
    assert summary["status"] == "rejected"
    assert summary["no_statistics_reported"] is True
