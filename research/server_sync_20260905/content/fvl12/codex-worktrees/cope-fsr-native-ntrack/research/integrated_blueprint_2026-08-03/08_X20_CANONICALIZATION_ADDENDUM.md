# X20 addendum: canonical record ordering is resolved

Date: 2026-08-03 (Asia/Shanghai)

This addendum updates, but does not rewrite, the X10--X18 integration snapshot.
The original claim ledger remains preserved as preregistered evidence.

## Protocol decision

Adopt `stable-record-order-v1` at the state boundary:

1. validate collection and record shape;
2. require string stable keys and reject duplicates;
3. sort `commitments` and `entities` by `id`, and `progress_ledger` by
   `milestone_id`;
4. validate the normalized stored pre-state and normalized candidate;
5. publish and hash only normalized state;
6. include the normalization version in receipts.

Do not reorder plan actions, restoration records, goal atoms, grounding
arguments, or any sequence whose order may carry execution or logical meaning.
Existing receipts are not silently reinterpreted; migration creates a new
protocol version with before/after provenance.

## Evidence

- clean semantic/idempotence controls: 12/12;
- legacy clean states already in strict order: 0/12;
- normalized clean states in strict order: 12/12;
- strict rejection of known reorder candidates: 14/14;
- normalize-and-accept on the same candidates: 14/14;
- normalized candidate/reference bytes and hashes equal: 14/14;
- malformed, duplicate, or missing stable-key faults rejected: 7/7;
- aggregate median normalization time: 100,979 ns;
- independent audit: 11/11;
- focused tests: 4 passed;
- full repository regression: 436 passed.

No learned provider, credential, GPU, simulator, robot, or reserved LIBERO
state 27--49 was used. This resolves a protocol issue on small synthetic states;
it is not an embodied or learned-policy performance claim.

## Claim-ledger update

The X19 row `Canonical list order is irrelevant` changes from `OPEN` to
`SUPPORTED_FOR_STABLE_KEY_RECORD_COLLECTIONS`. The unrestricted wording remains
rejected: order is not assumed irrelevant for semantic sequences.

Full evidence package:
`research/canonical_order_policy_2026-08-03/03_RESULT_AND_PROTOCOL_DECISION.md`.
