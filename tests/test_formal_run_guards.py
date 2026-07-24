from __future__ import annotations

from pathlib import Path

from cope.config import load_comparison_config
from cope.pairing import load_atlas
from cope.providers.fake import DeterministicFakeProvider
from cope.runner import readiness_report
from tests.fakes import FakeComparisonBackend, create_fake_engine


ROOT = Path(__file__).resolve().parents[1]


def test_formal_readiness_rejects_fake_provider_engine_manifest_and_backend() -> None:
    config = load_comparison_config(ROOT / "configs/cope_main_comparison_v1.yaml")
    atlas = load_atlas(ROOT / "tests/fixtures/disturbance_atlas_v1.fixture.jsonl")
    provider = DeterministicFakeProvider(config.provider)
    backend = FakeComparisonBackend(config, provider)
    report = readiness_report(
        config=config,
        phase="formal",
        event_source="oracle",
        manifest=atlas,
        provider=provider,
        engine_factory=create_fake_engine,
        backend=backend,
        repo_root=ROOT,
        allow_test_fixtures=True,
    )
    assert not report["ready"]
    blockers = "\n".join(report["blockers"])
    assert "fake provider" in blockers
    assert "formal atlas" in blockers
    assert "metadata.is_fake=false" in blockers
    assert "not formal-capable" in blockers
    assert "checkpoint.sha256" in blockers


def test_pilot_fixture_readiness_still_reports_missing_local_runtime() -> None:
    config = load_comparison_config(ROOT / "configs/cope_main_comparison_v1.yaml")
    atlas = load_atlas(ROOT / "tests/fixtures/disturbance_atlas_v1.fixture.jsonl")
    provider = DeterministicFakeProvider(config.provider)
    backend = FakeComparisonBackend(config, provider)
    report = readiness_report(
        config=config,
        phase="pilot",
        event_source="oracle",
        manifest=atlas,
        provider=provider,
        engine_factory=create_fake_engine,
        backend=backend,
        repo_root=ROOT,
        allow_test_fixtures=True,
    )
    assert report["selected_pair_count"] == 4
    assert report["scheduled_episode_count"] == 24
    blockers = "\n".join(report["blockers"])
    assert "fake provider" in blockers
    assert "metadata.is_fake=false" in blockers
    assert "not formal-capable" in blockers
    assert "checkpoint.sha256" in blockers
