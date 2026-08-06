from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "delivery_semantics_stress", ROOT / "experiments" / "delivery_semantics_stress.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_every_frozen_schedule_passes_for_every_representation():
    for schedule in MODULE.SCHEDULES:
        hashes = set()
        for arm in MODULE.ARMS:
            row, trace = MODULE.run_cell(schedule, arm)
            assert row["passed"] is True
            assert row["publications"] == 2
            assert row["directive_count"] == 2
            assert row["caller_unchanged_on_rejection"] is True
            assert row["typed_revision_synchronized"] is True
            assert len(trace) == row["deliveries"]
            hashes.add(row["final_state_sha256"])
        assert len(hashes) == 1


def test_fault_schedules_exercise_expected_rejection_or_crash_paths():
    expectations = {
        "nominal": (0, 0, 0),
        "immediate_duplicate": (1, 0, 0),
        "delayed_duplicate": (1, 0, 0),
        "out_of_order": (1, 0, 0),
        "same_base_conflict": (1, 0, 0),
        "crash_before_validation": (0, 1, 0),
        "crash_after_stage": (0, 1, 1),
        "crash_after_publish_before_ack": (1, 1, 0),
    }
    for schedule, (rejections, crashes, staged_aborts) in expectations.items():
        for arm in MODULE.ARMS:
            row, _ = MODULE.run_cell(schedule, arm)
            assert row["rejections"] == rejections
            assert row["crashes"] == crashes
            assert row["staged_aborts"] == staged_aborts

