"""Numerical and dependence checks; fixtures are synthetic UNIT TESTS only."""

from __future__ import annotations

import math
import unittest

from cope_benchmark.repeated_v2.statistics import (
    StatisticsInputError,
    exact_mcnemar,
    holm_adjust,
    master_session_cluster_bootstrap,
    noninferiority,
    paired_risk_difference,
    wilson_interval,
)


def _mapping(values):
    return {f"master-{i:04d}": value for i, value in enumerate(values)}


class TestNumericalStatistics(unittest.TestCase):
    def test_wilson_known_values_and_extreme_counts(self):
        lower, upper = wilson_interval(5, 10)
        self.assertAlmostEqual(lower, 0.236593090512564, places=13)
        self.assertAlmostEqual(upper, 0.763406909487436, places=13)
        self.assertEqual(wilson_interval(0, 10)[0], 0.0)
        self.assertAlmostEqual(wilson_interval(0, 10)[1], 0.2775327998628892)
        self.assertAlmostEqual(wilson_interval(10, 10)[0], 0.7224672001371107)
        self.assertEqual(wilson_interval(10, 10)[1], 1.0)

    def test_exact_mcnemar_known_values_symmetry_and_no_discordance(self):
        self.assertEqual(exact_mcnemar(0, 0), 1.0)
        self.assertEqual(exact_mcnemar(10, 0), 2 / 1024)
        self.assertEqual(exact_mcnemar(12, 2), 0.012939453125)
        self.assertEqual(exact_mcnemar(2, 12), 0.012939453125)
        self.assertEqual(exact_mcnemar(1000, 1000), 1.0)
        # Large n cannot start a float recurrence at 2**-n (which underflows).
        self.assertAlmostEqual(exact_mcnemar(550, 550), 1.0)
        self.assertGreater(exact_mcnemar(600, 500), 0.002)
        self.assertLess(exact_mcnemar(600, 500), 0.004)

    def test_holm_known_step_down_values_and_ties(self):
        observed = holm_adjust({"p1": 0.01, "p2": 0.04, "p3": 0.03, "p4": 0.9})
        self.assertEqual(observed, {"p1": 0.04, "p2": 0.09, "p3": 0.09, "p4": 0.9})
        self.assertEqual(holm_adjust({"a": 0.02, "b": 0.02, "c": 1}), {"a": 0.06, "b": 0.06, "c": 1.0})

    def test_paired_risk_difference_counts_and_identical_pairs(self):
        a, b = _mapping([1, 1, 0, 1]), _mapping([0, 0, 1, 1])
        result = paired_risk_difference(a, b, replicates=100, seed=7)
        self.assertEqual(result["n_pairs"], 4)
        self.assertEqual(result["risk_difference"], 0.25)
        self.assertEqual(result["discordant_treatment_only"], 2)
        self.assertEqual(result["discordant_comparator_only"], 1)
        self.assertEqual(result["both_success"], 1)
        self.assertEqual(result["both_failure"], 0)
        self.assertFalse(result["bootstrap_degenerate"])
        self.assertEqual(result["treatment_rate"], 0.75)
        self.assertEqual(result["comparator_rate"], 0.5)
        same = paired_risk_difference(a, a, replicates=100)
        self.assertEqual((same["risk_difference"], same["ci_lower"], same["ci_upper"]), (0.0, 0.0, 0.0))
        self.assertEqual((same["both_success"], same["both_failure"]), (3, 1))
        self.assertTrue(same["bootstrap_degenerate"])

    def test_full_paired_outcome_table(self):
        result = paired_risk_difference(_mapping([1, 1, 0, 0]), _mapping([1, 0, 1, 0]), replicates=100)
        cells = [result[key] for key in ("both_success", "discordant_treatment_only",
                                        "discordant_comparator_only", "both_failure")]
        self.assertEqual(cells, [1, 1, 1, 1])
        self.assertEqual(sum(cells), result["n_pairs"])
        self.assertEqual(result["risk_difference"], 0)
        self.assertFalse(result["bootstrap_degenerate"])

    def test_seed_and_mapping_order_are_deterministic(self):
        a, b = _mapping([1, 1, 0, 1]), _mapping([0, 0, 1, 1])
        kwargs = {"replicates": 100, "seed": 31, "include_bootstrap_samples": True}
        original = paired_risk_difference(a, b, **kwargs)
        reordered = paired_risk_difference(dict(reversed(list(a.items()))), dict(reversed(list(b.items()))), **kwargs)
        self.assertEqual(original, reordered)
        changed = paired_risk_difference(a, b, **{**kwargs, "seed": 32})
        self.assertNotEqual(original["bootstrap_samples"], changed["bootstrap_samples"])

    def test_noninferiority_uses_fifth_percentile_and_strict_margin(self):
        a, b = _mapping([1] * 100), _mapping([1] * 100)
        same = noninferiority(a, b, replicates=100)
        self.assertTrue(same["noninferior"])
        self.assertEqual(same["ci_lower"], 0)
        self.assertEqual(same["ci_upper"], 1)
        self.assertTrue(same["bootstrap_degenerate"])
        worse = noninferiority(_mapping([0] * 100), b, replicates=100)
        self.assertFalse(worse["noninferior"])
        self.assertEqual(worse["ci_lower"], -1)
        varied = noninferiority(_mapping([1] * 9 + [0] * 11), _mapping([1] * 6 + [0] * 14),
                               replicates=101, seed=3, include_bootstrap_samples=True)
        ordered = sorted(varied["bootstrap_samples"])
        self.assertAlmostEqual(varied["ci_lower"], ordered[5])
        # Constant -0.05 is impossible for individual binary differences; a
        # sample distribution whose 5th percentile is exactly -0.05 tests the boundary.
        boundary = noninferiority(_mapping([1] * 59 + [0]), _mapping([1] * 60), replicates=101, seed=1)
        self.assertEqual(boundary["ci_lower"], -0.05)
        self.assertFalse(boundary["noninferior"])


class TestMasterSessionDependence(unittest.TestCase):
    def test_checkpoints_share_indices_and_do_not_multiply_sample_size(self):
        checkpoints = (0, 1, 2, 4)
        a = {key: dict.fromkeys(checkpoints, value) for key, value in _mapping([0, 1, 0, 1]).items()}
        b = {key: dict.fromkeys(checkpoints, 0) for key in a}
        result = master_session_cluster_bootstrap(a, b, replicates=101, seed=9, include_bootstrap_samples=True)
        samples = result["bootstrap_samples"]["checkpoint_risk_differences"]
        self.assertEqual(samples["0"], samples["1"])
        self.assertEqual(samples["0"], samples["2"])
        self.assertEqual(samples["0"], samples["4"])
        self.assertGreater(len(set(samples["0"])), 1)
        self.assertEqual(result["n_master_sessions"], 4)
        self.assertTrue(all(row["n_pairs"] == 4 for row in result["checkpoints"]))
        self.assertTrue(all(row["both_success"] == 0 and row["both_failure"] == 2
                            and not row["bootstrap_degenerate"] for row in result["checkpoints"]))
        self.assertEqual(result["slopes"]["difference"], 0)
        self.assertEqual(result["bootstrap_samples"]["slope_differences"], [0.0] * 101)
        single = paired_risk_difference({k: v[4] for k, v in a.items()}, {k: v[4] for k, v in b.items()},
                                        replicates=101, seed=9, include_bootstrap_samples=True)
        self.assertEqual(samples["4"], single["bootstrap_samples"])

    def test_known_probability_scale_slope_and_paired_difference(self):
        checkpoints = (0, 1, 2, 4)
        a = {f"master-{i}": {0: 1, 1: 1, 2: 1, 4: 1} for i in range(4)}
        b = {key: {0: 1, 1: 1, 2: 0, 4: 0} for key in a}
        result = master_session_cluster_bootstrap(a, b, replicates=20, include_bootstrap_samples=True)
        xs = [math.log2(k + 1) for k in checkpoints]
        x_mean = sum(xs) / 4
        expected = ((xs[0] - x_mean) + (xs[1] - x_mean)) / sum((x - x_mean) ** 2 for x in xs)
        self.assertEqual(result["slopes"]["treatment_slope"], 0)
        self.assertAlmostEqual(result["slopes"]["comparator_slope"], expected)
        self.assertAlmostEqual(result["slopes"]["difference"], -expected)
        self.assertAlmostEqual(result["slopes"]["ci_lower"], -expected)
        self.assertAlmostEqual(result["slopes"]["ci_upper"], -expected)
        self.assertTrue(result["slopes"]["flatter_supported"])
        # Identical arms may vary across sessions/checkpoints, but paired deltas stay zero.
        equal = master_session_cluster_bootstrap(b, b, replicates=20)
        self.assertEqual(equal["slopes"]["difference"], 0)
        self.assertEqual(equal["slopes"]["ci_lower"], 0)
        self.assertFalse(equal["slopes"]["flatter_supported"])

    def test_eight_event_grid(self):
        ks = (0, 1, 2, 4, 8)
        a = {"one": dict.fromkeys(ks, 1), "two": dict.fromkeys(ks, 0)}
        result = master_session_cluster_bootstrap(a, a, checkpoints=ks, replicates=2)
        self.assertEqual([r["checkpoint"] for r in result["checkpoints"]], list(ks))
        self.assertEqual(result["n_master_sessions"], 2)

    def test_each_bootstrap_slope_matches_the_same_sampled_curve(self):
        ks = (0, 1, 2, 4)
        a = {"a": dict(zip(ks, [1, 1, 0, 1])), "b": dict(zip(ks, [0, 0, 0, 0])),
             "c": dict(zip(ks, [1, 1, 1, 1])), "d": dict(zip(ks, [1, 0, 1, 0]))}
        b = {"a": dict(zip(ks, [1, 0, 0, 0])), "b": dict(zip(ks, [1, 1, 1, 1])),
             "c": dict(zip(ks, [1, 0, 1, 0])), "d": dict(zip(ks, [0, 1, 0, 1]))}
        result = master_session_cluster_bootstrap(a, b, replicates=51, seed=13, include_bootstrap_samples=True)
        samples = result["bootstrap_samples"]
        xs = [math.log2(k + 1) for k in ks]
        x_mean = sum(xs) / len(xs)
        denominator = sum((x - x_mean) ** 2 for x in xs)
        for index, delta in enumerate(samples["slope_differences"]):
            ys = [samples["checkpoint_risk_differences"][str(k)][index] for k in ks]
            y_mean = sum(ys) / len(ys)
            expected = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
            self.assertAlmostEqual(delta, expected, places=14)
            self.assertAlmostEqual(delta, samples["treatment_slopes"][index] - samples["comparator_slopes"][index], places=14)
        same = master_session_cluster_bootstrap(a, a, replicates=51, seed=13, include_bootstrap_samples=True)
        self.assertGreater(len(set(same["bootstrap_samples"]["treatment_slopes"])), 1)
        self.assertEqual(same["bootstrap_samples"]["slope_differences"], [0.0] * 51)


class TestIntegrityRejection(unittest.TestCase):
    def test_reject_invalid_counts_and_probabilities(self):
        for successes, total in ((0, 0), (-1, 1), (2, 1), (1.0, 2), (True, 2)):
            with self.subTest(successes=successes, total=total), self.assertRaises(StatisticsInputError):
                wilson_interval(successes, total)
        for value in (float("nan"), float("inf"), -0.01, 1.01, "0.1", True):
            with self.subTest(value=value), self.assertRaises(StatisticsInputError):
                holm_adjust({"a": value})
        for a, b in ((-1, 1), (1.2, 3), (True, 2)):
            with self.assertRaises(StatisticsInputError):
                exact_mcnemar(a, b)
        with self.assertRaises(StatisticsInputError):
            holm_adjust({})

    def test_reject_empty_unpaired_and_nonbinary_sessions(self):
        for a, b in (({}, {}), ({"a": 1}, {"b": 0}), ({1: 1}, {1: 0}), ({"": 1}, {"": 0}), ([], [])):
            with self.subTest(a=a, b=b), self.assertRaises(StatisticsInputError):
                paired_risk_difference(a, b, replicates=2)
        for value in (None, "1", -1, 2, 0.5, float("nan"), float("inf"), [1]):
            with self.subTest(value=value), self.assertRaises(StatisticsInputError):
                paired_risk_difference({"a": value}, {"a": 0}, replicates=2)

    def test_reject_invalid_bootstrap_settings_and_changed_ni_margin(self):
        for kwargs in ({"replicates": 1}, {"replicates": 2.5}, {"seed": -1}, {"seed": True},
                       {"confidence": 0}, {"confidence": 1}, {"confidence": float("nan")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(StatisticsInputError):
                paired_risk_difference({"a": 1}, {"a": 1}, **kwargs)
        with self.assertRaises(StatisticsInputError):
            noninferiority({"a": 1}, {"a": 1}, replicates=2, margin=-0.10)

    def test_reject_missing_extra_invalid_or_unregistered_checkpoints(self):
        valid = {"one": {0: 1, 1: 1, 2: 0, 4: 0}}
        for row in ({0: 1, 1: 1, 4: 0}, {0: 1, 1: 1, 2: 0, 4: 0, 8: 0},
                    {False: 1, 1: 1, 2: 0, 4: 0}, {0: 1, 1: 1, 2: None, 4: 0}, {"0": 1}, [1, 1, 0, 0]):
            with self.subTest(row=row), self.assertRaises(StatisticsInputError):
                master_session_cluster_bootstrap({"one": row}, valid, replicates=2)
        for ks in ((0, 1, 4), (0, 2, 1, 4), (0, 1, 2, 2, 4), (0, True, 2, 4), "0124"):
            with self.subTest(ks=ks), self.assertRaises(StatisticsInputError):
                master_session_cluster_bootstrap(valid, valid, checkpoints=ks, replicates=2)


if __name__ == "__main__":
    unittest.main()
