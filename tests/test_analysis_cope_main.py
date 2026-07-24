from __future__ import annotations

from tools.analyze_cope_main_comparison import exact_mcnemar, holm_adjust, task_cluster_bootstrap


def rows() -> list[dict]:
    result = []
    outcomes = {
        "p0": {"cope_patch": True, "history_augmented_full_regeneration": False},
        "p1": {"cope_patch": True, "history_augmented_full_regeneration": False},
        "p2": {"cope_patch": False, "history_augmented_full_regeneration": True},
        "p3": {"cope_patch": True, "history_augmented_full_regeneration": True},
    }
    for pair_index, (pair_key, pair_outcomes) in enumerate(outcomes.items()):
        for method, success in pair_outcomes.items():
            result.append(
                {
                    "pair_key": pair_key,
                    "task_id": pair_index // 2,
                    "method": method,
                    "success": success,
                }
            )
    return result


def test_exact_mcnemar_uses_only_discordant_pairs() -> None:
    result = exact_mcnemar(rows(), "cope_patch", "history_augmented_full_regeneration")
    assert result["complete_pairs"] == 4
    assert result["a_success_b_failure"] == 2
    assert result["a_failure_b_success"] == 1
    assert 0.0 <= result["exact_two_sided_p"] <= 1.0


def test_holm_adjustment_is_monotone_and_not_smaller_than_raw_p() -> None:
    tests = [
        {"exact_two_sided_p": 0.01},
        {"exact_two_sided_p": 0.03},
        {"exact_two_sided_p": 0.20},
    ]
    adjusted = holm_adjust(tests)
    assert all(item["holm_adjusted_p"] >= item["exact_two_sided_p"] for item in adjusted)


def test_task_cluster_bootstrap_is_reproducible() -> None:
    statistic = lambda values: sum(bool(row["success"]) for row in values) / len(values)
    first = task_cluster_bootstrap(rows(), statistic, samples=100, seed=7)
    second = task_cluster_bootstrap(rows(), statistic, samples=100, seed=7)
    assert first == second
    assert first["ci95"][0] <= first["estimate"] <= first["ci95"][1]
