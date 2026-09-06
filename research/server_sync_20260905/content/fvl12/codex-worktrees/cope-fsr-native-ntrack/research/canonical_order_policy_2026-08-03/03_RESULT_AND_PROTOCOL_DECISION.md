# X20 result: normalize stable-key record collections before validation and hashing

Date: 2026-08-03 (Asia/Shanghai)

## Decision

Adopt `stable-record-order-v1` for future protocol artifacts:

1. parse state and validate collection/record shape;
2. require string stable keys and reject duplicates;
3. sort `commitments` and `entities` by `id`, and `progress_ledger` by
   `milestone_id`;
4. run semantic validation on normalized stored pre-state and normalized
   candidate;
5. publish and compute receipts/hashes only from the normalized state;
6. record the normalization version in every receipt.

Do not silently reinterpret existing hashes. Migrate them into a new protocol
version with explicit before/after provenance.

## Result

- legacy clean states already satisfying new strict order: 0/12;
- normalized clean states satisfying strict order: 12/12;
- clean semantic/idempotence controls: 12/12;
- strict policy rejects X18 reorder candidates: 14/14;
- normalize policy accepts and canonicalizes them: 14/14;
- normalized candidate/reference bytes and hashes equal: 14/14;
- malformed/duplicate/missing key faults rejected: 7/7;
- aggregate median normalization time: 100,979 ns (about 0.101 ms);
- frozen under-1-ms diagnostic gate: pass;
- independent audit: 11/11;
- focused tests: 4 passed in 0.11 seconds;
- complete repository regression: 436 passed in 50.94 seconds.

No provider, credential, LLM, GPU, simulator, robot, or reserved LIBERO state
27--49 was used.

## Why normalization wins

Strict rejection is deterministic but would reject every current legacy clean
state until migration, even though record-list order has no role in the
decomposed semantics. Boundary normalization removes that accidental output
degree of freedom while preserving fail-closed stable-key checks.

The policy does not reorder plan actions, restoration records, goal atoms,
grounding arguments, or any sequence whose order may encode execution or
logical structure.

## Claim boundary

This resolves the 14 known X18 canonicalization divergences on small synthetic
states. It is not a general performance result. The timing excludes network,
provider, simulator, and storage cost, and stable-key sorting should be profiled
again on larger task graphs.

