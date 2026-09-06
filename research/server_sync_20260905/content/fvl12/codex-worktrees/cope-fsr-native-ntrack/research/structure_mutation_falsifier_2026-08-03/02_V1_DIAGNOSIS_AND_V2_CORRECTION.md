# X18 v1 failure diagnosis and frozen v2 correction

Recorded before validator correction on 2026-08-03 (Asia/Shanghai).

## V1 outcome

- retained changed mutations: 2352/2352;
- exact validator rejected: 2352/2352;
- decomposed validator rejected: 2334/2352;
- frozen order-only divergences: 14;
- dangerous blind spots: 4;
- crashes / caller mutations: 0 / 0;
- decision: **FAIL**.

The four dangerous accepts are:

| Case | Mutation | Operator | Path |
|---|---|---|---|
| replace_pending_target | S0130 | add_unknown_field | `/commitments/1` |
| continuity_invalid | S0123 | add_unknown_field | `/commitments/1` |
| cancel_sibling | S0106 | add_unknown_field | `/commitments/1` |
| activate_override | S0123 | add_unknown_field | `/commitments/1` |

## Root cause

For an event-affected target commitment, the validator compares every known
pre-state field except the explicitly allowed lifecycle change. It did not also
require the post record's field set to equal the canonical commitment schema.
An extra unknown field was therefore ignored. Unaffected records and newly
created records already receive whole-record or exact-construction checks, which
is why only these four cases escaped.

## Frozen v2 correction

Add one schema check to `identity_lifecycle`: every post-state commitment record
must contain exactly the frozen commitment fields
`id,predicate,grounding,lifecycle_status,source,owner,authority,valid_from,valid_until,dependencies,support_links,override_links,supersession_links`.

Do not change the mutation grammar, traversal order, deduplication, order-only
allowlist, dangerous classification, cases, or gates. Preserve `run_v1` and run
the corrected validator into a new `run_v2` directory. Add a focused regression
test for an unknown field on an affected target.
