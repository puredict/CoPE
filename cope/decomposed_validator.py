from __future__ import annotations

import copy
from typing import Any, Mapping


PREDICATE_GROUPS = (
    "authorization_noop",
    "version_evidence",
    "identity_lifecycle",
    "goal_consistency",
    "progress_preservation",
    "action_continuity",
    "restoration_entity",
    "unaffected_scope",
)


class DecomposedValidationError(ValueError):
    def __init__(self, violations: Mapping[str, list[str]]) -> None:
        self.violations = {key: list(value) for key, value in violations.items() if value}
        super().__init__("; ".join(f"{key}:{'|'.join(value)}" for key, value in self.violations.items()))


def _without_history(state: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in state.items() if key != "action_history"}


def _authorized(state: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
    return bool(
        event.get("issuer") == "task_owner"
        and int(event.get("authority", -1)) >= 100
        and int(event.get("input_state_version", -1)) == int(state["state_version"])
        and event.get("duplicate_delivery") is not True
    )


def _records(rows: Any, group: str, add) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) or not isinstance(row.get("id"), str) for row in rows):
        add(group, "records_malformed")
        return {}
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        add(group, "stable_ids_not_unique")
    return {row["id"]: dict(row) for row in rows}


def _goal_atoms(value: Any, add) -> list[dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != {"all"} or not isinstance(value.get("all"), list):
        add("goal_consistency", "goal_shape_invalid")
        return []
    atoms = value["all"]
    if any(not isinstance(atom, Mapping) or set(atom) != {"predicate", "arguments"} for atom in atoms):
        add("goal_consistency", "goal_atom_invalid")
        return []
    normalized = [dict(atom) for atom in atoms]
    if len({repr(atom) for atom in normalized}) != len(normalized):
        add("goal_consistency", "goal_atoms_duplicated")
    return normalized


def decomposed_violations(
    candidate: Mapping[str, Any], state: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, list[str]]:
    violations = {group: [] for group in PREDICATE_GROUPS}

    def add(group: str, code: str) -> None:
        if code not in violations[group]:
            violations[group].append(code)

    required = {
        "schema_version", "state_version", "current_goal", "entities", "commitments",
        "progress_ledger", "plan", "pending_restorations", "evidence_versions",
    }
    if not isinstance(candidate, Mapping) or set(candidate) != required:
        add("authorization_noop", "candidate_shape_invalid")
        return violations
    pre = _without_history(state)
    event_type = event.get("event_type")
    authorized = _authorized(state, event)
    if not authorized or event_type == "no_op":
        for field in sorted(required):
            if candidate.get(field) != pre.get(field):
                add("authorization_noop", f"unexpected_change:{field}")
        return violations

    if candidate.get("schema_version") != pre.get("schema_version"):
        add("version_evidence", "state_schema_changed")
    if candidate.get("state_version") != int(state["state_version"]) + 1:
        add("version_evidence", "state_version_not_advanced_once")
    required_evidence = {
        "event_id": event.get("event_id"),
        "world_version": event.get("world_version"),
        "input_state_version": event.get("input_state_version"),
    }
    if candidate.get("evidence_versions") != required_evidence:
        add("version_evidence", "evidence_not_bound_to_event")

    pre_commitments = _records(pre.get("commitments"), "identity_lifecycle", add)
    post_commitments = _records(candidate.get("commitments"), "identity_lifecycle", add)
    pre_entities = _records(pre.get("entities"), "restoration_entity", add)
    post_entities = _records(candidate.get("entities"), "restoration_entity", add)
    pre_commitment_order = list(pre_commitments)
    post_commitment_order = [row.get("id") for row in candidate.get("commitments", []) if isinstance(row, Mapping)]
    pre_entity_order = list(pre_entities)
    post_entity_order = [row.get("id") for row in candidate.get("entities", []) if isinstance(row, Mapping)]
    pre_goal = _goal_atoms(pre.get("current_goal"), add)
    post_goal = _goal_atoms(candidate.get("current_goal"), add)

    target_id = event.get("target_id")
    override_id = event.get("override_id")
    replacement_id = event.get("replacement_id")
    affected_ids = {item for item in (target_id, override_id, replacement_id) if isinstance(item, str)}
    for record_id, record in pre_commitments.items():
        if record_id in post_commitments and set(post_commitments[record_id]) != set(record):
            add("identity_lifecycle", f"commitment_field_set_changed:{record_id}")
        if record_id not in affected_ids and post_commitments.get(record_id) != record:
            add("unaffected_scope", f"commitment_changed:{record_id}")
    expected_ids = set(pre_commitments)
    expected_commitment_order = list(pre_commitment_order)
    if event_type == "replace_commitment" and isinstance(replacement_id, str):
        expected_ids.add(replacement_id)
        if replacement_id not in expected_commitment_order:
            expected_commitment_order.append(replacement_id)
    if event_type == "activate_override" and isinstance(override_id, str):
        expected_ids.add(override_id)
        if override_id not in expected_commitment_order:
            expected_commitment_order.append(override_id)
    if set(post_commitments) != expected_ids:
        add("identity_lifecycle", "commitment_id_set_incorrect")
    if post_commitment_order != expected_commitment_order:
        add("identity_lifecycle", "commitment_order_incorrect")

    expected_goal = copy.deepcopy(pre_goal)

    def remove_goal(predicate: str, grounding: list[str]) -> None:
        atom = {"predicate": predicate, "arguments": list(grounding)}
        if expected_goal.count(atom) != 1:
            add("goal_consistency", "pre_goal_target_not_unique")
        elif atom in expected_goal:
            expected_goal.remove(atom)

    def append_goal(predicate: str, grounding: list[str]) -> None:
        expected_goal.append({"predicate": predicate, "arguments": list(grounding)})

    expected_plan = copy.deepcopy(pre.get("plan"))
    expected_restorations = copy.deepcopy(pre.get("pending_restorations"))
    expected_entity_ids = set(pre_entities)
    expected_entity_order = list(pre_entity_order)
    for entity_id, entity in pre_entities.items():
        if entity_id in post_entities and set(post_entities[entity_id]) != set(entity):
            add("restoration_entity", f"entity_field_set_changed:{entity_id}")

    if event_type == "cancel_commitment":
        target = post_commitments.get(str(target_id), {})
        before_target = pre_commitments.get(str(target_id), {})
        if not before_target or target.get("lifecycle_status") != "cancelled":
            add("identity_lifecycle", "cancel_target_not_cancelled")
        for field, value in before_target.items():
            if field != "lifecycle_status" and target.get(field) != value:
                add("identity_lifecycle", f"cancel_target_field_changed:{field}")
        if before_target:
            remove_goal(str(before_target.get("predicate")), list(before_target.get("grounding", [])))
        expected_plan = []
    elif event_type == "replace_commitment":
        before_target = pre_commitments.get(str(target_id), {})
        target = post_commitments.get(str(target_id), {})
        replacement = post_commitments.get(str(replacement_id), {})
        grounding = event.get("replacement_grounding")
        if target.get("lifecycle_status") != "superseded":
            add("identity_lifecycle", "replacement_target_not_superseded")
        for field, value in before_target.items():
            if field != "lifecycle_status" and target.get(field) != value:
                add("identity_lifecycle", f"replacement_target_field_changed:{field}")
        required_replacement = {
            "id": replacement_id,
            "predicate": "deliver",
            "grounding": grounding,
            "lifecycle_status": "active",
            "source": before_target.get("source"),
            "owner": before_target.get("owner"),
            "authority": before_target.get("authority"),
            "valid_from": event.get("event_id"),
            "valid_until": before_target.get("valid_until"),
            "dependencies": before_target.get("dependencies"),
            "support_links": before_target.get("support_links"),
            "override_links": [],
            "supersession_links": [target_id],
        }
        if replacement != required_replacement:
            add("identity_lifecycle", "replacement_record_incorrect")
        if before_target and isinstance(grounding, list):
            remove_goal(str(before_target.get("predicate")), list(before_target.get("grounding", [])))
            append_goal("deliver", grounding)
            expected_plan = [{
                "action_id": "place-c", "skill": "place", "arguments": list(grounding),
                "status": "pending", "cancellation_reason": None,
            }]
            expected_entity_ids.add(str(grounding[0]))
            if str(grounding[0]) not in expected_entity_order:
                expected_entity_order.append(str(grounding[0]))
            if post_entities.get(str(grounding[0])) != {"id": grounding[0], "kind": "object"}:
                add("restoration_entity", "replacement_entity_missing_or_wrong")
    elif event_type == "activate_override":
        before_target = pre_commitments.get(str(target_id), {})
        target = post_commitments.get(str(target_id), {})
        override = post_commitments.get(str(override_id), {})
        if target.get("lifecycle_status") != "suspended":
            add("identity_lifecycle", "override_target_not_suspended")
        for field, value in before_target.items():
            if field != "lifecycle_status" and target.get(field) != value:
                add("identity_lifecycle", f"override_target_field_changed:{field}")
        required_override = copy.deepcopy(before_target)
        required_override.update({
            "id": override_id, "predicate": "prohibit_touch", "lifecycle_status": "active",
            "valid_from": event.get("event_id"), "override_links": [target_id],
            "supersession_links": [],
        })
        if override != required_override:
            add("identity_lifecycle", "override_record_incorrect")
        grounding = list(before_target.get("grounding", []))
        if before_target:
            remove_goal(str(before_target.get("predicate")), grounding)
            append_goal("prohibit_touch", grounding)
        restoration = {"target_id": target_id, "override_id": override_id}
        expected_restorations.append(restoration)
        if event.get("conflicts_with_action"):
            expected_plan = copy.deepcopy(pre.get("plan"))
            found = False
            for action in expected_plan:
                if action.get("status") == "executing":
                    action["status"] = "cancelled"
                    action["cancellation_reason"] = event.get("cancellation_reason")
                    found = True
            if not found:
                add("action_continuity", "conflict_has_no_executing_action")
        else:
            expected_plan = []
    elif event_type == "release_override":
        before_target = pre_commitments.get(str(target_id), {})
        before_override = pre_commitments.get(str(override_id), {})
        target = post_commitments.get(str(target_id), {})
        override = post_commitments.get(str(override_id), {})
        grounding = event.get("world_facts", {}).get("deliver:b:grounding", before_target.get("grounding"))
        required_target = copy.deepcopy(before_target)
        required_target.update({"lifecycle_status": "active", "grounding": grounding})
        if target != required_target:
            add("identity_lifecycle", "released_target_record_incorrect")
        required_override = copy.deepcopy(before_override)
        required_override["lifecycle_status"] = "expired"
        if override != required_override:
            add("identity_lifecycle", "released_override_record_incorrect")
        if before_override:
            remove_goal(str(before_override.get("predicate")), list(before_override.get("grounding", [])))
        if isinstance(grounding, list):
            append_goal("deliver", grounding)
            expected_plan = [{
                "action_id": "place-b", "skill": "place", "arguments": list(grounding),
                "status": "pending", "cancellation_reason": None,
            }]
            expected_entity_ids.add(str(grounding[1]))
            if str(grounding[1]) not in expected_entity_order:
                expected_entity_order.append(str(grounding[1]))
            if str(grounding[1]) not in pre_entities and post_entities.get(str(grounding[1])) != {"id": grounding[1], "kind": "region"}:
                add("restoration_entity", "released_region_entity_missing_or_wrong")
        restoration = {"target_id": target_id, "override_id": override_id}
        if expected_restorations.count(restoration) != 1:
            add("restoration_entity", "pre_release_restoration_not_unique")
        elif restoration in expected_restorations:
            expected_restorations.remove(restoration)
    elif event_type == "irrelevant_world_change":
        if candidate.get("commitments") != pre.get("commitments"):
            add("unaffected_scope", "irrelevant_event_changed_commitments")
        expected_goal = copy.deepcopy(pre_goal)
        expected_plan = copy.deepcopy(pre.get("plan"))
    else:
        add("authorization_noop", "unsupported_event_type")

    if post_goal != expected_goal:
        add("goal_consistency", "goal_does_not_match_event_effect")
    if candidate.get("plan") != expected_plan:
        add("action_continuity", "plan_does_not_match_event_continuity")
    if candidate.get("pending_restorations") != expected_restorations:
        add("restoration_entity", "restoration_records_incorrect")
    if set(post_entities) != expected_entity_ids:
        add("restoration_entity", "entity_id_set_incorrect")
    if post_entity_order != expected_entity_order:
        add("restoration_entity", "entity_order_incorrect")
    for entity_id, entity in pre_entities.items():
        if post_entities.get(entity_id) != entity:
            add("unaffected_scope", f"entity_changed:{entity_id}")

    pre_progress = pre.get("progress_ledger")
    post_progress = candidate.get("progress_ledger")
    if not isinstance(pre_progress, list) or not isinstance(post_progress, list):
        add("progress_preservation", "progress_ledger_malformed")
    else:
        if len(post_progress) != len(pre_progress):
            add("progress_preservation", "progress_record_set_changed")
        pre_by_id = {row.get("milestone_id"): row for row in pre_progress if isinstance(row, Mapping)}
        post_by_id = {row.get("milestone_id"): row for row in post_progress if isinstance(row, Mapping)}
        if set(pre_by_id) != set(post_by_id):
            add("progress_preservation", "progress_ids_changed")
        for milestone_id, record in pre_by_id.items():
            physically_false = event.get("world_facts", {}).get(milestone_id) is False
            if not physically_false and post_by_id.get(milestone_id) != record:
                add("progress_preservation", f"preserved_progress_changed:{milestone_id}")

    return violations


def validate_decomposed(
    candidate: Mapping[str, Any], state: Mapping[str, Any], event: Mapping[str, Any]
) -> str:
    violations = decomposed_violations(candidate, state, event)
    if any(violations.values()):
        raise DecomposedValidationError(violations)
    executing = [action for action in candidate["plan"] if action.get("status") == "executing"]
    cancelled = [action for action in candidate["plan"] if action.get("status") == "cancelled"]
    pending = [action for action in candidate["plan"] if action.get("status") == "pending"]
    if cancelled:
        return f"CANCEL:{cancelled[0]['action_id']}"
    if executing:
        return f"CONTINUE:{executing[0]['action_id']}"
    if pending:
        return f"PLAN:{pending[0]['action_id']}"
    return "HALT"
