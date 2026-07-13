import json
from pathlib import Path

from libero_dashboard import run_mock_smoke


def test_run_mock_smoke_creates_parseable_outputs(tmp_path):
    result = run_mock_smoke(str(tmp_path))
    assert result["ok"] is True
    run_dir = Path(result["last_run_dir"])
    assert run_dir.exists()
    required = ["run_config.json", "events.jsonl", "episode_summary.json", "raw.mp4", "annotated.mp4"]
    for name in required:
        assert (run_dir / name).exists()
        assert (run_dir / name).stat().st_size > 0

    config = json.loads((run_dir / "run_config.json").read_text())
    summary = json.loads((run_dir / "episode_summary.json").read_text())
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines() if line.strip()]
    assert config["interactive"] is True
    assert config["formal_run"] is False
    assert summary["interactive"] is True
    assert summary["formal_run"] is False
    assert summary["manual_intervention"] is True
    assert any(event["event"] == "manual_stop" for event in events)
    assert all("timestamp" in event and "step" in event and "event" in event for event in events)
    assert "manual_stop" in result["manual_events"]
