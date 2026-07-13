import json

import numpy as np

from libero_mock_backend import MockBackend, MockRunConfig, SimpleVideoRecorder, json_safe


def test_mock_frames_are_dynamic_and_identifiable():
    backend = MockBackend(load_delay=0.0)
    backend.load_model()
    cfg = MockRunConfig(max_steps=8, success_step=6, step_delay=0.0)
    info = backend.start_episode(cfg)
    result = backend.step(cfg, policy_step=0)
    assert info["frame"].shape == (cfg.frame_size, cfg.frame_size, 3)
    assert result.raw_frame.shape == (cfg.frame_size, cfg.frame_size, 3)
    assert not np.array_equal(info["frame"], result.raw_frame)
    assert len(result.raw_action) == 7
    assert len(result.env_action) == 7


def test_manual_disturbance_switches_structured_prompt_once():
    backend = MockBackend(load_delay=0.0)
    backend.load_model()
    cfg = MockRunConfig(
        mode="structured_relocalize_prompt",
        enable_auto_disturbance=False,
        allow_multiple_disturbances=False,
    )
    backend.start_episode(cfg)
    original = backend.current_prompt
    disturbance = backend.apply_disturbance(cfg, policy_step=3, source="manual_ui", target_joint="auto", dx=0.1, dy=0.0)
    skipped = backend.apply_disturbance(cfg, policy_step=4, source="manual_ui", target_joint="auto", dx=0.1, dy=0.0)
    assert disturbance["applied"] is True
    assert disturbance["prompt_changed"] is True
    assert backend.current_prompt != original
    assert backend.current_prompt.startswith("relocalize the")
    assert skipped["applied"] is False
    assert backend.disturbance_count == 1


def test_failure_and_timeout_outcomes():
    backend = MockBackend(load_delay=0.0)
    backend.load_model()
    failure_cfg = MockRunConfig(mock_outcome="failure", failure_step=2, step_delay=0.0)
    backend.start_episode(failure_cfg)
    first = backend.step(failure_cfg, policy_step=0)
    second = backend.step(failure_cfg, policy_step=1)
    assert first.done is False
    assert second.done is True
    assert second.success is False
    assert second.termination_reason == "mock_failure"

    timeout_cfg = MockRunConfig(mock_outcome="timeout", max_steps=2, step_delay=0.0)
    backend.start_episode(timeout_cfg)
    backend.step(timeout_cfg, policy_step=0)
    timeout = backend.step(timeout_cfg, policy_step=1)
    assert timeout.done is True
    assert timeout.termination_reason == "timeout"


def test_video_recorder_generates_files(tmp_path):
    raw = tmp_path / "raw.mp4"
    annotated = tmp_path / "annotated.mp4"
    recorder = SimpleVideoRecorder(raw, annotated, fps=5)
    frame = np.zeros((128, 128, 3), dtype=np.uint8)
    frame[:, :, 0] = 127
    recorder.append(frame, frame)
    info = recorder.close()
    assert raw.exists()
    assert annotated.exists()
    assert raw.stat().st_size > 0
    assert annotated.stat().st_size > 0
    assert info["frame_count"] == 1


def test_json_safe_converts_numpy():
    payload = {"array": np.array([1, 2]), "scalar": np.float32(0.5), "items": {3, 1}}
    safe = json_safe(payload)
    assert safe["array"] == [1, 2]
    assert isinstance(safe["scalar"], float)
    json.dumps(safe)
