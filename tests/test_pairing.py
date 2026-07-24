from __future__ import annotations

from pathlib import Path

import pytest

from cope.config import load_comparison_config
from cope.pairing import load_atlas, select_pairs, validate_formal_atlas


ROOT = Path(__file__).resolve().parents[1]


def test_config_locks_pilot_formal_and_detected_sizes() -> None:
    config = load_comparison_config(ROOT / "configs/cope_main_comparison_v1.yaml")
    assert config.pilot.pair_count == 4
    assert config.formal.pair_count == 120
    assert config.detected.pair_count == 30
    assert len(config.methods) == 6


def test_fixture_atlas_has_stable_unique_pilot_keys() -> None:
    atlas = load_atlas(ROOT / "tests/fixtures/disturbance_atlas_v1.fixture.jsonl")
    selected = select_pairs(
        atlas.pairs,
        task_ids=(1, 3),
        initial_state_ids=(0, 1),
        seeds=(7,),
    )
    assert len(selected) == 4
    assert len({pair.pair_key for pair in selected}) == 4
    assert all(pair.pair_key == pair.expected_pair_key for pair in selected)


def test_fixture_atlas_is_never_formal_ready() -> None:
    atlas = load_atlas(ROOT / "tests/fixtures/disturbance_atlas_v1.fixture.jsonl")
    errors = validate_formal_atlas(atlas)
    assert any("fixtures" in error for error in errors)
    assert any("source_branch" in error for error in errors)
    assert any("git commit" in error for error in errors)


def test_incomplete_cartesian_selection_is_rejected() -> None:
    atlas = load_atlas(ROOT / "tests/fixtures/disturbance_atlas_v1.fixture.jsonl")
    with pytest.raises(ValueError, match="complete Cartesian"):
        select_pairs(
            atlas.pairs[:-1],
            task_ids=(1, 3),
            initial_state_ids=(0, 1),
            seeds=(7,),
        )
