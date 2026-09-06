"""R4 failure accounting and diagnostic/free-running separation tests."""

from contextlib import redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cope.lineage_benchmark.client import ModelClient, OracleModelClient
from cope.lineage_benchmark.models import GenerationResult, ScenarioSpec, canonical_json
from cope.lineage_benchmark.reference import reference_transition
from cope.lineage_benchmark.runner import run_episode
from cope.lineage_benchmark.schemas import validate_output_document
from cope.lineage_benchmark.task import ROOT_SLOT_ID, build_scenario


ROOT = Path(__file__).resolve().parents[1]
driver_spec = importlib.util.spec_from_file_location("r4_test_driver", ROOT / "scripts/run_r4_lineage.py")
driver = importlib.util.module_from_spec(driver_spec)
driver_spec.loader.exec_module(driver)


def failure(status="timeout"):
    return GenerationResult(
        ok=False, status=status, text="partial response", parsed=None,
        latency_s=90.0, request_completed=False,
        cancellation_status="connection_closed_cancellation_unconfirmed",
    )


class TrackingClient(ModelClient):
    def __init__(self, failed_ordinals=(), callback=None, episode_dir=None):
        self.failed_ordinals = set(failed_ordinals)
        self.callback = callback
        self.episode_dir = episode_dir
        self.packets = []
        self.progress_seen = []
        self.oracle = OracleModelClient()

    def generate(self, **kwargs):
        packet = kwargs["packet"]
        self.packets.append(deepcopy(packet))
        if self.episode_dir:
            self.progress_seen.append(json.loads((self.episode_dir / "progress.json").read_text()))
        if packet.event.ordinal in self.failed_ordinals:
            return failure()
        if self.callback:
            document = self.callback(packet)
            validate_output_document(kwargs["method"], document)
            return GenerationResult(
                ok=True, status="ok", text=canonical_json(document), parsed=document,
                latency_s=0.01, finish_reason="stop", request_completed=True,
                telemetry={"output_schema_valid": True},
            )
        return self.oracle.generate(**kwargs)


def acknowledge_without_changing_mode(packet):
    document = deepcopy(packet.current_state.to_dict())
    document["revision"] += 1
    current = next(slot for slot in document["slots"] if slot["slot_id"] == packet.event.current_slot_id)
    current["history"].append({
        "seq": len(current["history"]) + 1, "event_id": packet.event.event_id,
        "operation": "AcknowledgeWithoutRestore", "mode_before": current["mode"],
        "mode_after": current["mode"], "detail": packet.event.reason,
    })
    return document


def correct_fsr(packet):
    return reference_transition(
        packet.current_state, packet.event, packet.task_contract["critical_logical_id"],
    ).to_dict()


class RunnerAccountingTests(unittest.TestCase):
    def setUp(self):
        self.scenario = build_scenario(ScenarioSpec(
            seed=1000, profile="calibration", initial_slots=8, lineage_depth=2,
            max_output_tokens=100000, model_timeout_s=90.0,
        ))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "episode"

    def test_free_running_failure_stops_and_preserves_event_progress_evidence(self):
        client = TrackingClient(failed_ordinals={3}, episode_dir=self.out)
        with patch("cope.lineage_benchmark.runner.make_world") as world:
            row = run_episode(self.scenario, method="CoPE", client=client,
                              episode_dir=self.out, backend="libero_mujoco")
        world.assert_not_called()
        metrics = row["metrics"]
        self.assertEqual(metrics["n_model_calls"], 3)
        self.assertEqual(metrics["valid_model_calls"], 2)
        self.assertEqual(metrics["first_failure"], "timeout")
        self.assertEqual(metrics["first_failure_event"], "seed-1000/e03")
        self.assertFalse(metrics["all_events_processed"])
        self.assertFalse(metrics["physical_attempted"])
        self.assertIsNone(metrics["physical_success"])
        self.assertIsNone(row["physical"]["physical_success"])
        self.assertIsNone(row["physical"]["exact_assignment"])
        self.assertFalse(metrics["end_to_end_success"])
        self.assertFalse(metrics["task_completion"])
        self.assertEqual([p["ordinal"] for p in client.progress_seen], [1, 2, 3])
        self.assertEqual([p["completed_calls"] for p in client.progress_seen], [0, 1, 2])
        last_call = row["model_calls"][-1]
        self.assertFalse(last_call["state_committed"])
        self.assertFalse(last_call["request_completed"])
        self.assertEqual(last_call["failure_stage"], "generation")
        self.assertEqual(last_call["state_fingerprint_before"], last_call["state_fingerprint_after"])
        self.assertEqual(len((self.out / "model_calls.jsonl").read_text().splitlines()), 3)
        snapshots = [json.loads(line) for line in (self.out / "state_snapshots.jsonl").read_text().splitlines()]
        self.assertEqual(snapshots[-1]["label"], "rejected_after_event_03")
        self.assertEqual(snapshots[-1]["revision"], 2)
        self.assertEqual(json.loads((self.out / "progress.json").read_text())["completed_calls"], 3)

    def test_reference_diagnostic_observes_all_seven_failed_requests_without_physical_execution(self):
        client = TrackingClient(failed_ordinals=range(1, 8))
        with patch("cope.lineage_benchmark.runner.make_world") as world:
            row = run_episode(self.scenario, method="FSR-PC", client=client,
                              episode_dir=self.out, diagnostic_reference_inputs=True)
        world.assert_not_called()
        self.assertEqual(row["run_mode"], "reference_fed_diagnostic")
        self.assertEqual(len(client.packets), 7)
        expected = self.scenario.initial_state
        for packet, event in zip(client.packets, self.scenario.events):
            self.assertEqual(packet.current_state.to_dict(), expected.to_dict())
            expected = reference_transition(expected, event, self.scenario.critical_logical_id)
        metrics = row["metrics"]
        self.assertTrue(metrics["all_events_processed"])
        self.assertEqual(metrics["valid_model_calls"], 0)
        self.assertIsNone(metrics["task_completion"])
        self.assertIsNone(metrics["end_to_end_success"])
        self.assertIsNone(metrics["physical_success"])
        self.assertFalse(metrics["physical_attempted"])
        self.assertTrue(all(not call["state_committed"] for call in row["model_calls"]))
        self.assertEqual(row["compiled_plan"], [])
        self.assertEqual(row["physical"]["skipped_reason"], "reference_fed_diagnostic")

    def test_even_successful_reference_diagnostic_is_never_task_or_physical_success(self):
        with patch("cope.lineage_benchmark.runner.make_world") as world:
            row = run_episode(self.scenario, method="CoPE", client=TrackingClient(),
                              episode_dir=self.out, diagnostic_reference_inputs=True)
        world.assert_not_called()
        self.assertTrue(row["metrics"]["all_generations_valid"])
        self.assertTrue(row["metrics"]["all_registered_transitions_semantically_matched"])
        self.assertIsNone(row["metrics"]["task_completion"])
        self.assertIsNone(row["metrics"]["end_to_end_success"])
        self.assertFalse(row["metrics"]["physical_attempted"])
        self.assertTrue(all(not call["state_committed"] for call in row["model_calls"]))

    def test_successful_symbolic_free_running_is_not_physical_end_to_end_success(self):
        row = run_episode(self.scenario, method="CoPE", client=TrackingClient(),
                          episode_dir=self.out, backend="symbolic_basket")
        self.assertTrue(row["metrics"]["all_registered_transitions_semantically_matched"])
        self.assertTrue(row["metrics"]["symbolic_execution_success"])
        self.assertFalse(row["metrics"]["physical_attempted"])
        self.assertIsNone(row["metrics"]["physical_success"])
        self.assertFalse(row["metrics"]["end_to_end_success"])

    def test_coherent_wrong_final_candidate_is_committed_and_scored_not_oracle_corrected(self):
        client = TrackingClient(callback=lambda p: (
            acknowledge_without_changing_mode(p) if p.event.ordinal == 7 else correct_fsr(p)
        ))
        row = run_episode(self.scenario, method="FSR-PC", client=client, episode_dir=self.out)
        last = row["model_calls"][-1]
        self.assertTrue(last["transition_valid"])
        self.assertTrue(last["state_committed"])
        self.assertFalse(last["semantic_match_to_registered_transition"])
        self.assertEqual(last["failure_stage"], "semantic")
        self.assertEqual(row["metrics"]["first_failure_event"], "seed-1000/e07")
        self.assertFalse(row["metrics"]["root_lineage_restored"])
        self.assertFalse(row["metrics"]["compiled_plan_matches_root"])
        self.assertEqual(row["compiled_plan"][0], dict(self.scenario.expected_plan[0]))
        self.assertNotEqual(row["compiled_plan"][1:], list(self.scenario.expected_plan[1:]))
        self.assertFalse(row["metrics"]["end_to_end_success"])
        self.assertFalse(row["metrics"]["physical_attempted"])
        self.assertIsNone(row["metrics"]["physical_success"])
        self.assertFalse(row["metrics"]["symbolic_execution_success"])

    def test_wrong_prior_state_can_make_reference_undefined_without_crashing_or_correcting(self):
        client = TrackingClient(callback=lambda p: (
            acknowledge_without_changing_mode(p) if p.event.ordinal in {1, 2} else correct_fsr(p)
        ))
        row = run_episode(self.scenario, method="FSR-PC", client=client, episode_dir=self.out)
        self.assertEqual(len(client.packets), 7)
        self.assertEqual(client.packets[1].current_state.slots[ROOT_SLOT_ID].mode, "active")
        self.assertTrue(row["model_calls"][1]["state_committed"])
        self.assertIn("reference_transition_error", row["model_calls"][1]["generation"]["telemetry"])
        self.assertFalse(row["metrics"]["all_registered_transitions_semantically_matched"])
        self.assertFalse(row["metrics"]["end_to_end_success"])
        self.assertEqual(row["metrics"]["first_failure_event"], "seed-1000/e01")

    def test_unconfirmed_server_drain_stops_even_reference_diagnostic_before_next_request(self):
        inner = TrackingClient(failed_ordinals=range(1, 8))
        client = driver.DrainCheckedClient(inner, "http://not-contacted")
        class MetricsResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return b"vllm:num_requests_running 1\nvllm:num_requests_waiting 0\n"
        with patch.object(driver, "urlopen", return_value=MetricsResponse()), \
             patch.object(driver.time, "sleep"), \
             patch("cope.lineage_benchmark.runner.make_world") as world:
            row = run_episode(self.scenario, method="FSR-PC", client=client,
                              episode_dir=self.out, diagnostic_reference_inputs=True)
        world.assert_not_called()
        self.assertEqual(len(inner.packets), 1)
        self.assertTrue(client.blocked)
        self.assertFalse(row["metrics"]["all_events_processed"])
        self.assertFalse(row["model_calls"][0]["generation"]["telemetry"]["server_drain"]["confirmed_idle"])
        self.assertTrue((self.out / "result.json").exists())


class DriverGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.config = json.loads((ROOT / "configs_r4/experiment.json").read_text())
        # Keep these guard tests deterministic after the live config is frozen.
        self.config["protocol_phase"] = "phase1_diagnostic"
        self.config["budgets"]["adequate"].update({
            "status": "pending_development_capacity_and_throughput_audit",
            "max_output_tokens": None, "timeout_s": None,
        })
        self.cfg_path = self.base / "config.json"
        self.cfg_path.write_text(json.dumps(self.config))
        self.out = self.base / "run"

    def invoke(self, *args):
        argv = ["run_r4_lineage.py", "--config", str(self.cfg_path),
                "--out", str(self.out), "--client", "oracle", *args]
        with patch("sys.argv", argv), redirect_stdout(io.StringIO()):
            return driver.main()

    def test_reference_diagnostics_cannot_use_test_split_or_physical_backend(self):
        for args in (("--split", "test"), ("--backend", "libero_mujoco")):
            with self.subTest(args=args):
                with self.assertRaisesRegex(ValueError, "development-only"):
                    self.invoke("--budget", "fixed", "--mode", "reference_diagnostic", *args)
                self.assertFalse(self.out.exists())

    def test_unfrozen_adequate_budget_rejected_before_output_creation(self):
        with self.assertRaisesRegex(ValueError, "budget pending"):
            self.invoke("--budget", "adequate")
        self.assertFalse(self.out.exists())

    def test_numeric_adequate_trial_budget_is_rejected_until_status_is_frozen(self):
        self.config["budgets"]["adequate"].update({
            "max_output_tokens": 23552, "timeout_s": 1200.0,
            "status": "pending_development_capacity_and_throughput_audit",
        })
        self.cfg_path.write_text(json.dumps(self.config))
        with patch.object(driver, "OracleModelClient") as client:
            with self.assertRaisesRegex(ValueError, "not frozen"):
                self.invoke("--budget", "adequate")
        client.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_test_split_requires_completed_development_freeze_even_for_fixed_budget(self):
        with self.assertRaisesRegex(ValueError, "freeze"):
            self.invoke("--budget", "fixed", "--split", "test")
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
