from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "analyze_sequential_formal", ROOT / "tools" / "analyze_sequential_formal.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_exact_mcnemar_known_all_discordant_result():
    assert MODULE.exact_mcnemar(10, 0) == 0.001953125
    assert MODULE.exact_mcnemar(0, 10) == 0.001953125
    assert MODULE.exact_mcnemar(0, 0) == 1.0


def test_clopper_pearson_and_odds_cover_boundaries():
    low, high = MODULE.clopper_pearson(10, 10)
    assert 0.69 < low < 0.70
    assert high == 1.0
    assert MODULE.odds(0.0) == 0.0
    assert MODULE.odds(1.0) == float("inf")


def test_holm_is_monotone_and_familywise_adjusted():
    adjusted = MODULE.holm({"a": 0.01, "b": 0.04})
    assert adjusted == {"a": 0.02, "b": 0.04}
