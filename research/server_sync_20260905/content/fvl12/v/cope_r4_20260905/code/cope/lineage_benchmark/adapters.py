"""LLM-backed CoPE patch and FSR-PC full-regeneration adapters."""

from __future__ import annotations

from typing import Dict, Type

from .client import ModelClient
from .models import AdaptationResult, ModelPacket, WorkflowState
from .state import (
    StateValidationError,
    apply_patch_document,
    state_semantic_match,
    validate_regenerated_transition,
)
from .reference import reference_transition


def _oracle_after(packet: ModelPacket) -> WorkflowState:
    return reference_transition(
        packet.current_state,
        packet.event,
        str(packet.task_contract["critical_logical_id"]),
    )


def _semantic_diagnostic(packet, candidate, generation) -> bool:
    # A prior coherent but incorrect committed state can make the registered
    # transition undefined. This is a scored task error, not an evaluator crash
    # and never a reason to silently replace the candidate with a reference.
    try:
        return state_semantic_match(candidate, _oracle_after(packet))
    except (ValueError, KeyError, TypeError) as exc:
        generation.telemetry["reference_transition_error"] = str(exc)
        return False


class ModelAdapter:
    method = ""

    def __init__(self, client: ModelClient) -> None:
        self.client = client

    def adapt(self, packet: ModelPacket) -> AdaptationResult:
        raise NotImplementedError


class CoPEModelAdapter(ModelAdapter):
    method = "CoPE"

    def adapt(self, packet: ModelPacket) -> AdaptationResult:
        generation = self.client.generate(
            method=self.method,
            packet=packet,
            max_output_tokens=int(packet.compute_budget["max_output_tokens"]),
            timeout_s=float(packet.compute_budget["timeout_s"]),
        )
        if not generation.ok or generation.parsed is None:
            return AdaptationResult(
                False, generation.status, packet.current_state, generation
            )
        try:
            candidate = apply_patch_document(
                packet.current_state,
                generation.parsed,
                packet.event,
                str(packet.task_contract["critical_logical_id"]),
            )
        except (StateValidationError, ValueError, TypeError, KeyError) as exc:
            return AdaptationResult(
                False,
                "schema_validation_failure",
                packet.current_state,
                generation,
                validation_errors=[str(exc)],
                output_document=generation.parsed,
            )
        return AdaptationResult(
            True,
            "ok",
            candidate,
            generation,
            semantic_match=_semantic_diagnostic(packet, candidate, generation),
            output_document=generation.parsed,
        )


class FSRPCModelAdapter(ModelAdapter):
    method = "FSR-PC"

    def adapt(self, packet: ModelPacket) -> AdaptationResult:
        generation = self.client.generate(
            method=self.method,
            packet=packet,
            max_output_tokens=int(packet.compute_budget["max_output_tokens"]),
            timeout_s=float(packet.compute_budget["timeout_s"]),
        )
        if not generation.ok or generation.parsed is None:
            return AdaptationResult(
                False, generation.status, packet.current_state, generation
            )
        try:
            candidate = WorkflowState.from_dict(generation.parsed)
        except (ValueError, TypeError, KeyError) as exc:
            return AdaptationResult(
                False,
                "schema_validation_failure",
                packet.current_state,
                generation,
                validation_errors=[str(exc)],
                output_document=generation.parsed,
            )
        errors = validate_regenerated_transition(
            packet.current_state,
            candidate,
            packet.event,
            str(packet.task_contract["critical_logical_id"]),
        )
        if errors:
            return AdaptationResult(
                False,
                "schema_validation_failure",
                packet.current_state,
                generation,
                validation_errors=errors,
                output_document=generation.parsed,
            )
        return AdaptationResult(
            True,
            "ok",
            candidate,
            generation,
            semantic_match=_semantic_diagnostic(packet, candidate, generation),
            output_document=generation.parsed,
        )


ADAPTERS: Dict[str, Type[ModelAdapter]] = {
    "CoPE": CoPEModelAdapter,
    "FSR-PC": FSRPCModelAdapter,
}
