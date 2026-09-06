"""Method instructions for the same fixed model and same input packet."""

from __future__ import annotations

from .models import ModelPacket, canonical_json
from .operations import OPERATIONS


COMMON_RULES = """
You are the task-state adaptation component in a controlled robot experiment.
Return exactly one JSON object and no prose, markdown, or code fence.
Serialize compact JSON: no indentation and no unnecessary whitespace outside strings.
Never omit, rename, summarize, compress, or invent identifiers.
The event is authoritative. Preserve completed progress and every hard safety rule.
The task uses stable slot ids. A workflow's downstream plan is part of its identity:
do not infer it from the primary object and target.
/no_think
""".strip()


def development_examples():
    """Fixed interface demonstrations, independent of every evaluation seed."""
    examples = []
    new_slot = {
        "slot_id": "dev/order-alpha/temporary", "logical_id": "dev/order-alpha",
        "grounding": "deliver_demo_item_to_station_C", "priority": "soft",
        "payload": {"object": "demo_item", "target": "station_C",
                    "plan": [{"object": "demo_item", "target": "station_C"}]},
    }
    for index, definition in enumerate(OPERATIONS.values(), 1):
        current_id = "dev/order-alpha/root"
        if definition.name == "restore_root":
            current_id = new_slot["slot_id"]
        event = {"event_id": f"dev/interface-{index}", "kind": definition.event_kind,
                 "current_slot_id": current_id}
        operation = {"op": definition.name}
        for argument in definition.arguments:
            operation[argument] = dict(new_slot) if argument == "new_slot" else current_id
        if definition.name == "override":
            event["new_slot"] = dict(new_slot)
        examples.append({
            "input_excerpt": {"current_state_revision": index - 1, "event": event},
            "output": {"schema_version": "cope-lineage-patch-v1",
                       "event_id": event["event_id"], "base_revision": index - 1,
                       "ops": [operation]},
        })
    return examples


_OPERATION_INSTRUCTIONS = "\n".join(
    f"Input event.kind={definition.event_kind!r} maps to output op={definition.name!r}; "
    f"required arguments: {', '.join(definition.arguments)}."
    for definition in OPERATIONS.values()
)

COPE_SYSTEM_PROMPT = COMMON_RULES + """

METHOD: CoPE persistent typed patch.
Read current_state but emit only the minimal patch for the current event.
The exact top-level form is:
{"schema_version":"cope-lineage-patch-v1","event_id":STRING,
 "base_revision":INTEGER,"ops":[OPERATION]}

Use exactly one operation. Input event kinds and output op values are different
namespaces. Never put an event kind into op unless that is also its canonical
operation name. slot_id or from_slot_id is the event current_slot_id;
new_slot is an exact JSON-value copy of event.new_slot.
""" + _OPERATION_INSTRUCTIONS + """
Do not emit lineage or lifecycle history. The persistent state store owns those
fields and applies the typed operation atomically.
Four independent development examples (the input excerpts omit unrelated data;
the outputs shown are complete patches; replace every demo id using your input):
""" + "\n".join(canonical_json(example) for example in development_examples())


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
