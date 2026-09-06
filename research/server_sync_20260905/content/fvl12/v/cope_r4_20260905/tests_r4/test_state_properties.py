"""Hand-derived recovery properties, separate from the shared-oracle R3 tests."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from cope.lineage_benchmark.models import ScenarioSpec
from cope.lineage_benchmark.reference import reference_transition
from cope.lineage_benchmark.state import (
    StateValidationError,
    active_plan,
    apply_patch_document,
    state_semantic_match,
    validate_regenerated_transition,
    validate_state,
)
from cope.lineage_benchmark.task import ROOT_SLOT_ID, build_scenario, oracle_patch


ROOT_PLAN = [
    {"object": "butter", "target": "basket_B", "role": "primary_order"},
    {"object": "milk", "target": "basket_A", "role": "receipt_token"},
    {"object": "yogurt", "target": "basket_A", "role": "closure_token"},
]
D1 = "order-critical/detour-01"
D2 = "order-critical/detour-02"


class StatePropertyTests(unittest.TestCase):
    def setUp(self):
        self.scenario = build_scenario(ScenarioSpec(
            seed=0, profile="r4-unit", initial_slots=8, lineage_depth=2,
            max_output_tokens=100000, model_timeout_s=30.0,
        ))
        self.critical = self.scenario.critical_logical_id

    def transition(self, state, event):
        return apply_patch_document(
            state, oracle_patch(state, event), event, self.critical,
        )

    def trajectory(self):
        states = [self.scenario.initial_state]
        for event in self.scenario.events:
            states.append(self.transition(states[-1], event))
        return states

    def test_seven_event_trajectory_has_hand_derived_modes_and_plan(self):
        states = self.trajectory()
        self.assertEqual(len(self.scenario.events), 7)
        expected_modes = [
            {ROOT_SLOT_ID: "active"},
            {ROOT_SLOT_ID: "suspended"},
            {ROOT_SLOT_ID: "active"},
            {ROOT_SLOT_ID: "overridden", D1: "active"},
            {ROOT_SLOT_ID: "overridden", D1: "overridden", D2: "active"},
            {ROOT_SLOT_ID: "overridden", D1: "overridden", D2: "suspended"},
            {ROOT_SLOT_ID: "overridden", D1: "overridden", D2: "active"},
            {ROOT_SLOT_ID: "active", D1: "expired", D2: "expired"},
        ]
        reference = self.scenario.initial_state
        for index, (state, modes) in enumerate(zip(states, expected_modes)):
            with self.subTest(event=index):
                self.assertEqual(state.revision, index)
                self.assertEqual(
                    {sid: slot.mode for sid, slot in state.slots.items()
                     if slot.kind == "workflow"}, modes,
                )
                self.assertEqual(validate_state(state, self.critical), [])
                if index:
                    reference = reference_transition(
                        reference, self.scenario.events[index - 1], self.critical,
                    )
                self.assertEqual(reference.to_dict(), state.to_dict())
        self.assertEqual(active_plan(states[-1], self.critical), ROOT_PLAN)
        self.assertEqual(active_plan(reference, self.critical), ROOT_PLAN)
        self.assertEqual(active_plan(states[3], self.critical), [
            {"object": "butter", "target": "basket_C", "role": "primary_order"},
            {"object": "milk", "target": "basket_A", "role": "receipt_token"},
            {"object": "yogurt", "target": "basket_C", "role": "closure_token"},
        ])

    def test_suspend_restore_preserves_same_occurrence_payload_and_edges(self):
        states = self.trajectory()
        for before, suspended, restored, sid in (
            (states[0], states[1], states[2], ROOT_SLOT_ID),
            (states[4], states[5], states[6], D2),
        ):
            with self.subTest(slot_id=sid):
                self.assertEqual(set(before.slots), set(restored.slots))
                self.assertEqual(before.slots[sid].slot_id, restored.slots[sid].slot_id)
                self.assertEqual(before.slots[sid].payload, restored.slots[sid].payload)
                self.assertEqual(before.slots[sid].lineage, restored.slots[sid].lineage)
                self.assertEqual(suspended.slots[sid].mode, "suspended")
                self.assertEqual(restored.slots[sid].mode, "active")

    def test_nested_edges_and_full_lifecycle_history_are_exact(self):
        final = self.trajectory()[-1]
        self.assertEqual(final.slots[ROOT_SLOT_ID].lineage, {
            "parent_id": None, "root_id": ROOT_SLOT_ID, "depth": 0,
            "child_ids": [D1],
        })
        self.assertEqual(final.slots[D1].lineage, {
            "parent_id": ROOT_SLOT_ID, "root_id": ROOT_SLOT_ID, "depth": 1,
            "child_ids": [D2],
        })
        self.assertEqual(final.slots[D2].lineage, {
            "parent_id": D1, "root_id": ROOT_SLOT_ID, "depth": 2, "child_ids": [],
        })
        # Literal expected histories are not produced by either transition helper.
        expected = {
            ROOT_SLOT_ID: [
                ("task-initialization", "Create", None, "active",
                 "registered persistent slot order-critical/root"),
                ("seed-0000/e01", "Suspend", "active", "suspended", "temporary station outage"),
                ("seed-0000/e02", "Restore", "suspended", "active", "original station revalidated"),
                ("seed-0000/e03", "Override", "active", "overridden", "temporary detour level 1"),
                ("seed-0000/e07", "RestoreRoot", "overridden", "active",
                 "all temporary detours withdrawn; original order reinstated"),
            ],
            D1: [
                ("seed-0000/e03", "InsertOverride", "active", "active", "temporary detour level 1"),
                ("seed-0000/e04", "Override", "active", "overridden", "temporary detour level 2"),
                ("seed-0000/e07", "ExpireDetour", "overridden", "expired",
                 "all temporary detours withdrawn; original order reinstated"),
            ],
            D2: [
                ("seed-0000/e04", "InsertOverride", "active", "active", "temporary detour level 2"),
                ("seed-0000/e05", "Suspend", "active", "suspended", "brief hold on deepest detour"),
                ("seed-0000/e06", "Restore", "suspended", "active", "deepest detour revalidated"),
                ("seed-0000/e07", "ExpireDetour", "active", "expired",
                 "all temporary detours withdrawn; original order reinstated"),
            ],
        }
        for sid, entries in expected.items():
            wanted = tuple({
                "seq": index, "event_id": event_id, "operation": operation,
                "mode_before": before, "mode_after": after, "detail": detail,
            } for index, (event_id, operation, before, after, detail)
                in enumerate(entries, 1))
            self.assertEqual(final.slots[sid].history, wanted)

    def test_same_first_action_does_not_mask_wrong_milk_yogurt_continuation(self):
        states = self.trajectory()
        detour_plan = active_plan(states[6], self.critical)
        root_plan = active_plan(states[7], self.critical)
        self.assertEqual(detour_plan[0], root_plan[0])
        self.assertEqual([a["target"] for a in detour_plan[1:]], ["basket_B", "basket_C"])
        self.assertEqual([a["target"] for a in root_plan[1:]], ["basket_A", "basket_A"])
        wrong = deepcopy(states[7])
        wrong.slots[ROOT_SLOT_ID].payload["plan"] = detour_plan
        self.assertFalse(state_semantic_match(wrong, states[7]))
        self.assertNotEqual(active_plan(wrong, self.critical), ROOT_PLAN)

    def test_untouched_archives_and_safety_remain_exact_every_event(self):
        initial = self.scenario.initial_state
        untouched = {
            sid: deepcopy(slot.to_dict()) for sid, slot in initial.slots.items()
            if slot.kind in {"order_archive", "safety"}
        }
        for state in self.trajectory():
            for sid, expected in untouched.items():
                self.assertEqual(state.slots[sid].to_dict(), expected)

    def test_safety_cannot_be_suspended_by_a_well_formed_typed_operation(self):
        initial = self.scenario.initial_state
        event = self.scenario.events[0]
        raw = oracle_patch(initial, event)
        raw["ops"][0]["slot_id"] = "safety/no-repeat"
        before = deepcopy(initial.to_dict())
        with self.assertRaises(StateValidationError):
            apply_patch_document(initial, raw, event, self.critical)
        self.assertEqual(initial.to_dict(), before)

    def test_regeneration_rejects_nested_archive_mutation(self):
        initial = self.scenario.initial_state
        event = self.scenario.events[0]
        candidate = reference_transition(initial, event, self.critical)
        candidate.slots["archive/order-0000"].payload["completion_checkpoint"]["verified"] = False
        errors = validate_regenerated_transition(initial, candidate, event, self.critical)
        self.assertTrue(any("immutable archived/safety content changed" in error for error in errors))
        self.assertTrue(initial.slots["archive/order-0000"].payload["completion_checkpoint"]["verified"])

    def test_stale_revision_rejected_without_any_original_mutation(self):
        initial = self.scenario.initial_state
        event = self.scenario.events[0]
        raw = oracle_patch(initial, event)
        raw["base_revision"] = 1
        before = deepcopy(initial.to_dict())
        with self.assertRaisesRegex(StateValidationError, "stale"):
            apply_patch_document(initial, raw, event, self.critical)
        self.assertEqual(initial.to_dict(), before)

    def test_failure_after_first_multiop_keeps_original_and_patch_unchanged(self):
        initial = self.scenario.initial_state
        event = self.scenario.events[2]
        raw = oracle_patch(initial, event)
        # Insertion succeeds internally before restore fails on an active child.
        raw["ops"].append({"op": "restore", "slot_id": D1})
        before, raw_before = deepcopy(initial.to_dict()), deepcopy(raw)
        with self.assertRaisesRegex(StateValidationError, "cannot restore"):
            apply_patch_document(initial, raw, event, self.critical)
        self.assertEqual(initial.to_dict(), before)
        self.assertEqual(raw, raw_before)
        self.assertNotIn(D1, initial.slots)
        self.assertEqual(initial.slots[ROOT_SLOT_ID].lineage["child_ids"], [])

    def test_committed_snapshot_does_not_alias_prior_nested_state_or_patch(self):
        initial = self.scenario.initial_state
        event = self.scenario.events[2]
        raw = oracle_patch(initial, event)
        before, raw_before = deepcopy(initial.to_dict()), deepcopy(raw)
        candidate = apply_patch_document(initial, raw, event, self.critical)
        candidate.slots["archive/order-0000"].payload["completion_checkpoint"]["verified"] = False
        candidate.slots[D1].payload["plan"][0]["target"] = "basket_A"
        candidate.slots[ROOT_SLOT_ID].history[0]["detail"] = "changed only in candidate"
        self.assertEqual(initial.to_dict(), before)
        self.assertEqual(raw, raw_before)

    def test_partial_completion_exact_prefix_not_reexecuted_after_restore(self):
        final = self.trajectory()[-1]
        for count in range(4):
            self.assertEqual(
                active_plan(final, self.critical, completed_actions=ROOT_PLAN[:count]),
                ROOT_PLAN[count:],
            )
        self.assertEqual(active_plan(final, self.critical), ROOT_PLAN)

    def test_partial_completion_wrong_target_or_order_fails_closed(self):
        final = self.trajectory()[-1]
        wrong_target = deepcopy(ROOT_PLAN[:1])
        wrong_target[0]["target"] = "basket_C"
        for completed in (wrong_target, [ROOT_PLAN[1]], ROOT_PLAN + ROOT_PLAN[:1], [{"object": "butter"}]):
            with self.subTest(completed=completed):
                with self.assertRaises(StateValidationError):
                    active_plan(final, self.critical, completed_actions=completed)

    def test_reference_does_not_call_patch_executor_and_owns_its_snapshot(self):
        initial = self.scenario.initial_state
        before = deepcopy(initial.to_dict())
        with patch("cope.lineage_benchmark.state.apply_patch_document", side_effect=AssertionError("shared executor")):
            candidate = reference_transition(initial, self.scenario.events[0], self.critical)
        self.assertEqual(candidate.slots[ROOT_SLOT_ID].mode, "suspended")
        candidate.slots[ROOT_SLOT_ID].payload["plan"][0]["target"] = "basket_C"
        self.assertEqual(initial.to_dict(), before)


if __name__ == "__main__":
    unittest.main()
