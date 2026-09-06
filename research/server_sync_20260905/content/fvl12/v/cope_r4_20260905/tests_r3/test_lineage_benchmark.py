from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from cope.lineage_benchmark.analysis import analyse
from cope.lineage_benchmark.client import OracleModelClient, parse_json_object
from cope.lineage_benchmark.models import ScenarioSpec, WorkflowState
from cope.lineage_benchmark.runner import run_episode
from cope.lineage_benchmark.state import (
    active_plan,
    apply_patch_document,
    validate_regenerated_transition,
)
from cope.lineage_benchmark.task import ROOT_SLOT_ID, build_scenario, oracle_patch


def spec(slots=8, depth=4, budget=4096):
    return ScenarioSpec(
        seed=7,
        profile="test",
        initial_slots=slots,
        lineage_depth=depth,
        max_output_tokens=budget,
        model_timeout_s=30.0,
    )


class LineageTaskTests(unittest.TestCase):
    def test_registered_initial_slot_count_and_event_count(self):
        scenario = build_scenario(spec(slots=48, depth=6))
        self.assertEqual(len(scenario.initial_state.slots), 48)
        self.assertEqual(len(scenario.events), 11)

    def test_deepest_surface_goal_matches_root_but_continuation_differs(self):
        scenario = build_scenario(spec(depth=4))
        root_plan = scenario.initial_state.slots[ROOT_SLOT_ID].payload["plan"]
        deepest = scenario.events[-4].new_slot
        self.assertEqual(deepest["payload"]["target"], "basket_B")
        self.assertEqual(deepest["payload"]["plan"][0], root_plan[0])
        self.assertNotEqual(deepest["payload"]["plan"][1:], root_plan[1:])

    def test_oracle_restore_root_uses_lineage_and_expires_detours(self):
        scenario = build_scenario(spec(depth=4))
        state = scenario.initial_state
        for event in scenario.events:
            state = apply_patch_document(
                state, oracle_patch(state, event), event, scenario.critical_logical_id
            )
        self.assertEqual(active_plan(state, scenario.critical_logical_id), list(scenario.expected_plan))
        self.assertEqual(state.slots[ROOT_SLOT_ID].mode, "active")
        detours = [slot for sid, slot in state.slots.items() if "/detour-" in sid]
        self.assertTrue(detours)
        self.assertTrue(all(slot.mode == "expired" for slot in detours))

    def test_full_regeneration_cannot_drop_history_prefix(self):
        scenario = build_scenario(spec())
        event = scenario.events[0]
        oracle = apply_patch_document(
            scenario.initial_state,
            oracle_patch(scenario.initial_state, event),
            event,
            scenario.critical_logical_id,
        )
        archive_id = next(
            sid for sid, slot in oracle.slots.items() if slot.kind == "order_archive"
        )
        broken_slots = dict(oracle.slots)
        broken_slots[archive_id] = replace(broken_slots[archive_id], history=())
        broken = WorkflowState(revision=oracle.revision, slots=broken_slots)
        errors = validate_regenerated_transition(
            scenario.initial_state, broken, event, scenario.critical_logical_id
        )
        self.assertTrue(any("history" in error for error in errors))

    def test_coherent_but_wrong_lineage_state_remains_a_task_error(self):
        scenario = build_scenario(spec(depth=4))
        state = scenario.initial_state
        for event in scenario.events[:-1]:
            state = apply_patch_document(
                state, oracle_patch(state, event), event, scenario.critical_logical_id
            )
        final_event = scenario.events[-1]
        deepest = state.slots[final_event.current_slot_id]
        wrong_entry = {
            "seq": len(deepest.history) + 1,
            "event_id": final_event.event_id,
            "operation": "AcknowledgeWithoutRestore",
            "mode_before": deepest.mode,
            "mode_after": deepest.mode,
            "detail": final_event.reason,
        }
        wrong_slots = dict(state.slots)
        wrong_slots[deepest.slot_id] = replace(
            deepest, history=deepest.history + (wrong_entry,)
        )
        wrong = WorkflowState(revision=state.revision + 1, slots=wrong_slots)
        self.assertEqual(
            validate_regenerated_transition(
                state, wrong, final_event, scenario.critical_logical_id
            ),
            [],
        )
        self.assertNotEqual(
            active_plan(wrong, scenario.critical_logical_id),
            list(scenario.expected_plan),
        )

    def test_json_parser_rejects_trailing_answer(self):
        with self.assertRaises(ValueError):
            parse_json_object('{"ok":true} second answer')


class EpisodeTests(unittest.TestCase):
    def test_unbudgeted_oracle_proves_paths_are_semantically_equivalent(self):
        scenario = build_scenario(spec(slots=10, depth=6, budget=100000))
        with tempfile.TemporaryDirectory() as tmp:
            rows = []
            for method in ("CoPE", "FSR-PC"):
                rows.append(run_episode(
                    scenario,
                    method=method,
                    client=OracleModelClient(),
                    episode_dir=Path(tmp) / method,
                ))
        self.assertTrue(all(row["metrics"]["task_completion"] for row in rows))
        self.assertEqual(rows[0]["final_state_fingerprint"], rows[1]["final_state_fingerprint"])
        self.assertEqual(
            [event["exogenous_fingerprint"] for event in rows[0]["events"]],
            [event["exogenous_fingerprint"] for event in rows[1]["events"]],
        )

    def test_budget_failure_is_primary_task_failure(self):
        scenario = build_scenario(spec(slots=48, depth=6, budget=4096))
        with tempfile.TemporaryDirectory() as tmp:
            cope = run_episode(
                scenario,
                method="CoPE",
                client=OracleModelClient(enforce_budget=True),
                episode_dir=Path(tmp) / "CoPE",
            )
            fsrpc = run_episode(
                scenario,
                method="FSR-PC",
                client=OracleModelClient(enforce_budget=True),
                episode_dir=Path(tmp) / "FSR-PC",
            )
        self.assertTrue(cope["metrics"]["task_completion"])
        self.assertFalse(fsrpc["metrics"]["task_completion"])
        self.assertEqual(fsrpc["metrics"]["first_failure"], "truncated")
        report = analyse([cope, fsrpc], "test")
        self.assertEqual(report["primary"]["task_completion"]["CoPE"]["success"], 1)
        self.assertEqual(report["primary"]["task_completion"]["FSR-PC"]["success"], 0)


if __name__ == "__main__":
    unittest.main()
