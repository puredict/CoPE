from __future__ import annotations

import inspect

import pytest

from cope.libero_backend import LiberoComparisonBackend
from cope.libero_predicate_validator import (
    PredicateSnapshotError,
    attach_libero_predicate_snapshot,
)


COMMIT = "2fcfb32ec9c3a4b80642ddea494d9e32c85eb11b"


class FakeBaseEnv:
    def __init__(self) -> None:
        self.calls = 0

    def _eval_predicate(self, state):
        self.calls += 1
        return state[1] == "cream_cheese_1"


class FakeWrapper:
    def __init__(self) -> None:
        self.env = FakeBaseEnv()


def base_observation() -> dict:
    return {"sha256": "a" * 64, "fresh": True}


def enabled_config() -> dict:
    return {
        "predicate_snapshot": {
            "enabled": True,
            "test_only": True,
            "producer_commit": COMMIT,
        }
    }


def attach(config, fields, env):
    return attach_libero_predicate_snapshot(
        base_observation(),
        env,
        engine_config=config,
        observation_fields=fields,
        task_suite="libero_10",
        task_id=1,
        event_id="semantic-event-1",
        policy_step=280,
        simulator_state_sha256="b" * 64,
    )


def test_disabled_integration_does_not_touch_simulator_predicates() -> None:
    env = FakeWrapper()
    result = attach({}, (), env)
    assert "predicate_snapshot" not in result
    assert env.env.calls == 0


def test_enabled_integration_is_information_budget_guarded() -> None:
    with pytest.raises(PredicateSnapshotError, match="information budget"):
        attach(enabled_config(), ("sha256", "fresh"), FakeWrapper())


def test_enabled_integration_attaches_live_predicate_packet() -> None:
    env = FakeWrapper()
    result = attach(
        enabled_config(),
        ("sha256", "fresh", "predicate_snapshot"),
        env,
    )
    assert result["predicate_snapshot"]["source_kind"] == "live_libero_eval_predicate"
    assert env.env.calls == 2


def test_formal_backend_calls_the_guarded_attachment_boundary() -> None:
    source = inspect.getsource(LiberoComparisonBackend.run_episode)
    assert "attach_libero_predicate_snapshot(" in source

