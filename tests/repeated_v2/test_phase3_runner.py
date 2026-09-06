"""Mock-only integration tests. No result here is simulator or VLA evidence."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import math

import pytest

from cope_benchmark.repeated_v2.enums import EventFamily, MethodName
from cope_benchmark.repeated_v2.journal import (
    AmbiguousCallError, DurableJournal, DuplicateCellError, JournalError, stable_hash,
)
from cope_benchmark.repeated_v2.planner_backend import ExecutionPlan
from cope_benchmark.repeated_v2.provider import FixtureReasoner, ReasonerConfig, ReasonerGateway
from cope_benchmark.repeated_v2.runner import (
    CommonExecutor, EpisodeRunner, InjectionReceipt, ObservationReceipt, RuntimeBlocked, RuntimeConfig,
)
from cope_benchmark.repeated_v2.schema import (
    ContinuationState, EventEvidence, ExecutionContext, PlanningProblem,
)
from cope_benchmark.repeated_v2.scheduler import TriggerContext, build_master_schedule
from cope_benchmark.repeated_v2.vla_adapter import ActionChunk


EPISODE = "mock-master"
METHOD = MethodName.COPE_TYPED_EDIT


def context(step=0):
    return ExecutionContext((), (), ContinuationState(
        active_stage="mock-stage", active_skill="mock-skill", program_counter=step,
        held_object_hypothesis=None, resumable_suffix=("mock-suffix",),
        controller_state_ref=f"mock-controller:{step}", captured_at_step=step))


def canonical_ledger(index):
    return {"revision": index, "slots": [
        {"occurrence_id": f"goal:{i}", "predicate": "mock_achieved",
         "arguments": [f"goal:{i}"], "role": "achievement_goal", "hardness": "hard",
         "lifecycle": "active" if i == index else "expired"}
        for i in range(index + 1)]}


def schedule():
    return build_master_schedule(EPISODE, seed=15, semantic_triggers={
        family.value: {"predicate": "mock_visible_ready", "earliest_policy_step": 1,
                       "latest_policy_step": 180, "physical_feasibility_guard": "mock_clear",
                       "min_steps_since_previous_event": 10}
        for family in EventFamily})


class MockEnvironment:
    """Deterministic test state machine with separately owned sealed truth."""
    provider_id = "mock-environment-test-only"

    def __init__(self, *, stale_observation=False, stale_evidence=False,
                 wrong_step=False, complete_after=12):
        self.stale_observation = stale_observation
        self.stale_evidence = stale_evidence
        self.wrong_step = wrong_step
        self.complete_after = complete_after
        self.reset_calls = 0
        self.restore_calls = 0
        self.injections_seen = []
        self.actions_seen = []

    def reset(self, *, task, initial_state_id, seed):
        self.reset_calls += 1
        self.policy_step = self.version = self.event_index = self.segment_actions = 0
        self.achieved = set()
        return self.observe()

    def observe(self):
        ref = f"mock-observation:{self.policy_step}:{self.version}"
        return ObservationReceipt({"full_image": [[[self.version % 255, 0, 0]]],
                                   "state": [float(self.policy_step)], "observation_ref": ref},
                                  ref, self.version, self.policy_step)

    def snapshot(self):
        return {"policy_step": self.policy_step, "version": self.version,
                "event_index": self.event_index, "segment_actions": self.segment_actions,
                "achieved": sorted(self.achieved)}

    def restore(self, snapshot):
        self.restore_calls += 1
        for key, value in snapshot.items():
            setattr(self, key, set(value) if key == "achieved" else deepcopy(value))

    def _advance(self, target):
        self.policy_step += 2 if self.wrong_step else 1
        self.version += 1
        self.segment_actions += 1
        self.actions_seen.append((self.policy_step, target))
        if self.segment_actions >= self.complete_after:
            self.achieved.add(target)
        return self.observe()

    def execute_macro(self, macro):
        return self._advance(macro["target_occurrence_id"])

    def step(self, action):
        assert len(action) == 7 and all(math.isfinite(x) for x in action)
        return self._advance(f"goal:{int(action[0])}")

    def inject(self, event):
        self.event_index = event.event_index
        self.injections_seen.append((event.event_index, self.policy_step))
        self.segment_actions = 0
        if not self.stale_observation:
            self.version += 1
        fresh = self.observe()
        evidence = EventEvidence(
            event_id=event.event_id, event_index=event.event_index,
            hypothesis="The visible instruction target changed.", confidence=1.0,
            evidence_ids=(f"mock-evidence:{event.event_index}",),
            timestamp=fresh.version - 1 if self.stale_evidence else fresh.version,
            provenance="mock-detector-test-only", observation_refs=(fresh.observation_ref,),
            user_message=f"goal:{event.event_index}")
        return InjectionReceipt(evidence, canonical_ledger(event.event_index))

    def trigger_context(self, *, previous_event_step):
        return TriggerContext(self.policy_step, {"mock_visible_ready": self.segment_actions > 0},
                              {"mock_clear": True}, previous_event_step=previous_event_step)

    def public_context(self, observation, previous):
        return context(observation.policy_step)

    def macro_complete(self, macro, context):
        return self.segment_actions >= self.complete_after

    def sealed_predicate(self, predicate, arguments):
        assert predicate == "mock_achieved"
        return arguments[0] in self.achieved

    def sealed_progress(self):
        return ()

    def close(self):
        pass


class MockMethod:
    method = METHOD

    def __init__(self, *, reasoner=None, reject_first=False, corrupt_first=False):
        self.reject_first, self.corrupt_first = reject_first, corrupt_first
        self.gateway = ReasonerGateway(reasoner, ReasonerConfig("mock-provider", "mock-model")) if reasoner else None

    def start_episode(self, *, task, ledger, context):
        self.episode_id = task["episode_id"]
        self.accepted_target = "goal:0"
        self.revision = 0
        self.seen = []
        self.received_refs = []
        self.history_lengths = []
        self.rejections = []

    def on_event(self, *, evidence, public_history, context, evidence_records=()):
        assert isinstance(evidence, EventEvidence)
        assert "canonical" not in json.dumps(public_history).lower()
        self.seen.append(self.accepted_target)
        self.received_refs.append(evidence.observation_refs[0])
        self.history_lengths.append(len(public_history))
        accepted = not (self.reject_first and evidence.event_index == 1)
        if self.gateway:
            raw = self.gateway.call(episode_id=self.episode_id, event_index=evidence.event_index,
                messages=[{"role": "user", "content": json.dumps({
                    "event_index": evidence.event_index, "observation_ref": evidence.observation_refs[0],
                    "prior_target": self.accepted_target})}])
            assert json.loads(raw) == {"response": "mock-response"}
        if accepted:
            if self.corrupt_first:
                self.accepted_target = "goal:999"
            else:
                self.accepted_target = evidence.user_message
            self.revision += 1
        else:
            self.rejections.append(evidence.event_index)
        return {"accepted": accepted}

    def compile_state(self, *, context):
        return PlanningProblem(
            problem_id=f"mock-problem:{self.revision}:{self.accepted_target}", source_method=METHOD,
            source_revision=self.revision, initial_facts=(),
            active_goal_occurrence_ids=(self.accepted_target,),
            remaining_goals=({"occurrence_id": self.accepted_target, "predicate": "mock_achieved",
                              "arguments": (self.accepted_target,)},),
            hard_constraints=(), soft_preferences=(), forbidden_regressions=(),
            grounding_bindings=(), restore_eligibility=(), progress_certificates=(),
            continuation_assumptions={"mock_fixture": True})

    def snapshot(self):
        result = {name: deepcopy(getattr(self, name)) for name in (
            "episode_id", "accepted_target", "revision", "seen", "received_refs",
            "history_lengths", "rejections")}
        if self.gateway:
            result["gateway"] = self.gateway.snapshot()
        return result

    def restore(self, snapshot):
        for name, value in snapshot.items():
            if name == "gateway":
                self.gateway.restore(value)
            else:
                setattr(self, name, deepcopy(value))


class MockPlanner:
    provider_id = "mock-planner-test-only"
    uses_hidden_truth = False

    def __init__(self):
        self.targets = []

    def solve(self, *, problem, context):
        target = problem.active_goal_occurrence_ids[0]
        self.targets.append(target)
        return ExecutionPlan(self.provider_id, "controlled_mechanism", problem.problem_id,
            stable_hash(problem.to_dict()), "planned", ({"target_occurrence_id": target,
                "compiled_instruction": {"target_occurrence_id": target,
                                         "text": f"mock instruction for {target}"}},))


class MockVLA:
    provider_id = "mock-vla-test-only"
    learned_policy = False
    uses_privileged_state = False
    stateless = False
    identity = {"provider_id": provider_id, "action_dim": 7, "max_chunk_horizon": 2,
                "action_space": "libero_environment",
                "policy_model_id": "mock", "adapter_type": "mock"}

    def __init__(self):
        self.observations = []

    def reset(self, *, task, seed, initial_observation):
        assert set(task) == {"language"}
        self.target = 0

    def begin_subgoal(self, compiled_instruction):
        self.target = int(compiled_instruction["target_occurrence_id"].split(":")[-1])

    def act(self, observation):
        assert set(observation) <= {"full_image", "state", "observation_ref"}
        self.observations.append(deepcopy(observation))
        return ActionChunk(((float(self.target), 0., 0., 0., 0., 0., 0.),) * 2)

    def snapshot(self):
        return {"target": self.target}

    def restore(self, snapshot):
        self.target = snapshot["target"]

    def close(self):
        pass


def build_runner(path, *, protocol="controlled", environment=None, method=None,
                 injector=None, policy=None, fallback="retain_and_replan", max_steps=180,
                 planner=None):
    journal = DurableJournal(path, failure_injector=injector)
    method = method or MockMethod()
    environment = environment or MockEnvironment()
    planner = planner or MockPlanner()
    runner = EpisodeRunner(config=RuntimeConfig(protocol, max_policy_steps=max_steps,
        phase="test", fixture=True, fallback=fallback), environment=environment,
        method=method, planner=planner, journal=journal, policy=policy)
    return runner, journal


def run(runner, *, resume=False):
    return runner.run(master_episode_id=EPISODE, task={"language": "mock task"},
                      initial_state_id=0, seed=15, initial_ledger=canonical_ledger(0),
                      initial_context=context(), schedule=schedule(), resume=resume)


def key(index, protocol="controlled"):
    return protocol, EPISODE, METHOD.value, index


@pytest.mark.parametrize("protocol,count", [("controlled", 8), ("end_to_end", 4)])
def test_continuous_master_trajectory_with_all_checkpoints_and_finite_actions(tmp_path, protocol, count):
    policy = MockVLA() if protocol == "end_to_end" else None
    runner, journal = build_runner(tmp_path, protocol=protocol, policy=policy)
    with journal:
        episode = run(runner)
        assert episode["reached_events"] == count
        assert episode["success"] is True
        assert runner.env.reset_calls == 1
        assert runner.method.seen == [f"goal:{i}" for i in range(count)]
        assert runner.method.history_lengths == list(range(count))
        assert len(journal.read_records("results")) == count + 1
        assert len(journal.read_records("episodes")) == 1
        assert journal.inspect_integrity([key(i, protocol) for i in range(count + 1)],
                                         snapshot_label="completed").valid
        trace = episode["action_trace"]
        assert [entry["step"] for entry in trace] == list(range(1, len(trace) + 1))
        assert all(entry["target_occurrence_id"] is not None for entry in trace)
        assert {entry["target_occurrence_id"] for entry in trace} == {f"goal:{i}" for i in range(count + 1)}
        for (left, _), (right, _) in zip(runner.env.injections_seen, runner.env.injections_seen[1:]):
            assert right == left + 1
        assert all(b[1] - a[1] >= 10 for a, b in zip(runner.env.injections_seen, runner.env.injections_seen[1:]))
        if policy:
            assert policy.observations
            assert all(len(entry["values"]) == 7 for entry in trace)
            assert all(math.isfinite(value) for entry in trace for value in entry["values"])
        else:
            assert all(entry["values"] is None for entry in trace)


@pytest.mark.parametrize("option,status", [
    ("stale_observation", "INVALID_STALE_POST_EVENT_OBSERVATION"),
    ("stale_evidence", "INVALID_STALE_EVENT_EVIDENCE"),
    ("wrong_step", "INVALID_POLICY_STEP_ACCOUNTING"),
])
def test_stale_post_event_data_and_hidden_policy_steps_fail_closed(tmp_path, option, status):
    runner, journal = build_runner(tmp_path, environment=MockEnvironment(**{option: True}))
    with journal, pytest.raises(RuntimeBlocked) as error:
        run(runner)
    assert error.value.status == status


def test_rejected_update_retains_previous_accepted_state_and_history(tmp_path):
    runner, journal = build_runner(tmp_path, method=MockMethod(reject_first=True))
    with journal:
        episode = run(runner)
        assert runner.method.seen[:3] == ["goal:0", "goal:0", "goal:2"]
        assert runner.method.rejections == [1]
        assert runner.method.history_lengths == list(range(8))
        assert journal.load_snapshot(key(1), label="completed")["method"]["accepted_target"] == "goal:0"
        assert episode["success"] is False
        assert "goal:0" in episode["evaluation"]["wrong_occurrence_execution"]


def test_accepted_corruption_persists_without_canonical_reset_or_planner_repair(tmp_path):
    runner, journal = build_runner(tmp_path, method=MockMethod(corrupt_first=True))
    with journal:
        episode = run(runner)
        assert runner.method.seen == ["goal:0"] + ["goal:999"] * 7
        assert runner.planner.targets == ["goal:0"] + ["goal:999"] * 8
        assert episode["success"] is False
        assert episode["evaluation"]["wrong_occurrence_execution"] == ("goal:999",)
        assert "goal:8" in episode["evaluation"]["unsatisfied_goal_ids"]


@pytest.mark.parametrize("stage", ["after_intent", "after_invoke", "after_response"])
def test_raw_reasoner_intent_is_never_repeated_after_crash(tmp_path, stage):
    reasoner = FixtureReasoner([{"response": "mock-response"}] * 8)
    def crash(where):
        if where == stage:
            raise RuntimeError("injected provider boundary crash")
    first, journal = build_runner(tmp_path, method=MockMethod(reasoner=reasoner), injector=crash)
    with journal, pytest.raises(RuntimeError, match="injected provider boundary crash"):
        run(first)
    already_called = reasoner.calls
    resumed, journal = build_runner(tmp_path, method=MockMethod(reasoner=reasoner))
    with journal:
        if stage == "after_response":
            episode = run(resumed, resume=True)
            assert episode["reached_events"] == 8
            assert reasoner.calls == 8
            assert len(journal.read_records("intents")) == 8
            assert len(journal.read_records("responses")) == 8
        else:
            with pytest.raises(AmbiguousCallError):
                run(resumed, resume=True)
            assert reasoner.calls == already_called


@pytest.mark.parametrize("label,index", [("pre", 1), ("completed", 1), ("completed", 8)])
def test_verified_snapshot_result_crash_gap_resumes_without_duplicates(tmp_path, label, index):
    reasoner = FixtureReasoner([{"response": "mock-response"}] * 8)
    first, journal = build_runner(tmp_path, method=MockMethod(reasoner=reasoner))
    original_save = journal.save_snapshot
    def crash_after_save(the_key, payload, *, label="post"):
        result = original_save(the_key, payload, label=label)
        if tuple(the_key) == key(index) and label == crash_label:
            raise RuntimeError("injected event boundary crash")
        return result
    crash_label = label
    journal.save_snapshot = crash_after_save
    with journal, pytest.raises(RuntimeError, match="injected event boundary crash"):
        run(first)
    resumed, journal = build_runner(tmp_path, method=MockMethod(reasoner=reasoner))
    with journal:
        episode = run(resumed, resume=True)
        assert episode["success"] is True
        assert reasoner.calls == 8
        assert resumed.env.restore_calls > 0
        assert len(journal.read_records("results")) == 9
        assert len(journal.read_records("episodes")) == 1
        assert journal.inspect_integrity([key(i) for i in range(9)], snapshot_label="completed").valid


def test_completed_episode_resume_is_idempotent_and_does_not_reexecute(tmp_path):
    reasoner = FixtureReasoner([{"response": "mock-response"}] * 8)
    first, journal = build_runner(tmp_path, method=MockMethod(reasoner=reasoner))
    with journal:
        expected = run(first)
    resumed, journal = build_runner(tmp_path, method=MockMethod(reasoner=reasoner))
    with journal:
        actual = run(resumed, resume=True)
        assert actual == json.loads(json.dumps(expected))
        assert reasoner.calls == 8
        assert resumed.env.actions_seen == []
        assert len(journal.read_records("episodes")) == 1


@pytest.mark.parametrize("mode", ["rejection", "timeout", "early_completion"])
def test_prior_failure_keeps_every_unreached_cell_in_the_denominator(tmp_path, mode):
    options = ({"method": MockMethod(reject_first=True), "fallback": "terminate"}
               if mode == "rejection" else {"max_steps": 5} if mode == "timeout"
               else {"environment": MockEnvironment(complete_after=1)})
    runner, journal = build_runner(tmp_path, **options)
    with journal:
        episode = run(runner)
        assert episode["success"] is False
        assert episode["reached_events"] < 8
        results = journal.read_records("results")
        assert len(results) == 9
        for i in range(episode["reached_events"] + 1, 9):
            assert results[key(i)]["status"] == "EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE"
            assert results[key(i)]["success"] is False
            assert results[key(i)]["high_level_calls"] == 0
            source_index = results[key(i)]["source_boundary_event_index"]
            assert source_index == episode["reached_events"]
            assert results[key(i)]["source_boundary_sha256"] == stable_hash(
                journal.load_snapshot(key(source_index), label="completed"))
        assert journal.inspect_integrity([key(i) for i in range(9)], snapshot_label="completed").valid


@pytest.mark.parametrize("mode,failed_index,status", [
    ("rejection", 1, "METHOD_REJECTED_TERMINATED"),
    ("timeout", 1, "METHOD_TIMEOUT"),
    ("early_completion", 1, "METHOD_TERMINATED_BEFORE_REQUIRED_EVENT"),
])
@pytest.mark.parametrize("publication", ["completed_snapshot", "failed_result", "unreached_result"])
def test_failure_boundary_resume_retains_failure_and_never_attempts_later_events(
        tmp_path, mode, failed_index, status, publication):
    reasoner = FixtureReasoner([{"response": "mock-response"}] * 8)

    def options():
        return ({"method": MockMethod(reasoner=reasoner, reject_first=True), "fallback": "terminate"}
                if mode == "rejection" else
                {"method": MockMethod(reasoner=reasoner), "max_steps": 5} if mode == "timeout" else
                {"method": MockMethod(reasoner=reasoner), "environment": MockEnvironment(complete_after=1)})

    first, journal = build_runner(tmp_path, **options())
    save = journal.save_snapshot
    record = journal.record_result

    def crash_after_save(the_key, payload, *, label="post"):
        result = save(the_key, payload, label=label)
        if publication == "completed_snapshot" and tuple(the_key) == key(failed_index) and label == "completed":
            raise RuntimeError("injected terminal boundary crash")
        return result

    def crash_after_result(the_key, payload):
        result = record(the_key, payload)
        target_index = failed_index + (publication == "unreached_result")
        if publication != "completed_snapshot" and tuple(the_key) == key(target_index):
            raise RuntimeError("injected terminal boundary crash")
        return result

    journal.save_snapshot = crash_after_save
    journal.record_result = crash_after_result
    with journal, pytest.raises(RuntimeError, match="injected terminal boundary crash"):
        run(first)
    previous_calls = reasoner.calls
    resumed, journal = build_runner(tmp_path, **options())
    with journal:
        episode = run(resumed, resume=True)
        assert episode["status"] == status
        assert episode["success"] is False
        assert episode["reached_events"] == failed_index
        assert resumed.env.actions_seen == []
        assert resumed.env.injections_seen == []
        assert reasoner.calls == previous_calls
        assert len(journal.read_records("results")) == 9
        assert len(journal.read_records("episodes")) == 1
        assert journal.inspect_integrity([key(i) for i in range(9)], snapshot_label="completed").valid


def test_rejected_accepted_state_mutation_fails_closed_before_execution(tmp_path):
    class BrokenRejectingMethod(MockMethod):
        def on_event(self, **kwargs):
            self.revision += 1
            return {"accepted": False}

    runner, journal = build_runner(tmp_path, method=BrokenRejectingMethod())
    with journal, pytest.raises(RuntimeBlocked) as error:
        run(runner)
    assert error.value.status == "INVALID_REJECTED_STATE_MUTATION"
    assert runner.env.actions_seen == [(1, "goal:0")]


def test_vla_resumes_exact_chunk_and_persistent_policy_state(tmp_path):
    first_policy = MockVLA()
    first, journal = build_runner(tmp_path, protocol="end_to_end", policy=first_policy)
    original_save = journal.save_snapshot

    def crash_after_save(the_key, payload, *, label="post"):
        result = original_save(the_key, payload, label=label)
        if tuple(the_key) == key(1, "end_to_end") and label == "pre":
            # A chunk has already been partly consumed at this boundary.
            assert payload["executor"]["chunk"]
            raise RuntimeError("injected VLA pre-boundary crash")
        return result

    journal.save_snapshot = crash_after_save
    with journal, pytest.raises(RuntimeError, match="injected VLA pre-boundary crash"):
        run(first)
    resumed, journal = build_runner(tmp_path, protocol="end_to_end", policy=MockVLA())
    with journal:
        episode = run(resumed, resume=True)
        assert episode["success"] is True
        assert episode["reached_events"] == 4
        assert all(len(action["values"]) == 7 for action in episode["action_trace"])
        assert [entry["step"] for entry in episode["action_trace"]] == list(
            range(1, len(episode["action_trace"]) + 1))
        assert journal.inspect_integrity([key(i, "end_to_end") for i in range(5)],
                                         snapshot_label="completed").valid


@pytest.mark.parametrize("corruption", ["receipt", "sensory"])
def test_restored_environment_must_match_verified_snapshot_exactly(tmp_path, corruption):
    first, journal = build_runner(tmp_path)
    original_save = journal.save_snapshot

    def crash_after_save(the_key, payload, *, label="post"):
        result = original_save(the_key, payload, label=label)
        if tuple(the_key) == key(1) and label == "completed":
            raise RuntimeError("injected restore validation crash")
        return result

    journal.save_snapshot = crash_after_save
    with journal, pytest.raises(RuntimeError, match="injected restore validation crash"):
        run(first)

    class IncorrectRestoration(MockEnvironment):
        def restore(self, snapshot):
            super().restore(snapshot)
            self.restored_wrongly = True

        def observe(self):
            receipt = super().observe()
            if getattr(self, "restored_wrongly", False):
                if corruption == "receipt":
                    return ObservationReceipt(receipt.payload, receipt.observation_ref,
                                              receipt.version + 1, receipt.policy_step)
                return ObservationReceipt({**receipt.payload, "state": [-999.]},
                                          receipt.observation_ref, receipt.version, receipt.policy_step)
            return receipt

    resumed, journal = build_runner(tmp_path, environment=IncorrectRestoration())
    with journal, pytest.raises(RuntimeBlocked) as error:
        run(resumed, resume=True)
    assert error.value.status == "INVALID_SNAPSHOT_RESTORE"
    assert resumed.env.actions_seen == []
    assert resumed.env.injections_seen == []


@pytest.mark.parametrize("missing", ["result", "snapshot"])
def test_completed_episode_resume_requires_all_verified_cells(tmp_path, missing):
    first, journal = build_runner(tmp_path)
    with journal:
        run(first)
        if missing == "result":
            path = journal.root / "results" / (stable_hash(list(key(3))) + ".json")
        else:
            path = journal.root / "snapshots" / "completed" / (stable_hash(list(key(3))) + ".json")
    # Simulate loss of one previously committed synthetic artifact.
    path.unlink()
    resumed, journal = build_runner(tmp_path)
    with journal, pytest.raises((JournalError, RuntimeBlocked)):
        run(resumed, resume=True)
    assert resumed.env.actions_seen == []


def test_replayed_reasoner_response_retains_original_duration_in_result(tmp_path, monkeypatch):
    from cope_benchmark.repeated_v2 import journal as journal_module
    clock = {"now": 5.0}
    monkeypatch.setattr(journal_module.time, "monotonic", lambda: clock["now"])

    class TimedFixtureReasoner(FixtureReasoner):
        def complete(self, **kwargs):
            clock["now"] += 1.25
            return super().complete(**kwargs)

    reasoner = TimedFixtureReasoner([{"response": "mock-response"}] * 8)

    def crash(stage):
        if stage == "after_response":
            raise RuntimeError("durable timed response crash")

    first, journal = build_runner(tmp_path, method=MockMethod(reasoner=reasoner), injector=crash)
    with journal, pytest.raises(RuntimeError, match="durable timed response crash"):
        run(first)
    assert reasoner.calls == 1
    clock["now"] = 1000.0
    resumed, journal = build_runner(tmp_path, method=MockMethod(reasoner=reasoner))
    with journal:
        run(resumed, resume=True)
        assert reasoner.calls == 8
        for index in range(1, 9):
            assert journal.event_result(key(index))["metrics"]["reasoner_seconds"] == 1.25
            assert journal.invocation_seconds(key(index)) == 1.25


@pytest.mark.parametrize("failure_site", ["initial_plan", "event_plan", "before_macro", "complete_recovery"])
@pytest.mark.parametrize("error_name", ["UnsupportedPlanningSemantics", "RecoveryGateBlocked"])
@pytest.mark.parametrize("crash", [False, True])
def test_continuation_semantic_failures_retain_cells_and_resume_terminal_state(
        tmp_path, failure_site, error_name, crash):
    from cope_benchmark.repeated_v2 import continuation_backend
    error_type = getattr(continuation_backend, error_name)
    failed_index = 0 if failure_site == "initial_plan" else 1
    expected_status = ("METHOD_PLANNING_FAILURE" if failure_site.endswith("plan")
                       else "METHOD_RECOVERY_EXECUTION_FAILURE")

    class SemanticFailurePlanner(MockPlanner):
        def solve(self, *, problem, context):
            if (failure_site == "initial_plan" and problem.source_revision == 0
                    or failure_site == "event_plan" and problem.source_revision == 1):
                raise error_type("diagnostic accepted recovery cannot be realized")
            plan = super().solve(problem=problem, context=context)
            if failure_site == "complete_recovery" and problem.source_revision == 1:
                plan = replace(plan, macro_actions=tuple({**dict(macro), "recovery": True,
                    "stage_id": "diagnostic-recovery"} for macro in plan.macro_actions))
            return plan

        def before_macro(self, macro):
            if failure_site == "before_macro" and macro["target_occurrence_id"] == "goal:1":
                raise error_type("diagnostic recovery stage cannot start")

        def complete_recovery_stage(self, *, stage_id, context):
            assert stage_id == "diagnostic-recovery"
            raise error_type("diagnostic recovery stage was not verified")

    def setup():
        return build_runner(tmp_path, planner=SemanticFailurePlanner(),
                            environment=MockEnvironment(complete_after=2))

    runner, journal = setup()
    if crash:
        save = journal.save_snapshot

        def crash_after_save(the_key, payload, *, label="post"):
            result = save(the_key, payload, label=label)
            if tuple(the_key) == key(failed_index) and label == "completed":
                raise RuntimeError("diagnostic terminal recovery snapshot crash")
            return result

        journal.save_snapshot = crash_after_save
        with journal, pytest.raises(RuntimeError, match="diagnostic terminal recovery snapshot crash"):
            run(runner)
        runner, journal = setup()
    with journal:
        episode = run(runner, resume=crash)
        assert episode["status"] == expected_status
        assert episode["success"] is False
        assert episode["reached_events"] == failed_index
        assert journal.event_result(key(failed_index))["status"] == expected_status
        assert len(journal.read_records("results")) == 9
        assert journal.inspect_integrity([key(i) for i in range(9)], snapshot_label="completed").valid
        if crash:
            assert runner.env.actions_seen == [] and runner.env.injections_seen == []
        if failure_site in {"initial_plan", "event_plan", "before_macro"}:
            assert journal.event_result(key(failed_index))["execution_started_at"] is None


def test_continuation_backend_unavailability_remains_infrastructure_failure(tmp_path):
    from cope_benchmark.repeated_v2.continuation_backend import PlannerBackendUnavailable

    class UnavailablePlanner(MockPlanner):
        def solve(self, **kwargs):
            raise PlannerBackendUnavailable("diagnostic missing dependency")

    runner, journal = build_runner(tmp_path, planner=UnavailablePlanner())
    with journal, pytest.raises(PlannerBackendUnavailable):
        run(runner)


def test_common_executor_traces_raw_and_converted_actions_without_extra_inference():
    class NativeActionFixture(MockVLA):
        identity = {**MockVLA.identity,
                    "action_space": "openvla_raw_normalize_binarize_then_invert_gripper"}

        def act(self, observation):
            self.observations.append(deepcopy(observation))
            return ActionChunk(((0., 0., 0., 0., 0., 0., 0.25),) * 2)

    environment, policy, method = MockEnvironment(), NativeActionFixture(), MockMethod()
    observation = environment.reset(task={}, initial_state_id=0, seed=15)
    method.start_episode(task={"episode_id": EPISODE}, ledger=canonical_ledger(0), context=context())
    policy.reset(task={"language": "diagnostic action"}, seed=15, initial_observation=observation.payload)
    executor = CommonExecutor(environment=environment, policy=policy,
        config=RuntimeConfig("end_to_end", phase="test", fixture=True))
    problem = method.compile_state(context=context())
    executor.begin(MockPlanner().solve(problem=problem, context=context()), problem)
    for _ in range(2):
        observation, entry = executor.step(observation, context())
        assert entry["raw_values"][-1] == 0.25
        assert entry["values"][-1] == 1.0
        assert entry["action_space"] == policy.identity["action_space"]
    assert len(policy.observations) == 1
    assert len(environment.actions_seen) == 2
    assert len(executor.trace) == 2
    assert executor.chunk == []
