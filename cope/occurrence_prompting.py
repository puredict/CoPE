"""Frozen five-arm prompt contracts for occurrence-sensitive learned calls."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from cope.sequential_prompting import (
    MAX_COMPLETION_TOKENS, MAX_PROMPT_TOKENS, MODEL, REASONING_EFFORT,
    TEMPERATURE, TIMEOUT_SECONDS,
)
from cope.types import InformationBudget, RecoveryInput


ARMS = ("cope", "neutral_patch", "governed_delta", "fsr_pc", "full_replan")

CONTRACTS = {
    "cope": """OUTPUT CONTRACT: occurrence-addressed CoPE commitment delta.
Return exactly one JSON object and no prose. Exact fields are event_id,
operation, patch_id, target_id, base_version, replacement_id. operation is
Override. Copy event_id, target_id, base_version, and replacement_id from the
event; patch_id is fresh and nonempty. target_id addresses the active temporal
occurrence and replacement_id addresses the new authorized occurrence, even
when both occurrences have the same grounded predicate as an older historical
record. Do not reactivate or overwrite a historical occurrence. Do not return
state, receipt, history, hashes, controller actions, or extra fields.""",
    "neutral_patch": """OUTPUT CONTRACT: occurrence-aware generic JSON-path transaction.
Return exactly one JSON object with schema_version, base_version, event_id,
writes. schema_version is generic-compact-transaction-v1. Copy base_version and
event_id from the input. writes is the minimum list of objects with exactly op,
path,value. Legal paths are /current_goal, /plan, /pending_restorations,
/commitments/<occurrence-id>/<existing-field>, and
/commitments/+/<new-occurrence-id>. Root writes replace complete values and a
new commitment add supplies its complete record. Preserve every satisfied and
superseded occurrence; insert the new replacement occurrence and never
reactivate an older record. Do not use CoPE operation names or extra fields.""",
    "governed_delta": """OUTPUT CONTRACT: governed occurrence affected-scope delta.
Return exactly one JSON object with schema_version,event_id,read_revision,
proposal_type,affected_scope,forest_delta,blackboard_delta. schema_version is
governed-delta-v1; proposal_type is repair. affected_scope is the complete
sorted list of changed or added occurrence IDs. forest_delta contains exactly
node_id and the complete canonical after-record for each affected occurrence.
blackboard_delta contains exactly complete current_goal, plan, and
pending_restorations values. Preserve historical occurrences by omitting
unchanged records; add a new occurrence instead of reactivating an old one. Do
not emit CoPE operation names, receipts, hashes, prose, or extra fields.""",
    "fsr_pc": """OUTPUT CONTRACT: complete occurrence-sensitive semantic state.
Return exactly one JSON object with exactly current_goal, entities, commitments,
progress_ledger, plan, pending_restorations. Regenerate the complete post-event
semantic state. Preserve every satisfied and superseded occurrence with its
original lifetime, retire the active target, and add the new replacement
occurrence. Trusted code supplies schema/state/evidence versions. Do not return
metadata, receipts, patch fields, controller actions, prose, or extra fields.""",
    "full_replan": """OUTPUT CONTRACT: occurrence-aware full remaining-task replan.
Return exactly one JSON object with schema_version,event_id,base_version,
completed_facts,remaining_ordered_occurrences,retired_commitment_occurrences.
schema_version is occurrence-full-replan-v1. Copy event_id and base_version.
completed_facts is the complete witnessed physical fact list;
remaining_ordered_occurrences is the complete ordered list still to execute;
retired_commitment_occurrences lists every superseded/cancelled occurrence.
Do not return patches, persistent state, receipts, hashes, prose, or extra fields.""",
}


def build_recovery_input(
    *, case_id: str, pre_state: Mapping[str, Any], event: Mapping[str, Any],
) -> RecoveryInput:
    done = str(event["done_object"])
    return RecoveryInput(
        schema_version="occurrence-recovery-input-v1", pair_key=case_id,
        original_task=(
            "maintain the witnessed basket item and execute the currently "
            "authorized pending commitment occurrence"
        ),
        observation={
            "source": "symbolic_occurrence_formal",
            "case_id": case_id,
            "rgb_observation_sha256": "NOT_APPLICABLE_SYMBOLIC_FORMAL",
        },
        event=copy.deepcopy(dict(event)),
        public_action_history=({
            "phase": "completed_prefix", "done_object": done,
            "physically_verified": True,
        },),
        task_progress={
            "pre_state": copy.deepcopy(dict(pre_state)),
            "physically_true_objects": [done],
            "transition_rules": {
                "identity": "predicate grounding and temporal occurrence ID are distinct",
                "history": "never reactivate or overwrite a historical occurrence",
                "version": "event base version equals pre-state version",
                "scope": "edit only the active target and new replacement occurrence",
            },
        },
        information_budget=InformationBudget(
            event_fields=tuple(sorted(str(key) for key in event)),
            history_fields=("phase", "done_object", "physically_verified"),
            observation_fields=("source", "case_id", "rgb_observation_sha256"),
            max_high_level_calls=1, max_prompt_tokens=MAX_PROMPT_TOKENS,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
        ),
    )
