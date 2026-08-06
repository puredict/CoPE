"""CoPE patch-trace auditability evaluation toolkit.

The public modules intentionally operate on JSON-compatible dictionaries.  This
keeps the evaluator usable while the state-semantics branch is still evolving
and lets :mod:`auditability.schema_adapter` be the only compatibility boundary.
"""

SCHEMA_VERSION = "auditability.v1"

__all__ = ["SCHEMA_VERSION"]
