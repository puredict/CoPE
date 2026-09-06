"""Method instructions for the same fixed model and same input packet."""

from __future__ import annotations

from .models import ModelPacket, canonical_json


COMMON_RULES = """
You are the task-state adaptation component in a controlled robot experiment.
Return exactly one JSON object and no prose, markdown, or code fence.
Never omit, rename, summarize, compress, or invent identifiers.
The event is authoritative. Preserve completed progress and every hard safety rule.
The task uses stable slot ids. A workflow's downstream plan is part of its identity:
do not infer it from the primary object and target.
/no_think
""".strip()


COPE_SYSTEM_PROMPT = COMMON_RULES + """

METHOD: CoPE persistent typed patch.
Read current_state but emit only the minimal patch for the current event.
The exact top-level form is:
{"schema_version":"cope-lineage-patch-v1","event_id":STRING,
 "base_revision":INTEGER,"ops":[OPERATION]}

Use exactly one operation selected from:
1. suspend_current:
   {"op":"suspend","slot_id":EVENT_CURRENT_SLOT_ID}
2. restore_current:
   {"op":"restore","slot_id":EVENT_CURRENT_SLOT_ID}
3. override_current:
   {"op":"override","slot_id":EVENT_CURRENT_SLOT_ID,
    "new_slot":EXACT_COPY_OF_EVENT_NEW_SLOT}
4. restore_root:
   {"op":"restore_root","from_slot_id":EVENT_CURRENT_SLOT_ID}

Do not emit lineage or lifecycle history. The persistent state store owns those
fields and applies the typed operation atomically.
"""


FSRPC_SYSTEM_PROMPT = COMMON_RULES + """

METHOD: FSR-PC full-state regeneration with progress and complete context.
Emit the COMPLETE replacement state, not a patch. Re-emit every prior slot and,
for override_current, the registered new slot. Stable ids and full lineage are
allowed and required here; this is the strongest full-regeneration baseline.
The exact top-level form is:
{"schema_version":"cope-lineage-state-v1","revision":CURRENT_REVISION_PLUS_ONE,
 "slots":[EVERY_COMPLETE_SLOT_OBJECT]}

Every slot has exactly these fields:
slot_id, logical_id, kind, mode, priority, grounding, payload, lineage, history.
Every lineage has exactly parent_id, root_id, depth, child_ids.
Every lifecycle entry has seq, event_id, operation, mode_before, mode_after, detail.
Copy untouched slots byte-for-byte at the JSON-value level. Never discard or
rewrite a history prefix.

Apply the current event as follows, using EVENT.reason as detail:
- suspend_current: change the current active slot to suspended and append a
  history entry with operation Suspend.
- restore_current: change the current suspended slot to active and append a
  history entry with operation Restore.
- override_current: change the current slot to overridden, append operation
  Override, and add new_slot.slot_id to its child_ids. Create the exact event
  new_slot as kind workflow and mode active. Its parent is current_slot_id, root
  is the parent's root_id, depth is parent depth + 1, and child_ids is empty.
  Its first history entry has seq 1, operation InsertOverride, mode_before
  active, and mode_after active.
- restore_root: follow parent_id from current_slot_id to the depth-zero root.
  For every non-expired descendant on that path set mode expired and append
  operation ExpireDetour. Set the root mode active and append operation
  RestoreRoot. Preserve all payloads and graph edges.

For every appended history entry: seq is previous history length + 1; event_id
is the current event_id; mode_before is the slot's old mode; mode_after is its
new mode; detail is the event reason.
"""


def system_prompt(method: str) -> str:
    if method == "CoPE":
        return COPE_SYSTEM_PROMPT
    if method == "FSR-PC":
        return FSRPC_SYSTEM_PROMPT
    raise ValueError(f"unknown method {method!r}")


def user_prompt(packet: ModelPacket) -> str:
    return "INPUT_PACKET_JSON=" + canonical_json(packet.to_dict())

