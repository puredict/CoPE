"""Post-outcome contract-explicit diagnostic prompts for occurrence editing.

This module does not replace the frozen v1 contracts or results.  It removes
field-shape ambiguities exposed by the completed v1 failure taxonomy so a
separate diagnostic can test whether the apparent advantage survives complete
arm-native serialization instructions.
"""

from cope.occurrence_prompting import CONTRACTS as V1_CONTRACTS


CONTRACTS_V2 = {
    "cope": V1_CONTRACTS["cope"],
    "neutral_patch": """OUTPUT CONTRACT: occurrence-aware generic JSON-path transaction.
Return exactly one JSON object and no prose with exactly schema_version,
base_version,event_id,writes. schema_version is generic-compact-transaction-v1.
Copy base_version and event_id from the event. writes contains exactly these
six operations (order is irrelevant):
(1) replace /current_goal with the complete object {"all": [predicate records]};
(2) replace /plan with the complete remaining list of plan-step records;
(3) replace /commitments/<target_id>/lifecycle_status with "superseded";
(4) replace /commitments/<target_id>/valid_until with event_id;
(5) replace /commitments/<target_id>/supersession_links with [replacement_id];
(6) add /commitments/+/<replacement_id> with the complete new commitment.
Every write object has exactly op,path,value. A predicate record has exactly
predicate and arguments, where arguments is [object, region]. A plan step has
exactly step_id,skill,arguments,status,preconditions,effects,dependencies,
commitment_occurrence_id. The new commitment has exactly id,occurrence,type,
predicate,grounding,lifecycle_status,source,owner,authority,valid_from,
valid_until,dependencies,support_links,override_links,supersession_links. Its
id and occurrence come from the replacement occurrence; lifecycle_status is
active; source and owner are task_owner; authority is 100; valid_from is
event_id; valid_until is task_end; dependencies and support/supersession links
are empty; override_links is [target_id]. Preserve the witnessed done fact in
current_goal and use it as the plan dependency. Do not modify any other
historical occurrence. Do not use CoPE operation names or extra fields.""",
    "governed_delta": """OUTPUT CONTRACT: governed occurrence affected-scope delta.
Return exactly one JSON object and no prose with exactly schema_version,
event_id,read_revision,proposal_type,affected_scope,forest_delta,
blackboard_delta. schema_version is governed-delta-v1; proposal_type is repair;
read_revision is the event base version. affected_scope is exactly the sorted
two-item list [target_id,replacement_id]. forest_delta has exactly one item per
affected_scope ID, sorted by node_id. Each item has exactly the keys node_id
and after (the key is literally "after", not "after_record"). after is the
complete canonical commitment record with exactly id,occurrence,type,
predicate,grounding,lifecycle_status,source,owner,authority,valid_from,
valid_until,dependencies,support_links,override_links,supersession_links. The
target after-record is its unchanged historical record except status becomes
superseded, valid_until becomes event_id, and supersession_links becomes
[replacement_id]. The replacement after-record is active, uses the event's
replacement ID/object/occurrence, source and owner task_owner, authority 100,
valid_from event_id, valid_until task_end, empty dependencies/support/
supersession links, and override_links [target_id]. blackboard_delta has
exactly current_goal,plan,pending_restorations. current_goal is the complete
object {"all": [predicate records]}; plan is the complete list of plan-step
records; pending_restorations is empty. Predicate and plan-step record fields
must preserve the shapes already present in pre_state. Do not emit CoPE
operation names, receipts, hashes, extra fields, or unchanged forest records.""",
    "fsr_pc": """OUTPUT CONTRACT: complete occurrence-sensitive semantic state.
Return exactly one JSON object and no prose with exactly current_goal,entities,
commitments,progress_ledger,plan,pending_restorations. Copy all unchanged
semantic records byte-for-byte in content. current_goal has exactly {"all":
[predicate records]}; predicate records have predicate and arguments. Every
commitment has exactly id,occurrence,type,predicate,grounding,lifecycle_status,
source,owner,authority,valid_from,valid_until,dependencies,support_links,
override_links,supersession_links. Retire only target_id by setting status to
superseded, valid_until to event_id, and supersession_links to [replacement_id].
Add one active replacement record whose id and occurrence exactly match the
event, with override_links [target_id]. The plan uses replacement_id as its
commitment_occurrence_id and preserves the witnessed done commitment as its
dependency. Trusted code supplies nonsemantic versions. Do not return
metadata, patch fields, prose, or extra fields.""",
    "full_replan": """OUTPUT CONTRACT: occurrence-aware full remaining-task replan.
Return exactly one JSON object and no prose with exactly schema_version,
event_id,base_version,completed_facts,remaining_ordered_occurrences,
retired_commitment_occurrences. schema_version is
occurrence-full-replan-v1. Copy event_id and base_version. Each completed_facts
item has exactly predicate and arguments, with arguments [object,region]; list
only the witnessed done fact. remaining_ordered_occurrences is a list of
occurrence-ID strings only (not objects or plan records) and contains exactly
replacement_id. retired_commitment_occurrences is the complete ordered list of
all superseded/cancelled occurrence-ID strings from pre_state plus target_id,
in the same commitment-record order as the resulting state. Do not return
patches, persistent state, plan-step objects, receipts, hashes, or extra
fields.""",
}


# Filled with literal hashes before the diagnostic runner is committed.
EXPECTED_CONTRACT_HASHES_V2 = {
    "cope": "673f4a2728cc9a77fc8f19cc098ee2b8866306530f1e889827759a7eaf5c949b",
    "neutral_patch": "3bb943f9e02627a9d1ef0b8ef07b44ec39f4f306ab856e5694bf8fb887696c86",
    "governed_delta": "1c9bc4dbc4f7244867244cf4451724a86347c590d89d77df76f474af2ceb50fd",
    "fsr_pc": "dc42c3deeb1b891cb579b64e58217704c3d24f0302659a16913a2d52a52b6111",
    "full_replan": "fa39e1babb4ef970c15ee6d121c4b6a06d5f760961f63fabfcad50ad537da1a9",
}
