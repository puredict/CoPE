"""Event detector / noise-model / relocation tests."""

from __future__ import annotations

import numpy as np

from rekep_repair.events.detector import EventDetector, NoiseModel
from rekep_repair.events.event import EventType
from rekep_repair.execution.context import ExecutionContext
from rekep_repair.synthetic.dynamics import Obstacle, SceneConfig
from rekep_repair.synthetic.env import Synthetic2DEnv


def _intrusion_ctx(t=0):
    return ExecutionContext(t=t, state=np.array([0.4, 0.0, 1.0]),
                            obstacle_pos=np.array([0.5, 0.0]), obstacle_radius=0.1,
                            clearance=0.05, attachments={"object": "grasped"})


def test_false_negative_suppresses_event():
    nm = NoiseModel(p_false_neg=1.0)
    det = EventDetector(d_safe=0.15, noise_model=nm)
    assert det.detect(_intrusion_ctx()).event_type == EventType.NONE


def test_delay_defers_event():
    nm = NoiseModel(delay=3)
    det = EventDetector(d_safe=0.15, noise_model=nm)
    # event present from t=0, but only reported 3 steps later
    fired = [det.detect(_intrusion_ctx(t)).is_active for t in range(6)]
    assert fired[0] is False
    assert any(fired[3:])          # reported after the delay
    assert True in fired


def test_false_positive_can_fire_without_ground_truth():
    quiet = ExecutionContext(t=0, state=np.array([0.0, 0.0, 1.0]), clearance=float("inf"),
                             attachments={"object": "grasped"})
    nm = NoiseModel(p_false_pos=1.0)
    det = EventDetector(d_safe=0.15, noise_model=nm)
    assert det.detect(quiet).event_type == EventType.OBSTACLE_INTRUSION


def test_target_relocation_triggers():
    cfg = SceneConfig(relocation_time=2, relocation_delta=np.array([0.0, 0.3]),
                      obstacle=Obstacle(np.array([9.0, 9.0]), np.array([9.0, 9.0]), 0.05, 0, 0))
    env = Synthetic2DEnv(cfg, seed=0)
    det = EventDetector(d_safe=cfg.d_react, target_threshold=0.15)
    env.reset()
    fired = False
    ctx = env.observe()
    for _ in range(6):
        ev = det.detect(ctx)
        if ev.event_type == EventType.TARGET_RELOCATION:
            fired = True
        ctx = env.step(np.zeros(3))
    assert fired
