from __future__ import annotations

from pathlib import Path

from cope.config import load_comparison_config
from cope.pairing import load_atlas
from cope.providers.fake import DeterministicFakeProvider
from cope.runner import ComparisonRunner
from cope.validation import read_jsonl
from tests.fakes import FakeComparisonBackend, create_fake_engine


ROOT = Path(__file__).resolve().parents[1]


def make_runner(output_dir: Path, backend: FakeComparisonBackend) -> ComparisonRunner:
    config = load_comparison_config(ROOT / "configs/cope_main_comparison_v1.yaml")
    atlas = load_atlas(ROOT / "tests/fixtures/disturbance_atlas_v1.fixture.jsonl")
    provider = backend.provider
    return ComparisonRunner(
        config=config,
        phase="pilot",
        event_source="oracle",
        manifest=atlas,
        provider=provider,
        engine_factory=create_fake_engine,
        backend=backend,
        repo_root=ROOT,
        output_dir=output_dir,
    )


def test_runner_writes_exactly_24_unique_pilot_episodes_and_resumes(tmp_path: Path) -> None:
    config = load_comparison_config(ROOT / "configs/cope_main_comparison_v1.yaml")
    provider = DeterministicFakeProvider(config.provider)
    first_backend = FakeComparisonBackend(config, provider)
    output_dir = tmp_path / "pilot"
    summary = make_runner(output_dir, first_backend).run()
    assert summary["complete"] is True
    assert summary["episode_count"] == 24
    rows = read_jsonl(output_dir / "episodes.jsonl")
    assert len(rows) == 24
    assert len({(row["pair_key"], row["method"]) for row in rows}) == 24
    assert len(first_backend.calls) == 24

    second_backend = FakeComparisonBackend(config, provider)
    resumed = make_runner(output_dir, second_backend).run(resume=True)
    assert resumed["complete"] is True
    assert len(second_backend.calls) == 0
    assert len(read_jsonl(output_dir / "episodes.jsonl")) == 24
