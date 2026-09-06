"""Method-neutral transaction syntax over the same semantic facts and kernel."""

from .patch_contract import (BASE_PROPERTIES, CHECK_PROPERTIES, MAPPING, NEW_SLOT_SCHEMA,
                             RELATIONS, STRING, STRINGS, obj)

GENERIC_VERSION = "generic-persistent-v2/tx-1"
ASSERTION_SCHEMA = obj({**CHECK_PROPERTIES, "kind": {"const": "validation"}})
WRITE_SCHEMA = obj({"occurrence_id": STRING,
    "path": {"enum": ["/lifecycle", "/priority", "/grounding_validity", "/restore_guard", "/dependency_ids"]},
    "value": {}, "assertion_id": STRING}, required=["occurrence_id", "path", "value"])
GENERIC_TRANSACTION_SCHEMA = obj({**BASE_PROPERTIES,
    "schema_version": {"const": GENERIC_VERSION},
    "assertions": {"type": "array", "items": ASSERTION_SCHEMA},
    "creates": {"type": "array", "items": obj({"request_id": STRING, "slot": NEW_SLOT_SCHEMA})},
    "writes": {"type": "array", "items": WRITE_SCHEMA},
    "relation_additions": RELATIONS, "relation_removals": RELATIONS,
    "evidence_links": {"type": "array", "items": obj({"occurrence_id": STRING, "evidence_ids": STRINGS})},
})
