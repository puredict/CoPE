from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Protocol, runtime_checkable

from cope.providers.base import load_object
from cope.types import PatchOutput, RecoveryInput, stable_hash


class CoPEEngineProtocolError(RuntimeError):
    pass


@runtime_checkable
class ConstraintStateEngine(Protocol):
    """Adapter contract for the engine delivered by method/cope-state-semantics.

    This branch intentionally contains no production state semantics.
    """

    @property
    def metadata(self) -> dict[str, Any]: ...

    def initialize(self, original_task: str, context: dict[str, Any]) -> None: ...

    def snapshot(self) -> dict[str, Any]: ...

    def apply_operation(self, operation: dict[str, Any]) -> None: ...

    def revalidate(self, target_id: str, context: dict[str, Any]) -> dict[str, Any]: ...

    def compile_controller_prompt(self) -> str: ...


EngineFactory = Callable[[dict[str, Any]], ConstraintStateEngine]


def load_engine_factory(spec: str) -> EngineFactory:
    factory = load_object(spec)
    if not callable(factory):
        raise TypeError(f"engine factory {spec!r} is not callable")
    return factory


def validate_engine(engine: ConstraintStateEngine, *, formal: bool) -> None:
    missing = [
        name
        for name in (
            "metadata",
            "initialize",
            "snapshot",
            "apply_operation",
            "revalidate",
            "compile_controller_prompt",
        )
        if not hasattr(engine, name)
    ]
    if missing:
        raise CoPEEngineProtocolError(f"CoPE engine adapter is missing {missing}")
    metadata = engine.metadata
    if not isinstance(metadata, dict):
        raise CoPEEngineProtocolError("engine metadata must be a dictionary")
    if formal:
        if metadata.get("is_fake") is not False:
            raise CoPEEngineProtocolError("formal run requires metadata.is_fake=false")
        if not metadata.get("engine_commit"):
            raise CoPEEngineProtocolError("formal run requires engine_commit")
        if not metadata.get("schema_version"):
            raise CoPEEngineProtocolError("formal run requires engine schema_version")
        if metadata.get("revalidation_validator_configured") is not True:
            raise CoPEEngineProtocolError("formal run requires a real revalidation validator adapter")
        validator_metadata = metadata.get("revalidation_validator_metadata")
        if not isinstance(validator_metadata, dict):
            raise CoPEEngineProtocolError("formal run requires revalidation validator metadata")
        if validator_metadata.get("is_fake") is not False:
            raise CoPEEngineProtocolError("formal run forbids a fake revalidation validator")
        if not validator_metadata.get("validator_commit"):
            raise CoPEEngineProtocolError("formal run requires revalidation validator_commit")
        if not metadata.get("controller_compiler_version"):
            raise CoPEEngineProtocolError("formal run requires a versioned controller compiler")


def _constraint_map(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    constraints = state.get("constraints", [])
    if not isinstance(constraints, list):
        raise CoPEEngineProtocolError("engine snapshot constraints must be a list")
    result: dict[str, dict[str, Any]] = {}
    for index, constraint in enumerate(constraints):
        if not isinstance(constraint, dict):
            raise CoPEEngineProtocolError(f"constraint {index} must be an object")
        constraint_id = constraint.get("id")
        if not isinstance(constraint_id, str) or not constraint_id:
            raise CoPEEngineProtocolError(f"constraint {index} has no stable id")
        if constraint_id in result:
            raise CoPEEngineProtocolError(f"duplicate constraint id {constraint_id!r}")
        for field in ("source", "priority", "lineage"):
            if field not in constraint:
                raise CoPEEngineProtocolError(f"constraint {constraint_id!r} is missing {field}")
        result[constraint_id] = constraint
    return result


def unaffected_slot_preservation(
    before: dict[str, Any],
    after: dict[str, Any],
    affected_ids: set[str],
) -> dict[str, Any]:
    before_map = _constraint_map(before)
    after_map = _constraint_map(after)
    unaffected = sorted(set(before_map) - affected_ids)
    missing = [constraint_id for constraint_id in unaffected if constraint_id not in after_map]
    changed: list[str] = []
    for constraint_id in unaffected:
        if constraint_id in after_map and stable_hash(before_map[constraint_id]) != stable_hash(after_map[constraint_id]):
            changed.append(constraint_id)
    return {
        "unaffected_ids": unaffected,
        "preserved_count": len(unaffected) - len(missing) - len(changed),
        "missing_ids": missing,
        "changed_ids": changed,
        "passed": not missing and not changed,
    }


@dataclass(frozen=True)
class GuardedPatchResult:
    state_before: dict[str, Any]
    state_after: dict[str, Any]
    operations: tuple[dict[str, Any], ...]
    revalidations: tuple[dict[str, Any], ...]
    controller_prompt: str
    preservation: dict[str, Any]


def apply_guarded_patch(
    engine: ConstraintStateEngine,
    patch: PatchOutput,
    recovery_input: RecoveryInput,
) -> GuardedPatchResult:
    """Apply typed operations while enforcing the Revalidate-before-Restore gate."""

    validate_engine(engine, formal=False)
    before = engine.snapshot()
    _constraint_map(before)
    atomic_apply = getattr(engine, "apply_typed_patch", None)
    if callable(atomic_apply):
        raw_operations = [asdict(operation) for operation in patch.operations]
        atomic = atomic_apply(raw_operations, recovery_input.as_payload())
        if not isinstance(atomic, dict):
            raise CoPEEngineProtocolError("atomic engine adapter must return an object")
        state_before = atomic.get("state_before")
        state_after = atomic.get("state_after")
        operations = atomic.get("operations")
        revalidations = atomic.get("revalidations")
        prompt = atomic.get("controller_prompt")
        if state_before != before:
            raise CoPEEngineProtocolError("atomic engine state_before does not match pre-call snapshot")
        if not isinstance(state_after, dict):
            raise CoPEEngineProtocolError("atomic engine state_after must be an object")
        if not isinstance(operations, list) or not isinstance(revalidations, list):
            raise CoPEEngineProtocolError("atomic engine operations/revalidations must be lists")
        if [operation.get("op") for operation in operations] != [
            operation.op for operation in patch.operations
        ]:
            raise CoPEEngineProtocolError("atomic engine changed typed operation order or type")
        successful: set[str] = set()
        for operation in operations:
            target_id = operation.get("target_id")
            if operation.get("op") == "Revalidate":
                result = (operation.get("payload") or {}).get("result") or {}
                if result.get("success") is True and target_id:
                    successful.add(str(target_id))
            elif operation.get("op") == "Restore" and target_id not in successful:
                raise CoPEEngineProtocolError(
                    f"blind restore rejected for {target_id!r}: no successful prior Revalidate"
                )
        _constraint_map(state_after)
        if not isinstance(prompt, str) or not prompt.strip():
            raise CoPEEngineProtocolError("atomic engine controller prompt must be non-empty")
        affected_ids = {
            str(operation.target_id)
            for operation in patch.operations
            if operation.target_id is not None
        }
        preservation = unaffected_slot_preservation(state_before, state_after, affected_ids)
        if not preservation["passed"]:
            raise CoPEEngineProtocolError(
                "engine changed unaffected slots: "
                f"missing={preservation['missing_ids']} changed={preservation['changed_ids']}"
            )
        return GuardedPatchResult(
            state_before=state_before,
            state_after=state_after,
            operations=tuple(operations),
            revalidations=tuple(revalidations),
            controller_prompt=prompt,
            preservation=preservation,
        )

    successful_revalidations: set[str] = set()
    revalidations: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    affected_ids: set[str] = set()

    for operation in patch.operations:
        operation_payload = asdict(operation)
        target_id = operation.target_id
        if target_id:
            affected_ids.add(target_id)

        if operation.op == "Revalidate":
            assert target_id is not None
            result = engine.revalidate(target_id, recovery_input.as_payload())
            if not isinstance(result, dict) or not isinstance(result.get("success"), bool):
                raise CoPEEngineProtocolError("revalidate must return an object containing boolean success")
            record = {"target_id": target_id, **result}
            revalidations.append(record)
            if result["success"]:
                successful_revalidations.add(target_id)
            operation_payload["payload"] = {**operation_payload["payload"], "result": result}
            engine.apply_operation(operation_payload)
        elif operation.op == "Restore":
            assert target_id is not None
            if target_id not in successful_revalidations:
                raise CoPEEngineProtocolError(
                    f"blind restore rejected for {target_id!r}: no successful prior Revalidate"
                )
            engine.apply_operation(operation_payload)
        else:
            engine.apply_operation(operation_payload)
        operations.append(operation_payload)

    after = engine.snapshot()
    _constraint_map(after)
    prompt = engine.compile_controller_prompt()
    if not isinstance(prompt, str) or not prompt.strip():
        raise CoPEEngineProtocolError("compiled controller prompt must be non-empty")
    preservation = unaffected_slot_preservation(before, after, affected_ids)
    if not preservation["passed"]:
        raise CoPEEngineProtocolError(
            "engine changed unaffected slots: "
            f"missing={preservation['missing_ids']} changed={preservation['changed_ids']}"
        )
    return GuardedPatchResult(
        state_before=before,
        state_after=after,
        operations=tuple(operations),
        revalidations=tuple(revalidations),
        controller_prompt=prompt,
        preservation=preservation,
    )
