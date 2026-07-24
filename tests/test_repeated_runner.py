from __future__ import annotations

import json

from experiments.repeated_interruptions import _already_complete


def test_resume_only_skips_episode_with_matching_config_and_schedule(tmp_path) -> None:
    path = tmp_path / "episode.json"
    path.write_text(
        json.dumps(
            {
                "complete": True,
                "phase": "correctness",
                "event_schedule_hash": "schedule-a",
                "provenance": {"config_hash": "config-a"},
            }
        )
    )
    assert _already_complete(
        path,
        expected_config_hash="config-a",
        expected_schedule_hash="schedule-a",
    )
    assert not _already_complete(
        path,
        expected_config_hash="config-b",
        expected_schedule_hash="schedule-a",
    )
    assert not _already_complete(
        path,
        expected_config_hash="config-a",
        expected_schedule_hash="schedule-b",
    )
