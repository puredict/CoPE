from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from cope.libero_predicate_validator import create_libero_predicate_validator
from cope.schema import ConstraintSlot
from cope.semantic_cancellation import (
    apply_oracle_cancellation_patch,
    build_cancellation_event,
    build_oracle_cancellation_state,
    compile_execution_directive,
    validate_oracle_cancellation_state,
)
from cope.semantic_materialization import (
    materialize_cancellation_receipt,
    materialize_replacement_receipt,
)
from cope.semantic_replacement import (
    MilestoneEvent,
    apply_oracle_replacement_patch,
    build_oracle_full_state,
    build_replacement_event,
    compile_controller_prompt,
    validate_oracle_full_state,
)
from cope.serialization import deserialize_state
from cope.types import InformationBudget, RecoveryInput, canonical_json, stable_hash


SEMANTIC_CONFIG_SCHEMA = "cope-semantic-task1-pilot-config-v1"
DEVELOPMENT_STATE_IDS = frozenset(range(5))
EVENT_TYPES = frozenset({"replace_pending_goal", "cancel_pending_goal"})
DONE_OBJECT = "cream_cheese_1"
PENDING_OBJECT = "butter_1"
REPLACEMENT_OBJECT = "alphabet_soup_1"
REQUIRED_STABLE_STEPS = 5


@dataclass(frozen=True)
class LoadedSemanticConfig:
    row: dict[str, str]
    path: Path
    sha256: str
    observation_fields: tuple[str, ...]
    event_types: frozenset[str]
    reserved_state_ids: frozenset[int]
    reserve_manifest_sha256: str

    @property
    def predicate_engine_config(self) -> dict[str, Any]:
        return {
            "predicate_snapshot": {
                "enabled": True,
                "test_only": False,
                "allow_test_packets": False,
                "task_suite": self.row["task_suite"],
                "task_id": int(self.row["task_id"]),
                "producer_commit": self.row["predicate_producer_commit"],
            }
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_semantic_config(path: Path, *, repo_root: Path) -> LoadedSemanticConfig:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError("semantic config must contain exactly one row")
    row = dict(rows[0])
    if row.get("schema_version") != SEMANTIC_CONFIG_SCHEMA:
        raise ValueError("unsupported semantic config schema")
    if (row.get("task_suite"), row.get("task_id")) != ("libero_10", "1"):
        raise ValueError("live semantic runner is locked to LIBERO-10 task 1")
    observation_fields = tuple(item for item in row["observation_fields"].split(";") if item)
    if "predicate_snapshot" not in observation_fields:
        raise ValueError("semantic config omits predicate_snapshot from the information budget")
    event_types = frozenset(item for item in row["event_types"].split(";") if item)
    if event_types != EVENT_TYPES:
        raise ValueError("semantic config event families differ from the frozen runner contract")
    reserved_state_ids = frozenset(int(item) for item in row["reserved_state_ids"].split(";") if item)
    if reserved_state_ids != frozenset({25, 26}):
        raise ValueError("semantic config reserve identity differs from the frozen manifest")
    if row.get("rollout_authorized", "").lower() != "false":
        raise ValueError("development integration requires the reserved rollout lock to remain closed")
    if row.get("predicate_snapshot_schema") != "cope-libero-predicate-snapshot-v1":
        raise ValueError("semantic config predicate packet schema is not pinned")
    if row.get("predicate_factory") != (
        "cope.libero_predicate_validator:create_libero_predicate_validator"
    ):
        raise ValueError("semantic config predicate factory is not the production validator")
    for path_key, digest_key in (
        ("bddl_path", "bddl_sha256"),
        ("init_states_path", "init_states_sha256"),
    ):
        artifact = Path(row[path_key])
        if not artifact.is_file() or sha256_file(artifact) != row[digest_key]:
            raise ValueError(f"semantic config artifact verification failed for {path_key}")
    reserve_path = repo_root / row["pilot_manifest_path"]
    with reserve_path.open(newline="", encoding="utf-8") as handle:
        reserve_rows = list(csv.DictReader(handle))
    if (
        {int(item["state_id"]) for item in reserve_rows} != reserved_state_ids
        or any(item.get("status") != "reserved_uninspected" for item in reserve_rows)
    ):
        raise ValueError("reserved-state manifest is not intact")
    return LoadedSemanticConfig(
        row=row,
        path=path,
        sha256=sha256_file(path),
        observation_fields=observation_fields,
        event_types=event_types,
        reserved_state_ids=reserved_state_ids,
        reserve_manifest_sha256=sha256_file(reserve_path),
    )


def validate_case_rows(rows: Sequence[Mapping[str, str]]) -> None:
    expected = {(state_id, event_type) for state_id in DEVELOPMENT_STATE_IDS for event_type in EVENT_TYPES}
    observed: set[tuple[int, str]] = set()
    case_ids: set[str] = set()
    for row in rows:
        state_id = int(row["state_id"])
        event_type = row["event_type"]
        if state_id not in DEVELOPMENT_STATE_IDS:
            raise ValueError(f"state {state_id} is outside the consumed development range 0--4")
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unsupported event type {event_type!r}")
        if row["case_id"] in case_ids:
            raise ValueError("duplicate case_id")
        if row.get("done_object") != DONE_OBJECT or row.get("pending_object") != PENDING_OBJECT:
            raise ValueError("case manifest atomic commitments differ from preregistration")
        if int(row.get("stable_steps", 0)) != REQUIRED_STABLE_STEPS:
            raise ValueError("case manifest stability threshold differs from preregistration")
        expected_replacement = REPLACEMENT_OBJECT if event_type == "replace_pending_goal" else ""
        if row.get("replacement_object", "") != expected_replacement:
            raise ValueError("case manifest replacement assignment differs from preregistration")
        case_ids.add(row["case_id"])
        observed.add((state_id, event_type))
    if observed != expected or len(rows) != len(expected):
        raise ValueError("case manifest must be the frozen 5-state x 2-event assignment")


def recovery_input_bytes(recovery_input: RecoveryInput) -> bytes:
    return canonical_json(recovery_input.as_payload()).encode("utf-8")


def make_paired_recovery_inputs(
    *,
    pair_key: str,
    original_task: str,
    observation: Mapping[str, Any],
    event: Mapping[str, Any],
    public_action_history: Sequence[Mapping[str, Any]],
    task_progress: Mapping[str, Any],
    observation_fields: Sequence[str],
) -> tuple[RecoveryInput, RecoveryInput, bytes]:
    budget = InformationBudget(
        event_fields=tuple(sorted(event)),
        history_fields=("policy_step", "environment_action"),
        observation_fields=tuple(observation_fields),
        max_high_level_calls=0,
        max_prompt_tokens=1,
        max_completion_tokens=1,
    )
    payload = {
        "schema_version": "recovery-input-v1",
        "pair_key": pair_key,
        "original_task": original_task,
        "observation": dict(observation),
        "event": dict(event),
        "public_action_history": tuple(dict(item) for item in public_action_history),
        "task_progress": dict(task_progress),
        "information_budget": budget,
    }
    native = RecoveryInput(**payload)
    cope = RecoveryInput(**payload)
    native_bytes = recovery_input_bytes(native)
    cope_bytes = recovery_input_bytes(cope)
    if native_bytes != cope_bytes or native.input_hash != cope.input_hash:
        raise RuntimeError("native FSR and post-CoPE RecoveryInput differ")
    return native, cope, native_bytes


def _accepted_validate_compile(
    state: Mapping[str, Any],
    event: Mapping[str, Any],
    *,
    event_type: str,
    physically_true_objects: Sequence[str],
) -> Any:
    previous_state_version = int(event["valid_from_state_version"])
    if event_type == "replace_pending_goal":
        validate_oracle_full_state(
            state,
            event,
            previous_state_version=previous_state_version,
            physically_true_objects=physically_true_objects,
        )
        return compile_controller_prompt(state)
    if event_type == "cancel_pending_goal":
        validate_oracle_cancellation_state(
            state,
            event,
            previous_state_version=previous_state_version,
            physically_true_objects=physically_true_objects,
        )
        return compile_execution_directive(state)
    raise ValueError(f"unsupported event type {event_type!r}")


def run_semantic_wiring(
    *,
    row: Mapping[str, str],
    config: LoadedSemanticConfig,
    original_task: str,
    observation: Mapping[str, Any],
    public_action_history: Sequence[Mapping[str, Any]],
    independently_logged_predicates: Mapping[str, bool],
    simulator_state_before: str,
    controller_action_count_before: int,
) -> dict[str, Any]:
    state_id = int(row["state_id"])
    if state_id not in DEVELOPMENT_STATE_IDS:
        raise ValueError("reserved or unregistered state access rejected")
    milestone = MilestoneEvent(
        policy_step=int(observation["predicate_snapshot"]["policy_step"]),
        done_object=row["done_object"],
        pending_object=row["pending_object"],
        stable_steps=int(row["stable_steps"]),
    )
    if row["event_type"] == "replace_pending_goal":
        event = build_replacement_event(
            milestone,
            pair_key=row["case_id"],
            replacement_object=row["replacement_object"],
        )
    else:
        event = build_cancellation_event(milestone, pair_key=row["case_id"])
    packet = observation.get("predicate_snapshot")
    if not isinstance(packet, Mapping) or packet.get("event_id") != event["event_id"]:
        raise ValueError("live packet is not bound to the semantic event")
    if packet.get("test_only") is not False or packet.get("source_kind") != "live_libero_eval_predicate":
        raise ValueError("production path rejects fake or non-live predicate packets")
    if packet.get("policy_step") != event.get("world_version"):
        raise ValueError("live packet policy step is not bound to the semantic event")
    if packet.get("observation_sha256") != observation.get("sha256"):
        raise ValueError("live packet is not bound to the outer RGB observation")
    if packet.get("simulator_state_sha256") != simulator_state_before:
        raise ValueError("live packet is not bound to the probed simulator state")
    if packet.get("producer_commit") != config.row["predicate_producer_commit"]:
        raise ValueError("live packet producer differs from the pinned semantic config")
    packet_predicates = {
        str(item["arguments"][0]): bool(item["value"])
        for item in packet["predicates"]
        if item.get("predicate") == "in" and len(item.get("arguments", ())) == 2
    }
    if packet_predicates != dict(independently_logged_predicates):
        raise ValueError("independent predicate log differs from the live packet")
    physically_true = tuple(sorted(name for name, value in independently_logged_predicates.items() if value))
    native_input, cope_input, input_bytes = make_paired_recovery_inputs(
        pair_key=row["case_id"],
        original_task=original_task,
        observation=observation,
        event=event,
        public_action_history=public_action_history,
        task_progress={
            "source": "live_libero_eval_predicate",
            "physically_true_objects": list(physically_true),
            "simulator_state_sha256": simulator_state_before,
            "controller_action_count": int(controller_action_count_before),
        },
        observation_fields=config.observation_fields,
    )
    validator = create_libero_predicate_validator(config.predicate_engine_config)
    if validator.metadata.get("is_fake") is not False:
        raise RuntimeError("production validator unexpectedly advertises fake metadata")

    # Each branch consumes its event from its own decode of the canonical
    # RecoveryInput.  The builders do not receive a side-channel event object.
    native_event = native_input.event
    cope_event = cope_input.event
    if native_event != cope_event or native_event != event:
        raise RuntimeError("paired RecoveryInput event payloads diverged")
    if row["event_type"] == "replace_pending_goal":
        native_state = build_oracle_full_state(native_event)
        receipt = apply_oracle_replacement_patch(
            cope_event, physically_true_objects=physically_true
        )
        materialized_state = materialize_replacement_receipt(
            receipt, cope_event, physically_true_objects=physically_true
        )
    else:
        native_state = build_oracle_cancellation_state(native_event)
        receipt = apply_oracle_cancellation_patch(
            cope_event, physically_true_objects=physically_true
        )
        materialized_state = materialize_cancellation_receipt(
            receipt, cope_event, physically_true_objects=physically_true
        )

    state_before = deserialize_state(receipt["state_before"])
    done_slot = next(slot for slot in state_before.slots if slot.content["arguments"][0] == row["done_object"])
    pending_slot = next(slot for slot in state_before.slots if slot.content["arguments"][0] == row["pending_object"])
    evidence = {"observation": cope_input.observation, "event": cope_event}
    done_value = validator(done_slot, evidence)
    pending_value = validator(pending_slot, evidence)
    if done_value is not True or pending_value is not False:
        raise RuntimeError("production validator did not consume expected atomic task-1 predicates")

    native_directive = _accepted_validate_compile(
        native_state,
        native_event,
        event_type=row["event_type"],
        physically_true_objects=physically_true,
    )
    materialized_directive = _accepted_validate_compile(
        materialized_state,
        cope_event,
        event_type=row["event_type"],
        physically_true_objects=physically_true,
    )
    semantic_pass = all(
        (
            canonical_json(native_state) == canonical_json(materialized_state),
            stable_hash(native_state) == stable_hash(materialized_state),
            native_directive == materialized_directive,
            receipt.get("provider_called") is False,
            receipt.get("transition", {}).get("accepted") is True,
        )
    )
    return {
        "case_id": row["case_id"],
        "state_id": state_id,
        "event_type": row["event_type"],
        "semantic_config_sha256": config.sha256,
        "semantic_config_loaded": True,
        "reserve_manifest_sha256": config.reserve_manifest_sha256,
        "reserved_state_consumed": False,
        "event_id": event["event_id"],
        "policy_step": packet["policy_step"],
        "rgb_sha256": packet["observation_sha256"],
        "simulator_state_sha256": packet["simulator_state_sha256"],
        "producer_commit": packet["producer_commit"],
        "packet_sha256": packet["snapshot_sha256"],
        "packet_source_kind": packet["source_kind"],
        "packet_test_only": packet["test_only"],
        "live_packet_observed": True,
        "packet_matches_independent_log": True,
        "validator_is_fake": validator.metadata["is_fake"],
        "validator_done_value": done_value,
        "validator_pending_value": pending_value,
        "native_recovery_input_sha256": native_input.input_hash,
        "cope_recovery_input_sha256": cope_input.input_hash,
        "recovery_input_byte_identical": recovery_input_bytes(native_input) == recovery_input_bytes(cope_input),
        "recovery_input_bytes": len(input_bytes),
        "native_schema": native_state["schema_version"],
        "materialized_schema": materialized_state["schema_version"],
        "native_state_sha256": stable_hash(native_state),
        "materialized_state_sha256": stable_hash(materialized_state),
        "canonical_states_equal": canonical_json(native_state) == canonical_json(materialized_state),
        "shared_validator_compiler": True,
        "compiled_directive": canonical_json(native_directive),
        "directives_equal": native_directive == materialized_directive,
        "accepted_transition": receipt["transition"]["accepted"],
        "provider_called": receipt["provider_called"],
        "oracle_operation_selector": receipt["oracle_operation_selection"],
        "semantic_pass": semantic_pass,
    }


def finalize_mutation_accounting(
    semantic_result: Mapping[str, Any],
    *,
    simulator_state_before: str,
    simulator_state_after: str,
    controller_action_count_before: int,
    controller_action_count_after: int,
) -> dict[str, Any]:
    result = dict(semantic_result)
    simulator_unchanged = simulator_state_before == simulator_state_after
    actions_unchanged = controller_action_count_before == controller_action_count_after
    post_event_actions = controller_action_count_after - controller_action_count_before
    passed = bool(
        result.get("semantic_pass") is True
        and simulator_unchanged
        and actions_unchanged
        and post_event_actions == 0
    )
    result.update(
        {
            "simulator_state_before": simulator_state_before,
            "simulator_state_after": simulator_state_after,
            "simulator_unchanged_by_semantics": simulator_unchanged,
            "controller_action_count_before": controller_action_count_before,
            "controller_action_count_after": controller_action_count_after,
            "controller_actions_unchanged_by_semantics": actions_unchanged,
            "post_event_policy_actions": post_event_actions,
            "passed": passed,
        }
    )
    return result
