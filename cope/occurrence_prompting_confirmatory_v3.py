"""Outcome-locked contracts for the held-out occurrence confirmation run.

The v3 contracts are frozen before any v3 provider call.  They use the exact
input field names and remove the path-concatenation ambiguity identified in
the separate v2 diagnostic.  No v1 or v2 artifact is replaced.
"""

from cope.occurrence_prompting import ARMS


CONTRACTS_V3 = {
    "cope": """OUTPUT CONTRACT: occurrence-addressed CoPE commitment delta.
Return exactly one JSON object and no prose with exactly event_id,operation,
patch_id,target_id,base_version,replacement_id. operation is Override.
event_id equals event.event_id; target_id equals event.target_commitment_id;
base_version equals event.valid_from_state_version; replacement_id equals
event.replacement_commitment_id. patch_id is fresh and nonempty. target_id
addresses the active temporal occurrence and replacement_id addresses the new
authorized occurrence, even when the same grounded predicate has an older
historical record. Do not reactivate or overwrite a historical occurrence.
Do not return state, receipt, history, hashes, actions, or extra fields.""",
    "neutral_patch": """OUTPUT CONTRACT: occurrence-aware generic JSON-path transaction.
Return exactly one JSON object and no prose with exactly schema_version,
base_version,event_id,writes. schema_version is generic-compact-transaction-v1;
base_version equals event.valid_from_state_version; event_id equals
event.event_id. writes contains exactly these six operations (order is
irrelevant): (1) replace /current_goal with the complete object {"all":
[predicate records]}; (2) replace /plan with the complete one-item remaining
list of plan-step records; (3) replace
/commitments/<target>/lifecycle_status with "superseded"; (4) replace
/commitments/<target>/valid_until with event.event_id; (5) replace
/commitments/<target>/supersession_links with [replacement]; (6) add the
complete new commitment at /commitments/+/<replacement>. Here <target> means
the literal value of event.target_commitment_id and <replacement> means the
literal value of event.replacement_commitment_id. Path construction is literal
concatenation: if replacement were goal:in:item_1:box_region@2, the add path
would be /commitments/+/goal:in:item_1:box_region@2. The add path must not end
in "/" and must not contain angle brackets. Every write has exactly op,path,
value. A predicate record has exactly predicate,arguments, where arguments is
[object,region]. A plan step has exactly step_id,skill,arguments,status,
preconditions,effects,dependencies,commitment_occurrence_id. The new
commitment has exactly id,occurrence,type,predicate,grounding,lifecycle_status,
source,owner,authority,valid_from,valid_until,dependencies,support_links,
override_links,supersession_links. Its id is
event.replacement_commitment_id, occurrence is event.replacement_occurrence,
grounding is [event.replacement_object,event.replacement_target], status is
active, source and owner are task_owner, authority is 100, valid_from is
event.event_id, valid_until is task_end, dependencies/support/supersession
links are [], and override_links is [event.target_commitment_id]. Do not put
the plan dependency in the commitment dependencies field. Preserve the
witnessed done fact in current_goal. The one pending plan step executes the
replacement and its dependencies list contains exactly the satisfied done
commitment ID from pre_state. Do not modify any other historical occurrence.
Do not use CoPE operation names or extra fields.""",
    "governed_delta": """OUTPUT CONTRACT: governed occurrence affected-scope delta.
Return exactly one JSON object and no prose with exactly schema_version,
event_id,read_revision,proposal_type,affected_scope,forest_delta,
blackboard_delta. schema_version is governed-delta-v1; event_id equals
event.event_id; proposal_type is repair; read_revision equals
event.valid_from_state_version. Define target as event.target_commitment_id and
replacement as event.replacement_commitment_id. affected_scope is exactly the
lexicographically sorted two-item list containing target and replacement; do
not select another historical record with the same grounding. forest_delta
has exactly one item for target and one for replacement, sorted by node_id.
Each item has exactly node_id and after (the key is literally "after"). after
is the complete canonical commitment record with exactly id,occurrence,type,
predicate,grounding,lifecycle_status,source,owner,authority,valid_from,
valid_until,dependencies,support_links,override_links,supersession_links. The
target after-record is its unchanged pre_state record except status becomes
superseded, valid_until becomes event.event_id, and supersession_links becomes
[replacement]. The replacement after-record is active, has id replacement,
occurrence event.replacement_occurrence, grounding
[event.replacement_object,event.replacement_target], source and owner
task_owner, authority 100, valid_from event.event_id, valid_until task_end,
empty dependencies/support/supersession links, and override_links [target].
blackboard_delta has exactly current_goal,plan,pending_restorations.
current_goal preserves the witnessed done fact and adds the replacement fact;
plan is the complete one-item pending replacement step whose dependencies list
contains exactly the satisfied done commitment ID; pending_restorations is [].
Predicate and plan-step shapes match pre_state. Do not emit CoPE operation
names, receipts, hashes, extra fields, or unchanged forest records.""",
    "fsr_pc": """OUTPUT CONTRACT: complete occurrence-sensitive semantic state.
Return exactly one JSON object and no prose with exactly current_goal,entities,
commitments,progress_ledger,plan,pending_restorations. Copy all unchanged
semantic records byte-for-byte in content. Define target as
event.target_commitment_id and replacement as event.replacement_commitment_id.
current_goal has exactly {"all": [predicate records]}; predicate records have
predicate and arguments. Every commitment has exactly id,occurrence,type,
predicate,grounding,lifecycle_status,source,owner,authority,valid_from,
valid_until,dependencies,support_links,override_links,supersession_links.
Retire only target by setting status to superseded, valid_until to
event.event_id, and supersession_links to [replacement]. Add one active
replacement whose id is replacement, occurrence is event.replacement_occurrence,
grounding is [event.replacement_object,event.replacement_target], valid_from is
event.event_id, and override_links is [target]. Its dependencies,
support_links, and supersession_links are []. The complete one-item pending
plan uses replacement as commitment_occurrence_id and preserves the satisfied
done commitment ID as its only dependency. Trusted code supplies nonsemantic
versions. Do not return metadata, patch fields, prose, or extra fields.""",
    "full_replan": """OUTPUT CONTRACT: occurrence-aware full remaining-task replan.
Return exactly one JSON object and no prose with exactly schema_version,
event_id,base_version,completed_facts,remaining_ordered_occurrences,
retired_commitment_occurrences. schema_version is
occurrence-full-replan-v1; event_id equals event.event_id; base_version equals
event.valid_from_state_version. Each completed_facts item has exactly
predicate and arguments, with arguments [object,region]; list only the
witnessed done fact. remaining_ordered_occurrences is a list of occurrence-ID
strings only and contains exactly event.replacement_commitment_id.
retired_commitment_occurrences is the complete ordered list of all records in
pre_state.commitments whose lifecycle_status is superseded or cancelled,
followed by event.target_commitment_id; preserve pre_state commitment-record
order and do not include satisfied records. Do not return patches, persistent
state, plan-step objects, receipts, hashes, or extra fields.""",
}


if tuple(CONTRACTS_V3) != ARMS:
    raise RuntimeError("v3 arm order drift")


# Filled with literal values before the first v3 provider call.
EXPECTED_CONTRACT_HASHES_V3 = {
    "cope": "d8609008349c9edf3c1671eb42d592c610778c70d8011052d37dddb60b2de99c",
    "neutral_patch": "734bc9dbc2a1b5fb43256516b02f2d0c10d0754fcdaefab3a1efdf9efcedaabe",
    "governed_delta": "5d43dfdd05f9d41a241a9ff18e3e76c49c133edadffca6aebf1d4b6807ad1199",
    "fsr_pc": "124878e813078a42f1eb1998ac5b1af82b0899bef445cedef6d25fd757191c4b",
    "full_replan": "3ffc4f83a689b0b4a1356e8a171986cf561362b4882d260e45b8c2447dd90204",
}
