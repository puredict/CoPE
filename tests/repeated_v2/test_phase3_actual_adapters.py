"""Real phase-2 interfaces with explicit diagnostic responses and mock execution.

These tests provide no model, simulator, pilot, or formal experimental evidence.
The sealed mock task stays fixed across observation interruptions; inaccurate
proposals deliberately differ from that task and remain inaccurate when resumed.
"""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from cope_benchmark.repeated_v2.adapters import create_adapter
from cope_benchmark.repeated_v2.enums import MethodName
from cope_benchmark.repeated_v2.journal import DurableJournal
from cope_benchmark.repeated_v2.oracle_fixtures import directive_fixture, initial_fixture
from cope_benchmark.repeated_v2.planner_backend import ControlledMechanismBackend
from cope_benchmark.repeated_v2.provider import FixtureReasoner, ReasonerConfig, ReasonerGateway
from cope_benchmark.repeated_v2.runner import EpisodeRunner, InjectionReceipt, RuntimeConfig
from cope_benchmark.repeated_v2.schema import EventEvidence, EvidenceRecord, ExecutionContext

from .test_phase3_runner import EPISODE, MockEnvironment, schedule


GENERATIVE = list(MethodName)[:7]


class PublicFixtureEnvironment(MockEnvironment):
    """Public sensory records and progress, with separate sealed predicates."""
    def public_context(self, observation, previous):
        _, original = initial_fixture()
        data = original.to_dict()
        data["continuation"]["program_counter"] = observation.policy_step
        data["continuation"]["captured_at_step"] = observation.policy_step
        return ExecutionContext.from_dict(data)

    def inject(self, event):
        self.event_index = event.event_index
        self.injections_seen.append((event.event_index, self.policy_step))
        self.segment_actions = 0
        self.version += 1
        fresh = self.observe()
        evidence_id = f"visible-record-{event.event_index}"
        message = "The mug is available for the current request."
        evidence = EventEvidence(
            event_id=event.event_id, event_index=event.event_index,
            hypothesis=message, confidence=1.0, evidence_ids=(evidence_id,),
            timestamp=fresh.version, provenance="diagnostic-public-detector",
            observation_refs=(fresh.observation_ref,))
        record = EvidenceRecord(evidence_id, message, 1.0, "diagnostic-public-detector",
                                fresh.version, observation_refs=(fresh.observation_ref,))
        return InjectionReceipt(evidence, initial_fixture()[0], evidence_records=(record,))

    def sealed_predicate(self, predicate, arguments):
        if predicate == "inside" and tuple(arguments) == ("plate", "rack"):
            return True
        if predicate == "inside" and tuple(arguments) == ("mug", "shelf"):
            return bool(self.achieved)
        if predicate == "at":
            return tuple(arguments) == ("mug", "table")
        return False

    def sealed_progress(self):
        return initial_fixture()[1].progress


def responses_for(method, *, inaccurate=False):
    ledger, initial_context = initial_fixture()
    directive = directive_fixture(ledger, initial_context)
    if inaccurate:
        directive["active_goal_occurrence_ids"] = ["wrong-request@9"]
        directive["remaining_goals"] = [{"occurrence_id": "wrong-request@9",
            "predicate": "inside", "arguments": ["mug", "shelf"]}]
    if method in GENERATIVE[:3]:
        # Real parsers and rejected-state atomicity, without manufacturing edits.
        return ["deliberately malformed diagnostic response"] * 8
    if method == MethodName.SUMMARY_MEMORY_REPLAN:
        return [{"schema_version": "cope-repeated-v2/summary-1",
                 "summary": f"The public observation at interruption {i} was retained.",
                 "planning_directive": deepcopy(directive)} for i in range(1, 9)]
    return [deepcopy(directive) for _ in range(8)]


def create_runner(path, method, reasoner, *, injector=None):
    gateway = ReasonerGateway(reasoner, ReasonerConfig(
        provider="diagnostic-fixture-provider", model="diagnostic-fixture-model",
        max_input_tokens=200000, max_output_tokens=200000))
    adapter = create_adapter(method, gateway=gateway)
    journal = DurableJournal(path, failure_injector=injector)
    runner = EpisodeRunner(config=RuntimeConfig("controlled", phase="test", fixture=True,
        max_policy_steps=180), environment=PublicFixtureEnvironment(), method=adapter,
        planner=ControlledMechanismBackend(), journal=journal)
    return runner, journal


def run(runner, *, resume=False):
    ledger, initial_context = initial_fixture()
    return runner.run(master_episode_id=EPISODE,
        task={"instruction": "Put the mug on the shelf and keep the plate in the rack."},
        initial_state_id=0, seed=15, initial_ledger=ledger, initial_context=initial_context,
        schedule=schedule(), resume=resume)


def key(method, index):
    return "controlled", EPISODE, method.value, index


@pytest.mark.parametrize("method", GENERATIVE)
def test_real_adapters_keep_continuous_state_and_one_journaled_gateway_call(method, tmp_path):
    reasoner = FixtureReasoner(responses_for(method))
    runner, journal = create_runner(tmp_path, method, reasoner)
    with journal:
        episode = run(runner)
        assert episode["reached_events"] == 8
        assert reasoner.calls == 8
        assert len(runner.method.gateway.logs) == 8
        assert len(runner.method.public_history) == 7
        assert journal.inspect_integrity([key(method, i) for i in range(9)],
                                         snapshot_label="completed").valid
        for index, log in enumerate(runner.method.gateway.logs, 1):
            assert log.fixture
            assert f"visible-record-{index}" in json.dumps(log.messages)
            assert f"mock-observation:{1 + (index - 1) * 10}:" in json.dumps(log.messages)
        if method in GENERATIVE[:3]:
            assert runner.method.revision == 0
            assert runner.method.last_outcome.accepted is False
            assert runner.method.ledger == initial_fixture()[0]
        else:
            assert runner.method.revision == 8
            assert runner.method.last_outcome.accepted is True
            assert runner.method.ledger is None


@pytest.mark.parametrize("crash", [False, True])
def test_real_full_history_inaccurate_occurrence_persists_across_resume(tmp_path, crash):
    method = MethodName.FULL_HISTORY_REPLAN
    reasoner = FixtureReasoner(responses_for(method, inaccurate=True))

    def fail(stage):
        if stage == "after_response":
            raise RuntimeError("diagnostic persisted response crash")

    runner, journal = create_runner(tmp_path, method, reasoner, injector=fail if crash else None)
    if crash:
        with journal, pytest.raises(RuntimeError, match="diagnostic persisted response crash"):
            run(runner)
        assert reasoner.calls == 1
        runner, journal = create_runner(tmp_path, method, reasoner)
    with journal:
        episode = run(runner, resume=crash)
        assert episode["reached_events"] == 8
        assert episode["success"] is False
        assert episode["evaluation"]["wrong_occurrence_execution"] == ("wrong-request@9",)
        assert reasoner.calls == 8
        assert len(journal.read_records("intents")) == len(journal.read_records("responses")) == 8
        assert runner.method.revision == 8
        assert runner.method.directive["active_goal_occurrence_ids"] == ["wrong-request@9"]
        for index in range(1, 9):
            boundary = journal.load_snapshot(key(method, index), label="completed")
            assert boundary["planning_problem"]["active_goal_occurrence_ids"] == ["wrong-request@9"]
        assert journal.inspect_integrity([key(method, i) for i in range(9)],
                                         snapshot_label="completed").valid
