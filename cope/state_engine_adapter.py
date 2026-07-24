from __future__ import annotations

import json
from typing import Any, Mapping

from cope.providers.base import load_object
from cope.schema import (
    ConstraintSlot,
    ConstraintState,
    Demote,
    Expire,
    Insert,
    Override,
    Patch,
    PatchContext,
    Restore,
    Suspend,
)
from cope.operations import apply_patch
from cope.recovery import revalidate_slot
from cope.serialization import serialize_state, thaw_json
from cope.types import PATCH_OPERATION_TYPES, stable_hash


ENGINE_SOURCE_COMMIT = "fd0e2c501342ed7226360ae63c14615a1fc44c65"
ADAPTER_VERSION = "cope-main-engine-adapter-v1"
CONTROLLER_COMPILER_VERSION = "cope-controller-compiler-v1"


class CoPEStateEngineAdapter:
    """Thin experiment adapter over the committed persistent-state engine.

    State transition semantics stay in ``cope.operations.apply_patch``. This
    adapter only maps provider JSON into engine dataclasses and compiles the
    accepted state into the downstream controller prompt.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})
        self.state: ConstraintState | None = None
        self.original_task = ""
        self.prepare_context: dict[str, Any] = {}
        validator_spec = self.config.get("revalidation_validator_factory")
        self.validator = None
        self.validator_metadata: dict[str, Any] = {}
        if validator_spec:
            factory = load_object(str(validator_spec))
            if not callable(factory):
                raise TypeError("revalidation_validator_factory must resolve to a callable")
            self.validator = factory(self.config)
            metadata = getattr(self.validator, "metadata", {})
            self.validator_metadata = dict(metadata) if isinstance(metadata, Mapping) else {}

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "is_fake": False,
            "engine_commit": ENGINE_SOURCE_COMMIT,
            "schema_version": "1.0",
            "adapter_version": ADAPTER_VERSION,
            "controller_compiler_version": CONTROLLER_COMPILER_VERSION,
            "revalidation_validator_configured": self.validator is not None,
            "revalidation_validator_metadata": self.validator_metadata,
        }

    def initialize(self, original_task: str, context: dict[str, Any]) -> None:
        if self.state is not None:
            raise RuntimeError("constraint engine instance cannot be initialized twice")
        self.original_task = original_task
        self.prepare_context = dict(context)
        state_id = "cope-" + stable_hash(
            {
                "pair_key": context.get("pair_key"),
                "task": original_task,
                "schema": "1.0",
            }
        )[:24]
        state = ConstraintState.empty(state_id)
        goal = ConstraintSlot(
            slot_id="goal",
            constraint_type="task_goal",
            content={"instruction": original_task},
            source="task",
            mode="active",
            priority=int(self.config.get("initial_goal_priority", 100)),
            created_event_id="genesis-event",
            last_updated_event_id="genesis-event",
            lineage=("goal",),
            metadata={"adapter_version": ADAPTER_VERSION},
        )
        patch = Patch(
            patch_id="genesis-patch",
            event_id="genesis-event",
            reason="initialize original task constraint",
            operations=(Insert("genesis-insert-goal", goal),),
            generator=ADAPTER_VERSION,
            input_state_hash=state.state_hash,
            created_at=0,
        )
        result = apply_patch(state, patch, PatchContext.trusted("cope-main-genesis"))
        if not result.accepted:
            raise RuntimeError(
                f"engine genesis rejected: {result.rejection_code}: {result.rejection_reason}"
            )
        self.state = result.state

    def _require_state(self) -> ConstraintState:
        if self.state is None:
            raise RuntimeError("constraint engine has not been initialized")
        return self.state

    def snapshot(self) -> dict[str, Any]:
        state = self._require_state()
        serialized = serialize_state(state)
        constraints = [
            {
                "id": slot["slot_id"],
                "constraint_type": slot["constraint_type"],
                "content": slot["content"],
                "source": slot["source"],
                "mode": slot["mode"],
                "priority": slot["priority"],
                "created_event_id": slot["created_event_id"],
                "last_updated_event_id": slot["last_updated_event_id"],
                "parent_id": slot["parent_slot_id"],
                "overrides_ids": slot["overrides_slot_ids"],
                "lineage": slot["lineage"],
                "evidence_refs": slot["evidence_refs"],
                "metadata": slot["metadata"],
            }
            for slot in serialized["slots"]
        ]
        return {
            "schema_version": serialized["schema_version"],
            "state_id": serialized["state_id"],
            "revision": serialized["revision"],
            "state_hash": serialized["state_hash"],
            "constraints": constraints,
        }

    def _slot_from_payload(
        self,
        payload: Mapping[str, Any],
        *,
        event_id: str,
        parent: ConstraintSlot | None = None,
        override_target: ConstraintSlot | None = None,
    ) -> ConstraintSlot:
        slot_id = payload.get("slot_id")
        if not isinstance(slot_id, str) or not slot_id:
            raise ValueError("slot payload requires non-empty slot_id")
        if parent is not None and override_target is not None:
            raise ValueError("slot cannot be both lineage child and override replacement")
        if override_target is not None:
            parent = override_target
            overrides = (override_target.slot_id,)
        else:
            overrides = ()
        lineage = parent.lineage + (slot_id,) if parent else (slot_id,)
        content = payload.get("content")
        if not isinstance(content, Mapping) or not content:
            raise ValueError("slot payload requires non-empty structured content")
        return ConstraintSlot(
            slot_id=slot_id,
            constraint_type=str(payload.get("constraint_type", "recovery_constraint")),
            content=dict(content),
            source=str(payload.get("source", "planner")),
            mode="active",
            priority=int(payload.get("priority", 50)),
            created_event_id=event_id,
            last_updated_event_id=event_id,
            parent_slot_id=parent.slot_id if parent else None,
            overrides_slot_ids=overrides,
            lineage=lineage,
            metadata=dict(payload.get("metadata") or {}),
        )

    def _context(self, recovery_input: Mapping[str, Any]) -> PatchContext:
        information = recovery_input.get("information_budget") or {}
        information_units = int(information.get("max_prompt_tokens", 0)) + int(
            information.get("max_completion_tokens", 0)
        )
        event_source = self.prepare_context.get("event_source", "oracle")
        authorized_sources = tuple(
            self.config.get(
                "authorized_sources",
                ("task", "planner", "perception"),
            )
        )
        return PatchContext(
            actor=str(self.config.get("actor", "high_level_recovery_provider")),
            authority_priority=int(self.config.get("authority_priority", 100)),
            authorized_sources=authorized_sources,
            allow_safety_override=False,
            event_source=event_source,
            information_budget=information_units,
            policy_step_budget=self.prepare_context.get("policy_step_budget"),
            high_level_call_count=1,
            pair_key={"pair_key": recovery_input.get("pair_key")},
            task_progress=dict(recovery_input.get("task_progress") or {}),
            manual_intervention=False,
            git_commit=self.prepare_context.get("git_commit"),
            config_hash=self.prepare_context.get("config_hash"),
            checkpoint_id=self.prepare_context.get("checkpoint_id"),
            metadata={
                "adapter_version": ADAPTER_VERSION,
                "recovery_input_hash": stable_hash(recovery_input),
            },
        )

    def apply_typed_patch(
        self,
        operations: list[dict[str, Any]],
        recovery_input: dict[str, Any],
    ) -> dict[str, Any]:
        state = self._require_state()
        before = self.snapshot()
        revision = state.revision + 1
        event_id = f"recovery-event-{revision}-{stable_hash(recovery_input)[:12]}"
        patch_id = f"recovery-patch-{revision}-{stable_hash(operations)[:12]}"
        engine_operations: list[Any] = []
        returned_operations: list[dict[str, Any]] = []
        revalidations: list[dict[str, Any]] = []
        successful_revalidations: dict[str, str] = {}

        for index, operation in enumerate(operations):
            op = operation.get("op")
            target_id = operation.get("target_id")
            payload = operation.get("payload") or {}
            reason = str(operation.get("reason", "typed recovery patch"))
            if op not in PATCH_OPERATION_TYPES:
                raise ValueError(f"unsupported typed operation {op!r}")
            if not isinstance(payload, Mapping):
                raise ValueError(f"operation {index} payload must be an object")
            operation_id = f"op-{revision}-{index}-{str(op).lower()}"
            returned = {
                "op": op,
                "target_id": target_id,
                "payload": dict(payload),
                "reason": reason,
            }

            if op == "Insert":
                slot_payload = payload.get("slot", payload)
                if not isinstance(slot_payload, Mapping):
                    raise ValueError("Insert payload.slot must be an object")
                parent_id = slot_payload.get("parent_slot_id")
                parent = state.get_slot(str(parent_id)) if parent_id else None
                engine_operations.append(
                    Insert(
                        operation_id,
                        self._slot_from_payload(slot_payload, event_id=event_id, parent=parent),
                    )
                )
            elif op == "Suspend":
                engine_operations.append(Suspend(operation_id, str(target_id), reason))
            elif op == "Override":
                target = state.get_slot(str(target_id))
                replacement_payload = payload.get("replacement")
                if not isinstance(replacement_payload, Mapping):
                    raise ValueError("Override payload requires replacement object")
                replacement = self._slot_from_payload(
                    replacement_payload,
                    event_id=event_id,
                    override_target=target,
                )
                engine_operations.append(Override(operation_id, str(target_id), replacement, reason))
            elif op == "Demote":
                if "new_priority" not in payload:
                    raise ValueError("Demote payload requires new_priority")
                engine_operations.append(
                    Demote(operation_id, str(target_id), int(payload["new_priority"]), reason)
                )
            elif op == "Revalidate":
                if self.validator is None:
                    raise RuntimeError("Revalidate requires configured revalidation_validator_factory")
                evidence = {
                    "provider_evidence": dict(payload.get("evidence") or {}),
                    "observation": recovery_input.get("observation"),
                    "event": recovery_input.get("event"),
                }
                checked = revalidate_slot(state, str(target_id), evidence, self.validator)
                checked_operation = checked.operation
                engine_operations.append(checked_operation)
                result_payload = {
                    "success": checked.success,
                    "validation_id": checked.validation_id,
                    "validator_id": checked.validator_id,
                    "error_code": checked.error_code,
                    "error_message": checked.error_message,
                }
                returned["payload"] = {**dict(payload), "result": result_payload}
                record = {"target_id": str(target_id), **result_payload}
                revalidations.append(record)
                if checked.success:
                    successful_revalidations[str(target_id)] = checked.validation_id
            elif op == "Restore":
                validation_id = successful_revalidations.get(str(target_id))
                requested_validation = payload.get("validation_id")
                if not validation_id:
                    raise RuntimeError(
                        f"Restore for {target_id!r} has no successful prior Revalidate"
                    )
                if requested_validation is not None and requested_validation != validation_id:
                    raise RuntimeError("Restore validation_id does not match current revalidation")
                engine_operations.append(
                    Restore(operation_id, str(target_id), validation_id, reason)
                )
                returned["payload"] = {**dict(payload), "validation_id": validation_id}
            elif op == "Expire":
                engine_operations.append(Expire(operation_id, str(target_id), reason))
            returned_operations.append(returned)

        patch = Patch(
            patch_id=patch_id,
            event_id=event_id,
            reason="provider typed recovery patch",
            operations=tuple(engine_operations),
            generator=ADAPTER_VERSION,
            input_state_hash=state.state_hash,
            created_at=revision,
            metadata={"recovery_input_hash": stable_hash(recovery_input)},
        )
        transition = apply_patch(state, patch, self._context(recovery_input))
        if not transition.accepted:
            raise RuntimeError(
                f"CoPE engine rejected patch: {transition.rejection_code}: "
                f"{transition.rejection_reason}"
            )
        self.state = transition.state
        return {
            "state_before": before,
            "state_after": self.snapshot(),
            "operations": returned_operations,
            "revalidations": revalidations,
            "controller_prompt": self.compile_controller_prompt(),
            "transition": {
                "before_hash": transition.before_hash,
                "after_hash": transition.after_hash,
                "applied_operation_ids": list(transition.applied_operation_ids),
                "audit_record": thaw_json(transition.audit_record),
            },
        }

    def compile_controller_prompt(self) -> str:
        snapshot = self.snapshot()
        active = [
            constraint
            for constraint in snapshot["constraints"]
            if constraint["mode"] in {"active", "demoted"}
        ]
        active.sort(key=lambda item: (-int(item["priority"]), str(item["id"])))
        lines = [f"Complete the original task: {self.original_task}", "Current constraints:"]
        for constraint in active:
            content = json.dumps(
                constraint["content"],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            lines.append(
                f"- [{constraint['id']}|priority={constraint['priority']}] {content}"
            )
        return "\n".join(lines)

    def apply_operation(self, operation: dict[str, Any]) -> None:
        raise RuntimeError("production adapter requires atomic apply_typed_patch")

    def revalidate(self, target_id: str, context: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("production adapter performs revalidation inside atomic apply_typed_patch")


def create_cope_state_engine(config: dict[str, Any]) -> CoPEStateEngineAdapter:
    return CoPEStateEngineAdapter(config)
