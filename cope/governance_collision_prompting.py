"""Frozen learned-output contract for the governed-delta collision control."""

from __future__ import annotations


GOVERNED_DELTA_CONTRACT = """OUTPUT CONTRACT: governed affected-scope state delta.
Return exactly one JSON object and no prose. The exact top-level fields are
schema_version, event_id, read_revision, proposal_type, affected_scope,
forest_delta, blackboard_delta. schema_version is governed-delta-v1.
event_id equals event.event_id and read_revision equals
task_progress.pre_state.state_version. proposal_type is repair.
affected_scope is the complete sorted list of stable commitment IDs whose
records change or are added. forest_delta contains exactly one object per
affected ID with exactly node_id and after; after is the complete canonical
post-event commitment record for that node. blackboard_delta contains exactly
current_goal, plan, pending_restorations and supplies their complete post-event
values. For replacement, retire the active target and add the replacement
commitment. For cancellation, retire only the active target. Preserve completed
and inactive historical commitments by omitting unchanged records. Do not emit
CoPE operation names, patch IDs, transaction receipts, hashes, state/evidence
versions, controller actions, markdown, prose, or extra fields."""

