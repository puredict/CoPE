"""Randomized paired benchmark: scenes, runner, statistics."""

from .scenes import (
    CONDITIONS, FAMILIES, SEVERITIES, EpisodeSpec, episode_grid, sample_scene,
)
from .runner import EpisodeRecord, run_episode, run_grid
from .statistics import (
    ProportionSummary, holm_correction, mcnemar_exact,
    paired_bootstrap_diff, wilson_interval,
)

__all__ = [
    "CONDITIONS", "FAMILIES", "SEVERITIES", "EpisodeSpec", "episode_grid",
    "sample_scene", "EpisodeRecord", "run_episode", "run_grid",
    "ProportionSummary", "holm_correction", "mcnemar_exact",
    "paired_bootstrap_diff", "wilson_interval",
]
