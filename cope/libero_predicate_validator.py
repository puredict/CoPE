from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from cope.schema import ConstraintSlot
from cope.types import stable_hash
from cope_benchmark.task_progress import LiberoStateView, TASK_DEFINITIONS


PREDICATE_SNAPSHOT_SCHEMA = "cope-libero-predicate-snapshot-v1"
PREDICATE_VALIDATOR_VERSION = "cope-libero-predicate-validator-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class PredicateSnapshotError(ValueError):
    pass


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise PredicateSnapshotError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _commit(value: Any, label: str) -> str:
    if not isinstance(value, str) or _COMMIT_RE.fullmatch(value) is None:
        raise PredicateSnapshotError(f"{label} must be a full lowercase git commit")
    return value


def build_predicate_snapshot(
    *,
    task_suite: str,
    task_id: int,
    event_id: str,
    policy_step: int,
    observation_sha256: str,
    simulator_state_sha256: str,
    producer_commit: str,
    predicates: Sequence[tuple[str, Sequence[str], bool]],
    test_only: bool,
    source_kind: str,
) -> dict[str, Any]:
    _sha256(observation_sha256, "observation_sha256")
    _sha256(simulator_state_sha256, "simulator_state_sha256")
    _commit(producer_commit, "producer_commit")
    if not isinstance(event_id, str) or not event_id:
        raise PredicateSnapshotError("event_id must be nonempty")
    if not isinstance(source_kind, str) or not source_kind:
        raise PredicateSnapshotError("source_kind must be nonempty")
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for predicate, arguments, value in predicates:
        key = (str(predicate).lower(), tuple(str(item) for item in arguments))
        if not key[0] or not key[1] or key in seen:
            raise PredicateSnapshotError("predicate records must be unique and nonempty")
        if not isinstance(value, bool):
            raise PredicateSnapshotError("predicate value must be boolean")
        seen.add(key)
        records.append(
            {"predicate": key[0], "arguments": list(key[1]), "value": value}
        )
    if not records:
        raise PredicateSnapshotError("predicate snapshot cannot be empty")
    records.sort(key=lambda item: (item["predicate"], item["arguments"]))
    payload: dict[str, Any] = {
        "schema_version": PREDICATE_SNAPSHOT_SCHEMA,
        "task_suite": str(task_suite),
        "task_id": int(task_id),
        "event_id": event_id,
        "policy_step": int(policy_step),
        "observation_sha256": observation_sha256,
        "simulator_state_sha256": simulator_state_sha256,
        "producer_version": PREDICATE_VALIDATOR_VERSION,
        "producer_commit": producer_commit,
        "source_kind": source_kind,
        "test_only": bool(test_only),
        "predicates": records,
    }
    payload["snapshot_sha256"] = stable_hash(payload)
    return payload


def build_live_libero_predicate_snapshot(
    env: Any,
    *,
    task_suite: str,
    task_id: int,
    event_id: str,
    policy_step: int,
    observation_sha256: str,
    simulator_state_sha256: str,
    producer_commit: str,
    test_only: bool = False,
) -> dict[str, Any]:
    definition = TASK_DEFINITIONS.get((str(task_suite), int(task_id)))
    if definition is None:
        raise PredicateSnapshotError(
            f"no registered task progress definition for {(task_suite, task_id)!r}"
        )
    view = LiberoStateView(env)
    predicates: list[tuple[str, Sequence[str], bool]] = []
    for spec in definition.predicates:
        if not spec.commitment or spec.kind != "libero_predicate":
            continue
        predicate, *arguments = spec.arguments
        predicates.append(
            (
                str(predicate),
                tuple(str(item) for item in arguments),
                view.libero_predicate(str(predicate), arguments),
            )
        )
    return build_predicate_snapshot(
        task_suite=task_suite,
        task_id=task_id,
        event_id=event_id,
        policy_step=policy_step,
        observation_sha256=observation_sha256,
        simulator_state_sha256=simulator_state_sha256,
        producer_commit=producer_commit,
        predicates=predicates,
        test_only=test_only,
        source_kind="live_libero_eval_predicate",
    )


def attach_libero_predicate_snapshot(
    observation: Mapping[str, Any],
    env: Any,
    *,
    engine_config: Mapping[str, Any],
    observation_fields: Sequence[str],
    task_suite: str,
    task_id: int,
    event_id: str,
    policy_step: int,
    simulator_state_sha256: str,
) -> dict[str, Any]:
    result = dict(observation)
    config = engine_config.get("predicate_snapshot")
    if not isinstance(config, Mapping) or config.get("enabled") is not True:
        return result
    if "predicate_snapshot" not in set(observation_fields):
        raise PredicateSnapshotError(
            "enabled predicate snapshot exceeds the observation information budget"
        )
    result["predicate_snapshot"] = build_live_libero_predicate_snapshot(
        env,
        task_suite=task_suite,
        task_id=task_id,
        event_id=event_id,
        policy_step=policy_step,
        observation_sha256=_sha256(result.get("sha256"), "observation.sha256"),
        simulator_state_sha256=simulator_state_sha256,
        producer_commit=_commit(config.get("producer_commit"), "producer_commit"),
        test_only=bool(config.get("test_only", False)),
    )
    return result


class LiberoPredicateRevalidationValidator:
    validator_id = PREDICATE_VALIDATOR_VERSION

    def __init__(self, config: Mapping[str, Any]) -> None:
        raw = config.get("predicate_snapshot")
        if not isinstance(raw, Mapping):
            raw = config
        self.allow_test_packets = bool(raw.get("allow_test_packets", False))
        self.task_suite = str(raw.get("task_suite", "libero_10"))
        self.task_id = int(raw.get("task_id", 1))
        self.producer_commit = _commit(raw.get("producer_commit"), "producer_commit")
        self.metadata = {
            "is_fake": self.allow_test_packets,
            "validator_commit": self.producer_commit,
            "validator_version": PREDICATE_VALIDATOR_VERSION,
            "packet_schema": PREDICATE_SNAPSHOT_SCHEMA,
            "task_suite": self.task_suite,
            "task_id": self.task_id,
            "allows_test_packets": self.allow_test_packets,
        }

    def __call__(self, slot: ConstraintSlot, evidence: Mapping[str, Any]) -> bool:
        observation = evidence.get("observation")
        event = evidence.get("event")
        if not isinstance(observation, Mapping) or not isinstance(event, Mapping):
            raise PredicateSnapshotError("validator requires observation and event objects")
        packet = observation.get("predicate_snapshot")
        if not isinstance(packet, Mapping):
            raise PredicateSnapshotError("observation has no predicate_snapshot")
        expected_keys = {
            "schema_version",
            "task_suite",
            "task_id",
            "event_id",
            "policy_step",
            "observation_sha256",
            "simulator_state_sha256",
            "producer_version",
            "producer_commit",
            "source_kind",
            "test_only",
            "predicates",
            "snapshot_sha256",
        }
        if set(packet) != expected_keys:
            raise PredicateSnapshotError("predicate snapshot fields are non-canonical")
        unsigned = dict(packet)
        actual_hash = unsigned.pop("snapshot_sha256")
        if _sha256(actual_hash, "snapshot_sha256") != stable_hash(unsigned):
            raise PredicateSnapshotError("predicate snapshot hash mismatch")
        if packet.get("schema_version") != PREDICATE_SNAPSHOT_SCHEMA:
            raise PredicateSnapshotError("unsupported predicate snapshot schema")
        if packet.get("producer_version") != PREDICATE_VALIDATOR_VERSION:
            raise PredicateSnapshotError("unsupported predicate producer version")
        if packet.get("task_suite") != self.task_suite or int(packet.get("task_id", -1)) != self.task_id:
            raise PredicateSnapshotError("predicate snapshot task identity mismatch")
        if packet.get("event_id") != event.get("event_id"):
            raise PredicateSnapshotError("predicate snapshot event mismatch")
        if packet.get("producer_commit") != self.producer_commit:
            raise PredicateSnapshotError("predicate snapshot producer commit mismatch")
        if packet.get("test_only") is True and not self.allow_test_packets:
            raise PredicateSnapshotError("production validator rejects test-only packets")
        if not isinstance(packet.get("test_only"), bool):
            raise PredicateSnapshotError("test_only must be boolean")
        _sha256(packet.get("simulator_state_sha256"), "simulator_state_sha256")
        observation_hash = _sha256(observation.get("sha256"), "observation.sha256")
        if _sha256(packet.get("observation_sha256"), "observation_sha256") != observation_hash:
            raise PredicateSnapshotError("predicate snapshot is not bound to the outer observation")

        if slot.constraint_type != "task_goal":
            raise PredicateSnapshotError("validator supports only atomic task_goal slots")
        content = slot.content
        if not isinstance(content, Mapping) or set(content) != {"predicate", "arguments"}:
            raise PredicateSnapshotError("task_goal slot is not an atomic predicate")
        predicate = str(content.get("predicate", "")).lower()
        arguments = content.get("arguments")
        if not isinstance(arguments, (tuple, list)) or not arguments:
            raise PredicateSnapshotError("task_goal arguments are missing")
        key = (predicate, tuple(str(item) for item in arguments))

        records = packet.get("predicates")
        if not isinstance(records, list) or not records:
            raise PredicateSnapshotError("predicate records are missing")
        matches: list[bool] = []
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for record in records:
            if not isinstance(record, Mapping) or set(record) != {"predicate", "arguments", "value"}:
                raise PredicateSnapshotError("predicate record is non-canonical")
            record_arguments = record.get("arguments")
            if not isinstance(record_arguments, list) or not record_arguments:
                raise PredicateSnapshotError("predicate record arguments are invalid")
            record_key = (
                str(record.get("predicate", "")).lower(),
                tuple(str(item) for item in record_arguments),
            )
            if record_key in seen:
                raise PredicateSnapshotError("duplicate predicate record")
            seen.add(record_key)
            if not isinstance(record.get("value"), bool):
                raise PredicateSnapshotError("predicate record value must be boolean")
            if record_key == key:
                matches.append(record["value"])
        if len(matches) != 1:
            raise PredicateSnapshotError("atomic task_goal has no unique snapshot predicate")
        return matches[0]


def create_libero_predicate_validator(
    config: dict[str, Any],
) -> LiberoPredicateRevalidationValidator:
    return LiberoPredicateRevalidationValidator(config)
