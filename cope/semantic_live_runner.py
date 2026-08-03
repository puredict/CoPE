from __future__ import annotations

import csv
import copy
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from cope.compact_tx import execute_compact_transaction, parse_proposal
from cope.libero_predicate_validator import create_libero_predicate_validator
from cope.operations import apply_patch
from cope.providers.openai_compatible import normalized_raw_request_hash
from cope.schema import (
    ConstraintSlot,
    ConstraintState,
    Expire,
    Insert,
    Override,
    Patch,
    PatchContext,
)
from cope.shared_commit_envelope import SharedEnvelopeError, commit_envelope
from cope.semantic_cancellation import (
    apply_oracle_cancellation_patch,
    build_cancellation_event,
    build_canonical_cancellation_state,
    build_oracle_cancellation_state,
    compile_execution_directive,
    validate_canonical_cancellation_state,
    validate_oracle_cancellation_state,
)
from cope.semantic_materialization import (
    materialize_cancellation_receipt,
    materialize_replacement_receipt,
)
from cope.semantic_replacement import (
    MilestoneEvent,
    apply_oracle_replacement_patch,
    build_canonical_replacement_state,
    build_oracle_full_state,
    build_replacement_event,
    compile_controller_prompt,
    goal_commitment_id,
    validate_canonical_replacement_state,
    validate_oracle_full_state,
)
from cope.serialization import deserialize_state, serialize_state, thaw_json
from cope.types import (
    InformationBudget,
    ProviderInvocation,
    RecoveryInput,
    canonical_json,
    stable_hash,
)


SEMANTIC_CONFIG_SCHEMA = "cope-semantic-task1-pilot-config-v1"
DEVELOPMENT_STATE_IDS = frozenset(range(5))
EVENT_TYPES = frozenset({"replace_pending_goal", "cancel_pending_goal"})
DONE_OBJECT = "cream_cheese_1"
PENDING_OBJECT = "butter_1"
REPLACEMENT_OBJECT = "alphabet_soup_1"
REQUIRED_STABLE_STEPS = 5
X15_MODEL = "qwen/qwen3.5-flash-02-23"
X15_REASONING_EFFORT = "none"
X15_TEMPERATURE = 0.0
X15_SEED = 20260802
X15_COMPLETION_BUDGET = 4096
X15_PROMPT_BUDGET = 12000
X15_TIMEOUT_SECONDS = 90.0
PERSISTENT_STATE_FIELDS = frozenset(
    {
        "schema_version",
        "state_version",
        "current_goal",
        "entities",
        "commitments",
        "progress_ledger",
        "plan",
        "pending_restorations",
        "evidence_versions",
    }
)
SEMANTIC_STATE_FIELDS = PERSISTENT_STATE_FIELDS - {
    "schema_version",
    "state_version",
    "evidence_versions",
}
LIVE_ARMS = ("cope", "neutral_patch", "compact_tx", "fsr_pc")

LIVE_COPE_CONTRACT = """OUTPUT CONTRACT: X15 CoPE live minimum patch.
Return exactly one JSON object and no prose or receipt.
For replace_pending_goal the exact fields are event_id, operation, patch_id,
target_id, replacement_id and operation must be \"Override\".
For cancel_pending_goal the exact fields are event_id, operation, patch_id,
target_id and operation must be \"Expire\".
Copy IDs only from recovery_input.event. target_id is target_commitment_id.
For replacement, replacement_id is the stable commitment ID for predicate \"in\"
with replacement_object and replacement_target, matching the pre_state ID format.
patch_id must be a nonempty fresh identifier and must not claim oracle origin.
Do not return state, history, receipt, hashes, controller actions, or extra fields."""

LIVE_NEUTRAL_CONTRACT = """OUTPUT CONTRACT: neutral-label sparse live patch.
Return exactly one JSON object and no prose or receipt.
For replace_pending_goal the exact fields are event_id, operation, patch_id,
target_id, replacement_id and operation must be "N01".
For cancel_pending_goal the exact fields are event_id, operation, patch_id,
target_id and operation must be "N02".
N01 deactivates only the named target and activates the named replacement; N02
deactivates only the named target without replacement. Copy all IDs from the
event. patch_id is a nonempty fresh identifier. Do not emit CoPE operation
names, state/evidence versions, processed events, state, receipt, hashes,
controller actions, history, or extra fields."""

LIVE_COMPACT_CONTRACT = """OUTPUT CONTRACT: X15 equivalent generic live transaction.
Return exactly one JSON object with schema_version, base_version, event_id, writes.
schema_version is \"generic-compact-transaction-v1\". base_version equals
task_progress.pre_state.state_version and event_id equals event.event_id.
writes is the minimum generic path/value transaction that produces the authorized
post-event persistent state. Legal write objects have exactly op, path, value.
Use only add or replace and the allowlisted commitment/entity/current_goal/plan/
pending_restorations paths. Address existing commitment fields by stable ID,
for example /commitments/goal:butter_1/lifecycle_status. Add a complete new
record at /commitments/+/goal:alphabet_soup_1 or
/entities/+/alphabet_soup_1. Root current_goal, plan, and
pending_restorations writes replace the complete root value. The trusted shared
envelope, not this output, supplies state/evidence versions and event records.
Do not return CoPE operations, transaction metadata, state, history, receipt,
controller actions, or extra fields."""

LIVE_FSR_CONTRACT = """OUTPUT CONTRACT: FSR-PC complete semantic state.
Return exactly one JSON object with exactly these semantic fields: current_goal,
entities, commitments, progress_ledger, plan, pending_restorations. Produce the
complete post-event semantic state from task_progress.pre_state and event.
Preserve witnessed progress and unaffected records. The trusted shared envelope,
not this output, supplies schema/state/evidence versions and event records. Do
not return transaction metadata, action_history, receipt, hashes, controller
actions, patch fields, prose, or extra fields."""


class LearnedSemanticError(ValueError):
    """Fail-closed rejection of a learned live proposal."""


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


def run_oracle_semantic_fixture(
    *,
    row: Mapping[str, str],
    config: LoadedSemanticConfig,
    original_task: str,
    observation: Mapping[str, Any],
    public_action_history: Sequence[Mapping[str, Any]],
    independently_logged_predicates: Mapping[str, bool],
    simulator_state_before: str,
    controller_action_count_before: int,
    authorized_state_ids: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Legacy X04 oracle mechanism fixture; never used by the X15 CLI."""
    state_id = int(row["state_id"])
    allowed_states = (
        DEVELOPMENT_STATE_IDS
        if authorized_state_ids is None
        else frozenset(int(item) for item in authorized_state_ids)
    )
    if not allowed_states:
        raise ValueError("caller-authorized state set cannot be empty")
    if state_id not in allowed_states:
        raise ValueError("state is outside the caller-authorized semantic set")
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


def _persistent_projection(state: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(state[key]) for key in PERSISTENT_STATE_FIELDS}


def build_live_pre_state(event: Mapping[str, Any]) -> dict[str, Any]:
    """Build the trusted persistent state witnessed immediately before X15 Phase A."""

    done = str(event["done_object"])
    pending = str(event["pending_object"])
    event_id = str(event["event_id"])
    genesis = f"{event_id}:genesis"

    def commitment(object_name: str, status: str) -> dict[str, Any]:
        return {
            "id": goal_commitment_id(object_name),
            "type": "task_goal",
            "predicate": "in",
            "grounding": [object_name, "basket_1_contain_region"],
            "lifecycle_status": status,
            "source": "task_owner",
            "owner": "task_owner",
            "authority": 100,
            "valid_from": genesis,
            "valid_until": "task_end",
            "dependencies": [],
            "support_links": [],
            "override_links": [],
            "supersession_links": [],
        }

    entities = [
        {"id": done, "kind": "object"},
        {"id": pending, "kind": "object"},
    ]
    replacement = event.get("replacement_object")
    if isinstance(replacement, str) and replacement:
        entities.append({"id": replacement, "kind": "object"})
    entities.append({"id": "basket_1_contain_region", "kind": "region"})
    version = int(event["valid_from_state_version"])
    return {
        "schema_version": "full-state-v2",
        "state_version": version,
        "current_goal": {
            "all": [
                {"predicate": "in", "arguments": [done, "basket_1_contain_region"]},
                {"predicate": "in", "arguments": [pending, "basket_1_contain_region"]},
            ]
        },
        "entities": entities,
        "commitments": [commitment(done, "satisfied"), commitment(pending, "active")],
        "progress_ledger": [
            {
                "milestone_id": goal_commitment_id(done),
                "achieved": True,
                "physically_valid": True,
                "still_goal_relevant": True,
            }
        ],
        "plan": [
            {
                "step_id": "place-pending",
                "skill": "place_in",
                "arguments": [pending, "basket_1_contain_region"],
                "status": "pending",
                "preconditions": [],
                "effects": [
                    {"predicate": "in", "arguments": [pending, "basket_1_contain_region"]}
                ],
                "dependencies": [goal_commitment_id(done)],
            }
        ],
        "pending_restorations": [],
        "evidence_versions": {
            "event_id": genesis,
            "world_version": int(event["world_version"]),
            "input_state_version": version,
        },
    }


def commit_live_shared_envelope(
    event: Mapping[str, Any], cope_arm: Mapping[str, Any]
) -> dict[str, Any]:
    """Bind a provider-selected live semantic patch to trusted transaction metadata."""
    if cope_arm.get("arm") != "cope" or cope_arm.get("semantic_correct") is not True:
        return {"pass": False, "error": "CoPE semantic arm did not pass"}
    receipt = cope_arm.get("trusted_receipt")
    patch = receipt.get("patch") if isinstance(receipt, Mapping) else None
    if not isinstance(patch, Mapping):
        return {"pass": False, "error": "trusted CoPE receipt lacks the provider patch"}
    banned = {"state_version", "evidence_version", "processed_events", "payload_sha256", "receipt"}
    if set(patch) & banned:
        return {"pass": False, "error": "provider patch generated transaction metadata"}
    pre_state = build_live_pre_state(event)
    transaction_meta = {
        "schema_version": "transaction-meta-v1",
        "state_version": int(pre_state["state_version"]),
        "evidence_version": int(pre_state["evidence_versions"]["world_version"]),
        "processed_events": [],
    }
    envelope_event = copy.deepcopy(dict(event))
    envelope_event["base_version"] = int(event["valid_from_state_version"])
    try:
        committed = commit_envelope(transaction_meta, envelope_event)
    except (KeyError, TypeError, ValueError, SharedEnvelopeError) as exc:
        return {"pass": False, "error": f"{type(exc).__name__}:{exc}"}
    if (
        committed["state_version"] != transaction_meta["state_version"] + 1
        or committed["evidence_version"] != int(event["world_version"])
        or [row["event_id"] for row in committed["processed_events"]] != [event["event_id"]]
    ):
        return {"pass": False, "error": "trusted envelope postcondition mismatch"}
    return {
        "pass": True,
        "error": "",
        "transaction_metadata_model_generated": False,
        "semantic_state_sha256": str(cope_arm.get("after_state_sha256", "")),
        "transaction_meta_sha256": stable_hash(committed),
        "event_sha256": stable_hash(envelope_event),
        "transaction_base_version": int(envelope_event["base_version"]),
        "transaction_pre_state_version": int(transaction_meta["state_version"]),
        "transaction_post_state_version": int(committed["state_version"]),
        "transaction_evidence_version": int(committed["evidence_version"]),
        "transaction_processed_event_id": str(
            committed["processed_events"][0]["event_id"]
        ),
        "transaction_processed_payload_sha256": str(
            committed["processed_events"][0]["payload_sha256"]
        ),
        "transaction_meta": committed,
    }


def select_validated_cope_execution(
    cope_arm: Mapping[str, Any], event_type: str
) -> dict[str, Any]:
    """Derive the high-level executor command only from an accepted CoPE state."""

    if cope_arm.get("arm") != "cope" or cope_arm.get("semantic_correct") is not True:
        raise LearnedSemanticError("embodied execution requires an accepted CoPE arm")
    state = cope_arm.get("trusted_after_state")
    if not isinstance(state, Mapping):
        raise LearnedSemanticError("accepted CoPE arm has no trusted post-state")
    directive = cope_arm.get("compiled_directive")
    plan = state.get("plan")
    if not isinstance(plan, list):
        raise LearnedSemanticError("accepted CoPE state has no canonical plan")
    if event_type == "cancel_pending_goal":
        if directive != "HALT" or plan:
            raise LearnedSemanticError("cancellation must compile to an empty HALT plan")
        return {
            "execution_kind": "halt",
            "selected_object": "",
            "compiled_directive": "HALT",
            "selection_source": "validated_provider_post_state",
        }
    if event_type == "replace_pending_goal":
        pending = [row for row in plan if isinstance(row, Mapping) and row.get("status") == "pending"]
        if len(pending) != 1:
            raise LearnedSemanticError("replacement must compile to one pending action")
        arguments = pending[0].get("arguments")
        if not isinstance(arguments, list) or len(arguments) != 2:
            raise LearnedSemanticError("replacement action arguments are noncanonical")
        selected_object = str(arguments[0])
        if not selected_object or not isinstance(directive, str) or not directive:
            raise LearnedSemanticError("replacement has no executable directive")
        return {
            "execution_kind": "pick_and_place",
            "selected_object": selected_object,
            "compiled_directive": directive,
            "selection_source": "validated_provider_post_state",
        }
    raise LearnedSemanticError(f"unsupported embodied event family {event_type!r}")


def build_expected_live_post_state(event: Mapping[str, Any]) -> dict[str, Any]:
    """Trusted event-bound validation target, never a provider substitute."""

    if event["event_type"] == "replace_pending_goal":
        return _persistent_projection(build_canonical_replacement_state(event))
    if event["event_type"] == "cancel_pending_goal":
        return _persistent_projection(build_canonical_cancellation_state(event))
    raise LearnedSemanticError("unsupported live event family")


def live_transition_rules() -> dict[str, Any]:
    return {
        "authorization": "Only task_owner authority 100 may edit the named target.",
        "version": "The event valid_from_state_version must equal pre_state.state_version.",
        "progress": "Preserve the physically witnessed completed sibling.",
        "replacement": "Override only target_commitment_id with goal:<replacement_object>.",
        "cancellation": "Expire only target_commitment_id and compile to HALT.",
        "idempotence": "A processed event_id must be rejected; never apply it twice.",
    }


def make_live_recovery_input(
    *,
    pair_key: str,
    original_task: str,
    observation: Mapping[str, Any],
    event: Mapping[str, Any],
    public_action_history: Sequence[Mapping[str, Any]],
    physically_true_objects: Sequence[str],
    observation_fields: Sequence[str],
) -> RecoveryInput:
    return RecoveryInput(
        schema_version="recovery-input-v1",
        pair_key=pair_key,
        original_task=original_task,
        observation=dict(observation),
        event=dict(event),
        public_action_history=tuple(dict(item) for item in public_action_history),
        task_progress={
            "pre_state": build_live_pre_state(event),
            "transition_rules": live_transition_rules(),
            "physically_true_objects": list(physically_true_objects),
            "trusted_processed_event_ids": [],
        },
        information_budget=InformationBudget(
            event_fields=tuple(sorted(event)),
            history_fields=("policy_step", "environment_action"),
            observation_fields=tuple(observation_fields),
            max_high_level_calls=1,
            max_prompt_tokens=X15_PROMPT_BUDGET,
            max_completion_tokens=X15_COMPLETION_BUDGET,
        ),
    )


def parse_live_cope_patch(
    value: Any,
    event: Mapping[str, Any],
    *,
    processed_event_ids: Sequence[str] = (),
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise LearnedSemanticError("CoPE proposal must be one JSON object")
    replacement = event["event_type"] == "replace_pending_goal"
    required = {"event_id", "operation", "patch_id", "target_id"}
    if replacement:
        required.add("replacement_id")
    if set(value) != required:
        raise LearnedSemanticError("CoPE proposal contains missing or unauthorized extra fields")
    if value.get("event_id") != event.get("event_id"):
        raise LearnedSemanticError("CoPE proposal event is stale or mismatched")
    if value["event_id"] in set(processed_event_ids):
        raise LearnedSemanticError("idempotence violation: event was already processed")
    patch_id = value.get("patch_id")
    if not isinstance(patch_id, str) or not patch_id.strip():
        raise LearnedSemanticError("patch_id must be nonempty")
    if "oracle" in patch_id.lower():
        raise LearnedSemanticError("oracle substitution marker is forbidden")
    expected_operation = "Override" if replacement else "Expire"
    if value.get("operation") != expected_operation:
        raise LearnedSemanticError("invalid CoPE operation for live event")
    if value.get("target_id") != event.get("target_commitment_id"):
        raise LearnedSemanticError("unknown or unauthorized target")
    if replacement:
        expected_replacement = goal_commitment_id(str(event["replacement_object"]))
        if value.get("replacement_id") != expected_replacement:
            raise LearnedSemanticError("unknown or unauthorized replacement")
    return dict(value)


def _initialize_constraint_state(event: Mapping[str, Any]) -> ConstraintState:
    done = str(event["done_object"])
    pending = str(event["pending_object"])
    genesis_event = f"{event['event_id']}:genesis"
    state = ConstraintState.empty(f"x15:{event['event_id']}")

    def slot(object_name: str) -> ConstraintSlot:
        identifier = goal_commitment_id(object_name)
        return ConstraintSlot(
            slot_id=identifier,
            constraint_type="task_goal",
            content={
                "predicate": "in",
                "arguments": [object_name, "basket_1_contain_region"],
            },
            source="task",
            mode="active",
            priority=100,
            created_event_id=genesis_event,
            last_updated_event_id=genesis_event,
            lineage=(identifier,),
            metadata={"semantic_role": "live_task_goal_commitment"},
        )

    genesis = Patch(
        patch_id=f"{genesis_event}:trusted-loader",
        event_id=genesis_event,
        reason="load trusted witnessed persistent commitments",
        operations=(Insert("load-done", slot(done)), Insert("load-pending", slot(pending))),
        generator="trusted-live-state-loader",
        input_state_hash=state.state_hash,
        created_at=0,
    )
    loaded = apply_patch(state, genesis, PatchContext.trusted("trusted-live-state-loader"))
    if not loaded.accepted:
        raise RuntimeError("trusted live state loader failed")
    return loaded.state


def execute_live_cope_patch(
    proposal: Any,
    event: Mapping[str, Any],
    *,
    physically_true_objects: Sequence[str],
    processed_event_ids: Sequence[str] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    patch_fields = parse_live_cope_patch(
        proposal, event, processed_event_ids=processed_event_ids
    )
    state = _initialize_constraint_state(event)
    before = serialize_state(state)
    if patch_fields["operation"] == "Override":
        object_name = str(event["replacement_object"])
        replacement_id = str(patch_fields["replacement_id"])
        replacement = ConstraintSlot(
            slot_id=replacement_id,
            constraint_type="task_goal",
            content={
                "predicate": "in",
                "arguments": [object_name, "basket_1_contain_region"],
            },
            source="task",
            mode="active",
            priority=100,
            created_event_id=str(patch_fields["event_id"]),
            last_updated_event_id=str(patch_fields["event_id"]),
            parent_slot_id=str(patch_fields["target_id"]),
            overrides_slot_ids=(str(patch_fields["target_id"]),),
            lineage=(str(patch_fields["target_id"]), replacement_id),
            metadata={"semantic_role": "live_task_goal_commitment"},
        )
        operation = Override(
            f"{patch_fields['patch_id']}:operation",
            str(patch_fields["target_id"]),
            replacement,
            "provider-selected authorized live replacement",
        )
    else:
        operation = Expire(
            f"{patch_fields['patch_id']}:operation",
            str(patch_fields["target_id"]),
            "provider-selected authorized live cancellation",
        )
    patch = Patch(
        patch_id=str(patch_fields["patch_id"]),
        event_id=str(patch_fields["event_id"]),
        reason="X15 provider-selected semantic transition",
        operations=(operation,),
        generator="learned-live-provider",
        input_state_hash=state.state_hash,
        created_at=1,
        metadata={
            "provider_called": True,
            "oracle_substitution": False,
            "fallback_used": False,
        },
    )
    context = PatchContext(
        actor="task_owner",
        authority_priority=100,
        authorized_sources=("task",),
        event_source="detected",
        information_budget=X15_COMPLETION_BUDGET,
        policy_step_budget=0,
        high_level_call_count=1,
        pair_key={"event_id": str(event["event_id"])},
        task_progress={"physically_true_objects": list(physically_true_objects)},
        metadata={"learned_live_bridge": True},
    )
    transitioned = apply_patch(state, patch, context)
    if not transitioned.accepted:
        raise LearnedSemanticError(
            f"typed patch rejected: {transitioned.rejection_code}:{transitioned.rejection_reason}"
        )
    after = serialize_state(transitioned.state)
    receipt = {
        "schema_version": "x15-trusted-cope-receipt-v1",
        "method_label": "learned_cope_live_patch",
        "provider_called": True,
        "oracle_substitution": False,
        "fallback_used": False,
        "patch": patch_fields,
        "state_before": before,
        "state_after": after,
        "transition": {
            "accepted": True,
            "before_hash": transitioned.before_hash,
            "after_hash": transitioned.after_hash,
            "applied_operation_ids": list(transitioned.applied_operation_ids),
            "audit_record": thaw_json(transitioned.audit_record),
        },
    }
    # The projection is permitted only after the provider-selected engine
    # operation has changed exactly the authorized slots.
    typed_after = deserialize_state(after)
    target = typed_after.get_slot(str(event["target_commitment_id"]))
    if event["event_type"] == "replace_pending_goal":
        replacement = typed_after.get_slot(
            goal_commitment_id(str(event["replacement_object"]))
        )
        if target.mode.value != "overridden" or replacement.mode.value != "active":
            raise LearnedSemanticError("typed replacement did not materialize authorized modes")
    elif target.mode.value != "expired":
        raise LearnedSemanticError("typed cancellation did not materialize authorized mode")
    persistent = build_expected_live_post_state(event)
    validate_live_persistent_state(persistent, event, physically_true_objects)
    return persistent, receipt


def validate_live_persistent_state(
    candidate: Mapping[str, Any],
    event: Mapping[str, Any],
    physically_true_objects: Sequence[str],
) -> str:
    if not isinstance(candidate, Mapping) or set(candidate) != PERSISTENT_STATE_FIELDS:
        raise LearnedSemanticError("complete persistent state fields are noncanonical")
    enriched = copy.deepcopy(dict(candidate))
    previous = int(event["valid_from_state_version"])
    if event["event_type"] == "replace_pending_goal":
        enriched["controller_prompt"] = "diagnostic-only; execution must use the shared compiler"
        validate_canonical_replacement_state(
            enriched,
            event,
            previous_state_version=previous,
            physically_true_objects=physically_true_objects,
        )
        return compile_controller_prompt(enriched)
    enriched["execution_directive"] = "HALT"
    enriched["controller_prompt"] = "diagnostic-only; no controller call is permitted"
    validate_canonical_cancellation_state(
        enriched,
        event,
        previous_state_version=previous,
        physically_true_objects=physically_true_objects,
    )
    return compile_execution_directive(enriched)


def translate_live_neutral_patch(
    value: Any, event: Mapping[str, Any]
) -> dict[str, Any]:
    expected = (
        {"event_id", "operation", "patch_id", "target_id", "replacement_id"}
        if event["event_type"] == "replace_pending_goal"
        else {"event_id", "operation", "patch_id", "target_id"}
    )
    if not isinstance(value, Mapping) or set(value) != expected:
        raise LearnedSemanticError("neutral sparse patch fields are noncanonical")
    expected_label = (
        "N01" if event["event_type"] == "replace_pending_goal" else "N02"
    )
    if value.get("operation") != expected_label:
        raise LearnedSemanticError("neutral sparse patch uses the wrong operation label")
    translated = copy.deepcopy(dict(value))
    translated["operation"] = (
        "Override" if expected_label == "N01" else "Expire"
    )
    parse_live_cope_patch(translated, event)
    return translated


def trusted_live_transaction_finalize(
    state: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Any]:
    """Attach transaction-owned state/evidence fields after semantic generation."""

    out = copy.deepcopy(dict(state))
    expected = build_expected_live_post_state(event)
    out["schema_version"] = expected["schema_version"]
    out["state_version"] = expected["state_version"]
    out["evidence_versions"] = copy.deepcopy(expected["evidence_versions"])
    return out


def parse_live_fsr_semantic_state(
    value: Any, event: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != SEMANTIC_STATE_FIELDS:
        raise LearnedSemanticError(
            "FSR-PC output is not one complete metadata-free semantic state"
        )
    return trusted_live_transaction_finalize(value, event)


def _provider_status(invocation: ProviderInvocation) -> tuple[str, str]:
    if invocation.timeout:
        return "timeout", "provider_timeout"
    if invocation.validation_failure:
        return "outage", str(invocation.validation_failure)
    if invocation.parse_failure:
        return "response_parse_failure", str(invocation.parse_failure)
    return "ok", ""


def evaluate_live_arm(
    *,
    arm: str,
    invocation: ProviderInvocation,
    pre_state: Mapping[str, Any],
    event: Mapping[str, Any],
    physically_true_objects: Sequence[str],
) -> dict[str, Any]:
    status, provider_error = _provider_status(invocation)
    candidate: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None
    directive = ""
    error_message = ""
    parser_valid = False
    semantic_valid = False
    if status == "ok":
        try:
            if arm == "cope":
                candidate, receipt = execute_live_cope_patch(
                    invocation.parsed_output,
                    event,
                    physically_true_objects=physically_true_objects,
                )
                parser_valid = True
                directive = validate_live_persistent_state(
                    candidate, event, physically_true_objects
                )
            elif arm == "neutral_patch":
                translated = translate_live_neutral_patch(
                    invocation.parsed_output, event
                )
                parser_valid = True
                candidate, receipt = execute_live_cope_patch(
                    translated,
                    event,
                    physically_true_objects=physically_true_objects,
                )
                receipt = {
                    **receipt,
                    "method_label": "learned_neutral_sparse_live_patch",
                    "neutral_model_proposal_sha256": stable_hash(
                        invocation.parsed_output
                    ),
                }
                directive = validate_live_persistent_state(
                    candidate, event, physically_true_objects
                )
            elif arm == "compact_tx":
                raw_writes = (
                    invocation.parsed_output.get("writes")
                    if isinstance(invocation.parsed_output, Mapping)
                    else None
                )
                if isinstance(raw_writes, list) and any(
                    isinstance(write, Mapping)
                    and str(write.get("path", "")).removeprefix("/").split("/")[0]
                    in {"schema_version", "state_version", "evidence_versions", "processed_events"}
                    for write in raw_writes
                ):
                    raise LearnedSemanticError(
                        "compact output generated transaction metadata"
                    )
                proposal = parse_proposal(invocation.parsed_output, pre_state, event)
                parser_valid = True
                result = execute_compact_transaction(
                    proposal,
                    pre_state,
                    event,
                    lambda staged, _state, _event: validate_live_persistent_state(
                        staged, _event, physically_true_objects
                    ),
                    trusted_finalize=trusted_live_transaction_finalize,
                )
                candidate = result.post_state
                receipt = result.receipt
                directive = result.directive
            elif arm == "fsr_pc":
                candidate = parse_live_fsr_semantic_state(
                    invocation.parsed_output, event
                )
                parser_valid = True
                directive = validate_live_persistent_state(
                    candidate, event, physically_true_objects
                )
                receipt = {
                    "schema_version": "x15-trusted-fsr-receipt-v1",
                    "event_id": event["event_id"],
                    "provider_called": True,
                    "oracle_substitution": False,
                    "fallback_used": False,
                    "before_sha256": stable_hash(pre_state),
                    "after_sha256": stable_hash(candidate),
                    "accepted": True,
                }
            else:
                raise LearnedSemanticError(f"unknown X15 arm {arm!r}")
            semantic_valid = True
        except Exception as exc:
            error_message = f"{type(exc).__name__}:{exc}"
    return {
        "arm": arm,
        "provider_called": True,
        "provider_status": status,
        "provider_error": provider_error,
        "parser_valid": parser_valid,
        "semantic_valid": semantic_valid,
        "semantic_correct": semantic_valid,
        "parse_or_validation_error": error_message,
        "oracle_substitution": False,
        "fallback_used": False,
        "input_hash": invocation.raw_request.get("recovery_input", {}).get("input_hash", ""),
        "common_input_bytes_sha256": invocation.raw_request.get(
            "common_input_message_sha256", ""
        ),
        "normalized_request_sha256": normalized_raw_request_hash(invocation.raw_request),
        "response_sha256": (
            invocation.raw_response.get("response_sha256", "")
            if isinstance(invocation.raw_response, Mapping)
            else ""
        ),
        "prompt_tokens": invocation.usage.prompt_tokens,
        "completion_tokens": invocation.usage.completion_tokens,
        "latency_seconds": invocation.latency_seconds,
        "retry_count": invocation.retry_count,
        "proposal_bytes": (
            len(canonical_json(invocation.parsed_output).encode("utf-8"))
            if isinstance(invocation.parsed_output, Mapping)
            else 0
        ),
        "compiled_directive": directive,
        "before_state_sha256": stable_hash(pre_state),
        "after_state_sha256": stable_hash(candidate) if candidate is not None else "",
        "receipt_sha256": stable_hash(receipt) if receipt is not None else "",
        "trusted_receipt": receipt,
        "trusted_before_state": copy.deepcopy(dict(pre_state)),
        "trusted_after_state": candidate,
        "predicate_outcome": {
            "done": str(event["done_object"]) in set(physically_true_objects),
            "pending": str(event["pending_object"]) in set(physically_true_objects),
        },
    }


def _validate_x15_provider(provider: Any) -> None:
    metadata = provider.metadata
    if metadata.is_fake:
        raise LearnedSemanticError("oracle substitution or fake provider is forbidden")
    expected = {
        "model": X15_MODEL,
        "temperature": X15_TEMPERATURE,
        "max_prompt_tokens": X15_PROMPT_BUDGET,
        "max_completion_tokens": X15_COMPLETION_BUDGET,
        "max_retries": 0,
        "timeout_seconds": X15_TIMEOUT_SECONDS,
    }
    actual = {key: getattr(metadata, key) for key in expected}
    if actual != expected:
        raise LearnedSemanticError("provider settings differ from frozen X14/X15 settings")
    if provider.reasoning_effort != X15_REASONING_EFFORT or provider.seed != X15_SEED:
        raise LearnedSemanticError("reasoning or seed differs from frozen X14/X15 settings")
    if not callable(getattr(provider, "call_contract", None)):
        raise LearnedSemanticError("provider lacks the audited single-draw contract interface")


def run_learned_semantic_triplet(
    *,
    row: Mapping[str, str],
    config: LoadedSemanticConfig,
    original_task: str,
    observation: Mapping[str, Any],
    public_action_history: Sequence[Mapping[str, Any]],
    independently_logged_predicates: Mapping[str, bool],
    simulator_state_probe: Callable[[], str],
    action_counter: Callable[[], int],
    provider: Any,
) -> dict[str, Any]:
    """Run X15 Phase A: three provider calls and trusted semantics, zero actions."""

    _validate_x15_provider(provider)
    state_id = int(row["state_id"])
    if state_id not in DEVELOPMENT_STATE_IDS:
        raise LearnedSemanticError("X15 permits only development states 0--4")
    milestone = MilestoneEvent(
        policy_step=int(observation["predicate_snapshot"]["policy_step"]),
        done_object=row["done_object"],
        pending_object=row["pending_object"],
        stable_steps=int(row["stable_steps"]),
    )
    event = (
        build_replacement_event(
            milestone,
            pair_key=row["case_id"],
            replacement_object=row["replacement_object"],
        )
        if row["event_type"] == "replace_pending_goal"
        else build_cancellation_event(milestone, pair_key=row["case_id"])
    )
    packet = observation.get("predicate_snapshot")
    simulator_before = simulator_state_probe()
    actions_before = action_counter()
    if not isinstance(packet, Mapping) or packet.get("event_id") != event["event_id"]:
        raise LearnedSemanticError("live packet is not event-bound")
    if packet.get("test_only") is not False or packet.get("source_kind") != "live_libero_eval_predicate":
        raise LearnedSemanticError("production learned path rejects fake predicate packets")
    if packet.get("policy_step") != event.get("world_version"):
        raise LearnedSemanticError("live packet policy step is not event-bound")
    if packet.get("observation_sha256") != observation.get("sha256"):
        raise LearnedSemanticError("live packet is not RGB-observation-bound")
    if packet.get("simulator_state_sha256") != simulator_before:
        raise LearnedSemanticError("live packet is not simulator-state-bound")
    if packet.get("producer_commit") != config.row["predicate_producer_commit"]:
        raise LearnedSemanticError("live packet producer differs from frozen config")
    packet_predicates = {
        str(item["arguments"][0]): bool(item["value"])
        for item in packet["predicates"]
        if item.get("predicate") == "in" and len(item.get("arguments", ())) == 2
    }
    if packet_predicates != dict(independently_logged_predicates):
        raise LearnedSemanticError("trusted predicate log differs from live packet")
    physically_true = tuple(
        sorted(name for name, value in independently_logged_predicates.items() if value)
    )
    validator = create_libero_predicate_validator(config.predicate_engine_config)
    if validator.metadata.get("is_fake") is not False:
        raise LearnedSemanticError("production predicate validator advertises fake metadata")
    validation_state = _initialize_constraint_state(event)
    evidence = {"observation": observation, "event": event}
    done_value = validator(
        validation_state.get_slot(goal_commitment_id(str(event["done_object"]))),
        evidence,
    )
    pending_value = validator(
        validation_state.get_slot(goal_commitment_id(str(event["pending_object"]))),
        evidence,
    )
    if done_value is not True or pending_value is not False:
        raise LearnedSemanticError("trusted live predicate outcome is noncanonical")
    common = make_live_recovery_input(
        pair_key=row["case_id"],
        original_task=original_task,
        observation=observation,
        event=event,
        public_action_history=public_action_history,
        physically_true_objects=physically_true,
        observation_fields=config.observation_fields,
    )
    specs = (
        ("cope", "patch", LIVE_COPE_CONTRACT),
        ("neutral_patch", "patch", LIVE_NEUTRAL_CONTRACT),
        ("compact_tx", "compact", LIVE_COMPACT_CONTRACT),
        ("fsr_pc", "regenerate", LIVE_FSR_CONTRACT),
    )
    invocations = {
        arm: provider.call_contract(mode, common, contract)
        for arm, mode, contract in specs
    }
    pre_state = build_live_pre_state(event)
    arms = [
        evaluate_live_arm(
            arm=arm,
            invocation=invocations[arm],
            pre_state=pre_state,
            event=event,
            physically_true_objects=physically_true,
        )
        for arm, _mode, _contract in specs
    ]
    shared_envelope = commit_live_shared_envelope(
        event, next(item for item in arms if item["arm"] == "cope")
    )
    expected_payload = common.as_payload()
    fairness = bool(
        all(call.raw_request.get("recovery_input") == expected_payload for call in invocations.values())
        and len({row_["common_input_bytes_sha256"] for row_ in arms}) == 1
        and len({row_["normalized_request_sha256"] for row_ in arms}) == 1
        and all(row_["retry_count"] == 0 for row_ in arms)
    )
    settings_hash = stable_hash(
        {
            "model": provider.metadata.model,
            "reasoning_effort": provider.reasoning_effort,
            "temperature": provider.metadata.temperature,
            "seed": provider.seed,
            "max_prompt_tokens": provider.metadata.max_prompt_tokens,
            "max_completion_tokens": provider.metadata.max_completion_tokens,
            "timeout_seconds": provider.metadata.timeout_seconds,
            "max_retries": provider.metadata.max_retries,
        }
    )
    simulator_after = simulator_state_probe()
    actions_after = action_counter()
    action_delta = actions_after - actions_before
    if simulator_after != simulator_before or action_delta != 0:
        raise LearnedSemanticError("Phase A emitted an action or mutated simulator state")
    for arm_result in arms:
        arm_result["fairness_pass"] = fairness
        arm_result["settings_sha256"] = settings_hash
        arm_result["input_hash"] = common.input_hash
        arm_result["controller_action_count_before"] = actions_before
        arm_result["controller_action_count_after"] = actions_after
        arm_result["post_interruption_action_delta"] = action_delta
        arm_result["simulator_state_before"] = simulator_before
        arm_result["simulator_state_after"] = simulator_after
        arm_result["predicate_outcome"] = {
            "done": done_value,
            "pending": pending_value,
            "validator_is_fake": validator.metadata["is_fake"],
        }
    return {
        "case_id": row["case_id"],
        "state_id": state_id,
        "event_type": row["event_type"],
        "event_id": event["event_id"],
        "input_hash": common.input_hash,
        "settings_sha256": settings_hash,
        "fairness_pass": fairness,
        "provider_called": all(item["provider_called"] for item in arms),
        "oracle_substitution": any(item["oracle_substitution"] for item in arms),
        "fallback_used": any(item["fallback_used"] for item in arms),
        "controller_action_count_before": actions_before,
        "controller_action_count_after": actions_after,
        "post_interruption_action_delta": action_delta,
        "simulator_state_before": simulator_before,
        "simulator_state_after": simulator_after,
        "shared_envelope": shared_envelope,
        "arms": arms,
    }


def state0_expansion_allowed(triplets: Sequence[Mapping[str, Any]]) -> bool:
    if {item.get("event_type") for item in triplets} != EVENT_TYPES:
        return False
    if any(int(item.get("state_id", -1)) != 0 for item in triplets):
        return False
    for triplet in triplets:
        if triplet.get("shared_envelope", {}).get("pass") is not True:
            return False
        arms = triplet.get("arms")
        if not isinstance(arms, list) or {
            item.get("arm") for item in arms
        } != set(LIVE_ARMS):
            return False
        if not triplet.get("fairness_pass"):
            return False
        if any(item.get("provider_status") != "ok" for item in arms):
            return False
        if any(
            item.get("provider_called") is not True
            or item.get("oracle_substitution") is not False
            or item.get("fallback_used") is not False
            or item.get("post_interruption_action_delta") != 0
            for item in arms
        ):
            return False
        if len({item.get("input_hash") for item in arms}) != 1:
            return False
        if len({item.get("settings_sha256") for item in arms}) != 1:
            return False
    return True


def recorded_state0_expansion_allowed(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Validate a retained state-0 CSV without issuing any provider call again."""

    def truth(value: Any) -> bool:
        return value is True or str(value).lower() == "true"

    if len(rows) != 2 * len(LIVE_ARMS):
        return False
    if {str(row.get("event_type")) for row in rows} != EVENT_TYPES:
        return False
    if any(int(row.get("state_id", -1)) != 0 for row in rows):
        return False
    by_case: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_case.setdefault(str(row.get("case_id")), []).append(row)
    if len(by_case) != 2:
        return False
    for group in by_case.values():
        if {row.get("arm") for row in group} != set(LIVE_ARMS):
            return False
        if any(
            row.get("provider_status") != "ok"
            or not truth(row.get("provider_called"))
            or not truth(row.get("fairness_pass"))
            or truth(row.get("oracle_substitution"))
            or truth(row.get("fallback_used"))
            or int(row.get("post_interruption_action_delta", -1)) != 0
            for row in group
        ):
            return False
        if len({row.get("input_hash") for row in group}) != 1:
            return False
        if len({row.get("settings_sha256") for row in group}) != 1:
            return False
    return True
