"""Preregisterable paired statistics for repeated-interruption master sessions.

The caller MUST verify raw result-cell integrity before building these mappings:
duplicates already collapsed into a dict cannot be recovered here. A key denotes
one complete ``task + initial state + policy seed + master schedule`` session,
never an event. There is no complete-case deletion or imputation in this module.

Bootstrap conventions are fixed: stdlib ``random.Random(seed).randrange(n)``,
lexicographically sorted master IDs, n draws with replacement per replicate,
shared draws for both arms and every checkpoint, and percentile intervals with
linear interpolation (Hyndman--Fan type 7). Results are on the success-probability
scale, not odds or log odds. The slope fallback is unweighted OLS against
``log2(K+1)`` and must be selected before looking at formal outcomes; this module
does not silently attempt or select between statistical models.

References:
* Wilson score: https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm
* Exact McNemar (conditional binomial, no mid-p or chi-square approximation):
  https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html
* Paired percentile resampling semantics:
  https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from numbers import Integral, Real
import random
from statistics import NormalDist
from typing import Any


DEFAULT_SEED = 20260906
DEFAULT_REPLICATES = 10_000
NONINFERIORITY_MARGIN = -0.05
SLOPE_ANALYSIS = "preregistered_paired_master_session_bootstrap_ols_log2_k_plus_1"
REGISTERED_CHECKPOINTS = ((0, 1, 2, 4), (0, 1, 2, 4, 8))


class StatisticsInputError(ValueError):
    """Analysis input is incomplete, unpaired, nonbinary, or otherwise invalid."""


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
        raise StatisticsInputError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _probability(value: Any, name: str, *, interior: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise StatisticsInputError(f"{name} must be a finite probability")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise StatisticsInputError(f"{name} must be a finite probability")
    if interior and not 0 < result < 1:
        raise StatisticsInputError(f"{name} must be strictly between 0 and 1")
    return result


def _binary(value: Any, name: str) -> int:
    if isinstance(value, bool):
        return int(value)
    if not isinstance(value, Real) or not math.isfinite(float(value)) or value not in (0, 1):
        raise StatisticsInputError(f"{name} must be binary 0/1 or bool; got {value!r}")
    return int(value)


def _settings(replicates: int, seed: int, confidence: float) -> tuple[int, int, float]:
    return (
        _integer(replicates, "replicates", minimum=2),
        _integer(seed, "seed"),
        _probability(confidence, "confidence", interior=True),
    )


def _paired_ids(a: Mapping[str, Any], b: Mapping[str, Any]) -> tuple[str, ...]:
    for name, values in (("treatment", a), ("comparator", b)):
        if not isinstance(values, Mapping) or not values:
            raise StatisticsInputError(f"{name} must be a nonempty master-session mapping")
        if any(not isinstance(key, str) or not key.strip() for key in values):
            raise StatisticsInputError(f"{name} master-session IDs must be nonempty strings")
    if set(a) != set(b):
        raise StatisticsInputError(
            "unpaired master-session IDs: "
            f"treatment-only={sorted(set(a) - set(b))}; "
            f"comparator-only={sorted(set(b) - set(a))}"
        )
    return tuple(sorted(a))


def _paired_values(
    a: Mapping[str, Any], b: Mapping[str, Any]
) -> tuple[tuple[str, ...], list[int], list[int]]:
    ids = _paired_ids(a, b)
    return (
        ids,
        [_binary(a[key], f"treatment[{key}]") for key in ids],
        [_binary(b[key], f"comparator[{key}]") for key in ids],
    )


def _percentile(values: Sequence[float], probability: float) -> float:
    """Linear empirical quantile; the caller supplies a nonempty finite sample."""
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    # E.g. 100*(1-.95) is 5.000000000000004 in binary arithmetic. Avoid
    # manufacturing movement across the fixed NI boundary at an exact rank.
    nearest = round(index)
    if math.isclose(index, nearest, rel_tol=0, abs_tol=4 * math.ulp(index)):
        index = float(nearest)
    lower = math.floor(index)
    upper = math.ceil(index)
    return ordered[lower] + (index - lower) * (ordered[upper] - ordered[lower])


def _interval(values: Sequence[float], confidence: float) -> tuple[float, float]:
    alpha = 1 - confidence
    return _percentile(values, alpha / 2), _percentile(values, 1 - alpha / 2)


def wilson_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    """Two-sided Wilson score interval with no continuity correction.

    ``total`` is a count of master sessions at one checkpoint, never event cells.
    """
    successes = _integer(successes, "successes")
    total = _integer(total, "total", minimum=1)
    confidence = _probability(confidence, "confidence", interior=True)
    if successes > total:
        raise StatisticsInputError("successes cannot exceed total")
    z = -NormalDist().inv_cdf((1 - confidence) / 2)
    z2 = z * z
    p = successes / total
    denominator = 1 + z2 / total
    center = (p + z2 / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z2 / (4 * total * total)) / denominator
    lower = 0.0 if successes == 0 else max(0.0, center - radius)
    upper = 1.0 if successes == total else min(1.0, center + radius)
    return lower, upper


def exact_mcnemar(treatment_only: int, comparator_only: int) -> float:
    """Exact two-sided conditional McNemar p = min(1, 2*BinomCDF(min(b,c);b+c,.5)).

    The two inputs count discordant master sessions. No discordance gives p=1.
    Integer binomial sums avoid cancellation, underflow in recurrence terms, and
    normal approximations; only the final exact rational is converted to a float.
    """
    b = _integer(treatment_only, "treatment_only")
    c = _integer(comparator_only, "comparator_only")
    n, k = b + c, min(b, c)
    if n == 0 or 2 * k >= n - 1:
        return 1.0
    term = 1
    cumulative = 1
    for j in range(1, k + 1):
        term = term * (n - j + 1) // j
        cumulative += term
    return min(1.0, (2 * cumulative) / (1 << n))


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    """Holm step-down familywise adjustment; pass ONLY prespecified secondary tests.

    The singular preregistered primary test is kept outside this family. Missing or
    nonfinite p-values are errors rather than silently shrinking the testing family.
    An empty family is invalid; callers with no secondary tests should skip the call.
    """
    if not isinstance(p_values, Mapping) or not p_values:
        raise StatisticsInputError("p_values must be a nonempty named testing family")
    if any(not isinstance(key, str) or not key.strip() for key in p_values):
        raise StatisticsInputError("test names must be nonempty strings")
    checked = {name: _probability(p, f"p[{name}]") for name, p in p_values.items()}
    ordered = sorted(checked, key=lambda key: (checked[key], key))
    adjusted: dict[str, float] = {}
    previous = 0.0
    for rank, name in enumerate(ordered):
        previous = max(previous, min(1.0, (len(ordered) - rank) * checked[name]))
        adjusted[name] = previous
    return {name: adjusted[name] for name in p_values}


def _point_summary(a: Sequence[int], b: Sequence[int], confidence: float) -> dict[str, Any]:
    n = len(a)
    a_count, b_count = sum(a), sum(b)
    a_only = sum(x == 1 and y == 0 for x, y in zip(a, b))
    b_only = sum(x == 0 and y == 1 for x, y in zip(a, b))
    both_success = sum(x == 1 and y == 1 for x, y in zip(a, b))
    both_failure = n - a_only - b_only - both_success
    a_wilson, b_wilson = wilson_interval(a_count, n, confidence), wilson_interval(b_count, n, confidence)
    return {
        "n_pairs": n,
        "experimental_unit": "master_session",
        "treatment_successes": a_count,
        "comparator_successes": b_count,
        "treatment_rate": a_count / n,
        "comparator_rate": b_count / n,
        "risk_difference": (a_count - b_count) / n,
        "treatment_wilson_lower": a_wilson[0],
        "treatment_wilson_upper": a_wilson[1],
        "comparator_wilson_lower": b_wilson[0],
        "comparator_wilson_upper": b_wilson[1],
        "discordant_treatment_only": a_only,
        "discordant_comparator_only": b_only,
        "both_success": both_success,
        "both_failure": both_failure,
        "mcnemar_p": exact_mcnemar(a_only, b_only),
    }


def _bootstrap_metadata(replicates: int, seed: int, confidence: float) -> dict[str, Any]:
    return {
        "replicates": replicates,
        "seed": seed,
        "confidence": confidence,
        "interval_method": "percentile_linear_type7",
        "random_algorithm": "python_random_mt19937_randrange",
        "resampling_unit": "master_session",
        "paired": True,
        "shared_checkpoint_indices": True,
        "session_order": "lexicographic_master_session_id",
    }


def _difference_bootstrap(
    a: Sequence[int], b: Sequence[int], replicates: int, seed: int
) -> list[float]:
    n = len(a)
    delta = [x - y for x, y in zip(a, b)]
    rng = random.Random(seed)
    return [sum(delta[rng.randrange(n)] for _ in range(n)) / n for _ in range(replicates)]


def paired_risk_difference(
    treatment: Mapping[str, Any],
    comparator: Mapping[str, Any],
    *,
    replicates: int = DEFAULT_REPLICATES,
    seed: int = DEFAULT_SEED,
    confidence: float = 0.95,
    include_bootstrap_samples: bool = False,
) -> dict[str, Any]:
    """Compare binary success for paired master sessions at one fixed checkpoint."""
    replicates, seed, confidence = _settings(replicates, seed, confidence)
    _, a, b = _paired_values(treatment, comparator)
    samples = _difference_bootstrap(a, b, replicates, seed)
    lower, upper = _interval(samples, confidence)
    result = {
        **_point_summary(a, b, confidence),
        "ci_lower": lower,
        "ci_upper": upper,
        "bootstrap_degenerate": min(samples) == max(samples),
        "bootstrap": _bootstrap_metadata(replicates, seed, confidence),
    }
    if include_bootstrap_samples:
        result["bootstrap_samples"] = samples
    return result


def noninferiority(
    cope: Mapping[str, Any],
    generic: Mapping[str, Any],
    *,
    replicates: int = DEFAULT_REPLICATES,
    seed: int = DEFAULT_SEED,
    confidence: float = 0.95,
    margin: float = NONINFERIORITY_MARGIN,
    include_bootstrap_samples: bool = False,
) -> dict[str, Any]:
    """CoPE-minus-generic NI using a one-sided lower percentile bootstrap bound.

    NI requires the lower bound to be STRICTLY above the frozen -0.05 probability
    margin. The bounded parameter-space upper limit is +1. This is not a two-sided
    95% bound, an equivalence test, or a semantic-superiority test. A bootstrap may
    be degenerate when all observed paired differences are equal; that is reported,
    not repaired with fabricated observations or silently changed intervals.
    """
    replicates, seed, confidence = _settings(replicates, seed, confidence)
    if isinstance(margin, bool) or not isinstance(margin, Real) or margin != NONINFERIORITY_MARGIN:
        raise StatisticsInputError("CoPE non-inferiority margin is preregistered at -0.05")
    _, a, b = _paired_values(cope, generic)
    samples = _difference_bootstrap(a, b, replicates, seed)
    lower = _percentile(samples, 1 - confidence)
    result = {
        **_point_summary(a, b, confidence),
        "contrast": "cope_minus_generic",
        "margin": NONINFERIORITY_MARGIN,
        "confidence": confidence,
        "sidedness": "one_sided_lower",
        "ci_lower": lower,
        "ci_upper": 1.0,
        "noninferior": lower > NONINFERIORITY_MARGIN,
        "bootstrap_degenerate": min(samples) == max(samples),
        "bootstrap": _bootstrap_metadata(replicates, seed, confidence),
    }
    if include_bootstrap_samples:
        result["bootstrap_samples"] = samples
    return result


def master_session_cluster_bootstrap(
    treatment: Mapping[str, Mapping[int, Any]],
    comparator: Mapping[str, Mapping[int, Any]],
    *,
    checkpoints: Sequence[int] = (0, 1, 2, 4),
    replicates: int = DEFAULT_REPLICATES,
    seed: int = DEFAULT_SEED,
    confidence: float = 0.95,
    include_bootstrap_samples: bool = False,
) -> dict[str, Any]:
    """Paired success curves and preregistered bootstrap degradation-slope fallback.

    Each input is ``{master_session_id: {K: binary_success}}`` on exactly one of the
    two registered grids. Every session must have every checkpoint in both arms.
    The entire session is sampled once per draw: both methods and all checkpoints
    travel together. Checkpoint intervals are pointwise, not simultaneous bands.

    OLS slopes are changes in success probability per unit log2(K+1), with each
    checkpoint and each master session equally weighted. A positive treatment-minus-
    comparator slope difference means less decline/more increase; ``flatter_supported``
    requires its paired two-sided CI lower bound > 0. This does not itself establish
    the full runtime claim. No mixed-model convergence claim is made by this function.
    """
    replicates, seed, confidence = _settings(replicates, seed, confidence)
    if isinstance(checkpoints, (str, bytes)) or not isinstance(checkpoints, Sequence):
        raise StatisticsInputError("checkpoints must be a registered ordered sequence")
    ks = tuple(_integer(k, "checkpoint") for k in checkpoints)
    if ks not in REGISTERED_CHECKPOINTS:
        raise StatisticsInputError(f"checkpoint grid must be one of {REGISTERED_CHECKPOINTS}")
    ids = _paired_ids(treatment, comparator)
    a: list[list[int]] = []
    b: list[list[int]] = []
    for name, values, rows in (("treatment", treatment, a), ("comparator", comparator, b)):
        for session_id in ids:
            row = values[session_id]
            if not isinstance(row, Mapping):
                raise StatisticsInputError(f"{name}[{session_id}] must map checkpoints to success")
            if any(isinstance(k, bool) or not isinstance(k, Integral) for k in row) or set(row) != set(ks):
                raise StatisticsInputError(f"{name}[{session_id}] must have exactly checkpoints {ks}")
            rows.append([_binary(row[k], f"{name}[{session_id}][{k}]") for k in ks])
    n = len(ids)
    x = [math.log2(k + 1) for k in ks]
    x_mean = math.fsum(x) / len(x)
    centered = [value - x_mean for value in x]
    denominator = math.fsum(value * value for value in centered)

    def slope(row: Sequence[float]) -> float:
        # Centering y makes constant success curves exactly zero even with roundoff.
        mean = math.fsum(row) / len(row)
        return math.fsum(weight * (value - mean) for weight, value in zip(centered, row)) / denominator

    a_slopes = [slope(row) for row in a]
    b_slopes = [slope(row) for row in b]
    slope_deltas = [left - right for left, right in zip(a_slopes, b_slopes)]
    columns_a = [[row[j] for row in a] for j in range(len(ks))]
    columns_b = [[row[j] for row in b] for j in range(len(ks))]
    deltas = [[left - right for left, right in zip(ca, cb)] for ca, cb in zip(columns_a, columns_b)]
    checkpoint_samples: list[list[float]] = [[] for _ in ks]
    samples_a: list[float] = []
    samples_b: list[float] = []
    samples_delta: list[float] = []
    rng = random.Random(seed)
    for _ in range(replicates):
        indices = [rng.randrange(n) for _ in range(n)]
        for column, samples in zip(deltas, checkpoint_samples):
            samples.append(sum(column[index] for index in indices) / n)
        samples_a.append(math.fsum(a_slopes[index] for index in indices) / n)
        samples_b.append(math.fsum(b_slopes[index] for index in indices) / n)
        samples_delta.append(math.fsum(slope_deltas[index] for index in indices) / n)
    rows = []
    for k, column_a, column_b, samples in zip(ks, columns_a, columns_b, checkpoint_samples):
        lower, upper = _interval(samples, confidence)
        rows.append({
            "checkpoint": k,
            **_point_summary(column_a, column_b, confidence),
            "ci_lower": lower,
            "ci_upper": upper,
            "bootstrap_degenerate": min(samples) == max(samples),
            "interval_scope": "pointwise",
        })
    a_lower, a_upper = _interval(samples_a, confidence)
    b_lower, b_upper = _interval(samples_b, confidence)
    delta_lower, delta_upper = _interval(samples_delta, confidence)
    result = {
        "n_master_sessions": n,
        "experimental_unit": "master_session",
        "checkpoints": rows,
        "bootstrap": _bootstrap_metadata(replicates, seed, confidence),
        "slopes": {
            "analysis": SLOPE_ANALYSIS,
            "scale": "success_probability_per_log2_k_plus_1",
            "treatment_slope": math.fsum(a_slopes) / n,
            "comparator_slope": math.fsum(b_slopes) / n,
            "difference": math.fsum(slope_deltas) / n,
            "treatment_ci_lower": a_lower,
            "treatment_ci_upper": a_upper,
            "comparator_ci_lower": b_lower,
            "comparator_ci_upper": b_upper,
            "ci_lower": delta_lower,
            "ci_upper": delta_upper,
            "flatter_supported": delta_lower > 0,
            "n_master_sessions": n,
        },
    }
    if include_bootstrap_samples:
        result["bootstrap_samples"] = {
            "checkpoint_risk_differences": {str(k): samples for k, samples in zip(ks, checkpoint_samples)},
            "treatment_slopes": samples_a,
            "comparator_slopes": samples_b,
            "slope_differences": samples_delta,
        }
    return result
