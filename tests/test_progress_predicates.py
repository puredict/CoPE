from __future__ import annotations

from dataclasses import dataclass

from cope_benchmark.task_progress import (
    TASK_DEFINITIONS,
    ProgressTracker,
    get_task_definition,
)


@dataclass
class FakeState:
    predicates: dict[tuple[str, tuple[str, ...]], bool]
    positions: dict[str, tuple[float, float, float]]
    success: bool = False

    def libero_predicate(self, predicate, arguments):
        return self.predicates.get((predicate, tuple(arguments)), False)

    def object_position(self, object_name):
        return self.positions[object_name]

    def final_success(self):
        return self.success


def _task0_state() -> FakeState:
    return FakeState(
        predicates={
            ("in", ("alphabet_soup_1", "basket_1_contain_region")): False,
            ("in", ("tomato_sauce_1", "basket_1_contain_region")): False,
        },
        positions={
            "alphabet_soup_1": (0.0, 0.0, 0.46),
            "tomato_sauce_1": (0.0, 0.0, 0.48),
            "basket_1": (0.0, 0.2, 0.48),
        },
    )


def test_four_tasks_have_multistage_deterministic_progress_definitions() -> None:
    assert sorted(TASK_DEFINITIONS) == [
        ("libero_10", 0),
        ("libero_10", 1),
        ("libero_10", 4),
        ("libero_10", 8),
    ]
    for definition in TASK_DEFINITIONS.values():
        commitments = [predicate for predicate in definition.predicates if predicate.commitment]
        assert len(commitments) >= 2
        assert all(predicate.reversible for predicate in commitments)
        assert any(predicate.kind == "final_success" for predicate in definition.predicates)


def test_progress_tracker_logs_current_reversible_and_irreversible_history() -> None:
    definition = get_task_definition("libero_10", 0)
    state = _task0_state()
    tracker = ProgressTracker(definition)
    initial = tracker.sample(state, policy_step=0)
    assert initial.current["alphabet_soup_in_basket"] is False
    assert initial.current["basket_reachable"] is True

    state.predicates[("in", ("alphabet_soup_1", "basket_1_contain_region"))] = True
    achieved = tracker.sample(state, policy_step=10)
    assert achieved.current["alphabet_soup_in_basket"] is True
    assert achieved.irreversible["ever:alphabet_soup_in_basket"] is True

    state.predicates[("in", ("alphabet_soup_1", "basket_1_contain_region"))] = False
    regressed = tracker.sample(state, policy_step=11)
    assert regressed.current["alphabet_soup_in_basket"] is False
    assert regressed.ever_achieved["alphabet_soup_in_basket"] is True
    assert regressed.irreversible["ever:alphabet_soup_in_basket"] is True


def test_final_success_is_not_used_as_the_only_progress_signal() -> None:
    definition = get_task_definition("libero_10", 0)
    state = _task0_state()
    state.predicates[("in", ("alphabet_soup_1", "basket_1_contain_region"))] = True
    sample = ProgressTracker(definition).sample(state, policy_step=8)
    assert sample.current["alphabet_soup_in_basket"] is True
    assert sample.current["tomato_sauce_in_basket"] is False
    assert sample.current["final_goal_currently_satisfied"] is False
