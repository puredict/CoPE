# Neutral baseline identifiability correction

Date: 2026-08-04

Before any formal provider call, audit found that the provisional neutral arm
used anonymized labels (`N01`/`N02`) and then translated them into the same
typed `Override`/`Expire` engine used by CoPE.  That arm was isomorphic to CoPE
and could not identify the value of typed constraint operations; a tie would be
nearly built into the interface.

The frozen neutral arm is corrected to the originally specified baseline: a
generic JSON-path transaction over the same persistent commitment state.  It
receives identical public input and uses the same final semantic validator, but
its model must specify generic add/replace paths and values rather than CoPE
operation types.  Trusted code supplies only transaction-owned version and
evidence fields.

The arm label remains `neutral_patch` to preserve the formal manifest and
analysis schema.  Its implementation and prompt contract are no longer the
provisional N01/N02 adapter.  The corrected four-arm oracle gate and 320-request
cold preflight must both pass again before formal calls.  Historical gate v1--v3
results remain diagnostic and are not the final formal qualification.
