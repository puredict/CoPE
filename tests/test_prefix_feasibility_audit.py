from __future__ import annotations

import numpy as np

from experiments import prefix_feasibility_audit as audit


def test_diagnostic_and_locked_splits_are_exact_and_disjoint() -> None:
    assert audit.AUTHORIZED_STATE_IDS == tuple(range(5, 15))
    assert audit.LOCKED_STATE_IDS == tuple(range(15, 25))
    assert set(audit.AUTHORIZED_STATE_IDS).isdisjoint(audit.LOCKED_STATE_IDS)
    assert max(audit.LOCKED_STATE_IDS) < 25


def test_controller_and_provider_protocol_are_frozen() -> None:
    assert audit.CONTROLLER_CONFIG.max_move_steps == 60
    assert audit.CONTROLLER_CONFIG.warmup_steps == 10
    assert audit.PROVIDER_ENV_NAMES == (
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
    )


def test_array_hash_includes_shape_and_dtype() -> None:
    base = np.asarray([1.0, 2.0], dtype=np.float64)
    assert audit.array_hash(base) == audit.array_hash(base.copy())
    assert audit.array_hash(base) != audit.array_hash(base.astype(np.float32))
    assert audit.array_hash(base) != audit.array_hash(base.reshape(1, 2))


def test_phase_summary_retains_failure_diagnostics() -> None:
    phase = audit.CONTROLLER_CONFIG
    record = type(
        "Record",
        (),
        {"phase": "descend_to_grasp", "steps": phase.max_move_steps, "final_error_m": 0.0123},
    )()
    assert audit.phase_summary([record]) == "descend_to_grasp:60:0.012300000"
