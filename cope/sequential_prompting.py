"""Frozen common input and arm contracts for sequential formal calls."""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

from cope.types import InformationBudget, RecoveryInput


MODEL = "qwen/qwen3.5-flash-02-23"
REASONING_EFFORT = "none"
TEMPERATURE = 0.0
SEED_BASE = 20260804
MAX_PROMPT_TOKENS = 12000
MAX_COMPLETION_TOKENS = 4096
TIMEOUT_SECONDS = 90.0
ARMS = ("cope", "neutral_patch", "fsr_pc", "full_replan")


CONTRACTS = {
    "cope": """OUTPUT CONTRACT: sequential CoPE typed commitment patch.
Return exactly one JSON object and no prose. Exact fields are event_id,
operation, patch_id, target_id, base_version, plus replacement_id only for a
replacement. operation is Override for replacement and Expire for cancellation.
Copy event_id, target_id and base_version from the event. replacement_id is the
stable goal commitment ID for event.replacement_object. patch_id is fresh and
nonempty. Edit only the active target. Do not return state, receipt, history,
hashes, controller actions, transaction metadata, or extra fields.""",
    "neutral_patch": """OUTPUT CONTRACT: neutral sequential sparse patch.
Return exactly one JSON object and no prose. Exact fields are event_id,
operation, patch_id, target_id, base_version, plus replacement_id only for a
replacement. operation is N01 for replacement and N02 for cancellation. N01
deactivates the named active target and activates the named replacement; N02
deactivates the named active target without replacement. Copy IDs and version
from the event. Do not emit CoPE names, state, receipt, history, hashes,
controller actions, transaction metadata, or extra fields.""",
    "fsr_pc": """OUTPUT CONTRACT: sequential FSR-PC complete semantic state.
Return exactly one JSON object with exactly current_goal, entities, commitments,
progress_ledger, plan, pending_restorations. Regenerate the complete post-event
semantic state from task_progress.pre_state and event. Preserve the satisfied
physical fact and every historical inactive commitment; update only the event
target and add a replacement only when requested. Trusted code supplies schema,
state and evidence versions. Do not return metadata, receipt, hashes, patch
fields, controller actions, prose, or extra fields.""",
    "full_replan": """OUTPUT CONTRACT: full remaining-task replan.
Return exactly one JSON object with schema_version, event_id, base_version,
completed_facts, remaining_ordered_objects, retired_commitment_ids.
schema_version is full-replan-v1. Copy event_id and base_version from the event.
completed_facts is the complete immutable list of witnessed completed physical
predicates. remaining_ordered_objects is the complete ordered list still to
execute after this event. retired_commitment_ids lists every superseded or
cancelled historical commitment in task_progress.pre_state plus the current
event target. Do not return patches, persistent state, receipt, hashes,
controller actions, prose, or extra fields.""",
}


def build_sequential_recovery_input(
    *,
    sequence_id: str,
    task_id: int,
    state_id: int,
    event: Mapping[str, Any],
    pre_state: Mapping[str, Any],
    physically_true_objects: Sequence[str],
    processed_event_ids: Sequence[str],
    event_index: int,
) -> RecoveryInput:
    return RecoveryInput(
        schema_version="sequential-recovery-input-v1",
        pair_key=f"{sequence_id}:event{event_index}",
        original_task=(
            "put both the alphabet soup and the tomato sauce in the basket"
        ),
        observation={
            "source": "post_prefix_runtime",
            "task_id": int(task_id),
            "state_id": int(state_id),
            "rgb_observation_sha256": "RUNTIME_BOUND_BEFORE_PROVIDER_CALL",
        },
        event=copy.deepcopy(dict(event)),
        public_action_history=(
            {
                "phase": "completed_prefix",
                "done_object": str(event["done_object"]),
                "physically_verified": True,
            },
        ),
        task_progress={
            "pre_state": copy.deepcopy(dict(pre_state)),
            "physically_true_objects": list(physically_true_objects),
            "trusted_processed_event_ids": list(processed_event_ids),
            "transition_rules": {
                "authorization": "task_owner authority 100 edits only target",
                "version": "event base version equals pre-state version",
                "history": "preserve all satisfied and inactive commitments",
                "idempotence": "reject already processed event IDs",
            },
        },
        information_budget=InformationBudget(
            event_fields=tuple(sorted(str(key) for key in event)),
            history_fields=("phase", "done_object", "physically_verified"),
            observation_fields=(
                "source",
                "task_id",
                "state_id",
                "rgb_observation_sha256",
            ),
            max_high_level_calls=1,
            max_prompt_tokens=MAX_PROMPT_TOKENS,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
        ),
    )
