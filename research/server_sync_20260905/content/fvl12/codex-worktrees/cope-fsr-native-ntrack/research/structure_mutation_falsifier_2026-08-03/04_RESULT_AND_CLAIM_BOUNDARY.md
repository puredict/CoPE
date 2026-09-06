# X18 result: structure-agnostic falsification found and repaired four blind spots

Date: 2026-08-03 (Asia/Shanghai)

## Bottom line

A complete JSON-tree mutation pass generated 2,352 unique one-edit candidates
across 12 canonical states. The preregistered v1 validator failed: it accepted
four candidates that added an unknown field to an event-affected commitment
record.

The failed run was preserved. A diagnosis was written before correction, and a
single schema check was added: every commitment record must have exactly the
frozen commitment fields. Replaying the identical 2,352 candidate hashes in v2
eliminated all four dangerous blind spots.

V2 still accepted 14 record-list reversals that the exact canonical validator
rejects. These match the frozen order-only classification and are reported, not
hidden.

## V1 and V2

| Measure | V1 | V2 |
|---|---:|---:|
| Clean states accepted | 12/12 | 12/12 |
| Retained changed candidates | 2,352 | 2,352 |
| Exact validator rejected | 2,352 | 2,352 |
| Decomposed validator rejected | 2,334 | 2,338 |
| Order-only divergences | 14 | 14 |
| Dangerous blind spots | **4** | **0** |
| Validator crashes | 0 | 0 |
| Decision | **FAIL** | **PASS** |

The independent audit verified v1/v2 identity for every case, mutation ID,
traversal index, operator, path, argument, candidate hash, and canonical hash.

## The four v1 failures

All used `add_unknown_field` at `/commitments/1`:

- `replace_pending_target`;
- `continuity_invalid`;
- `cancel_sibling`;
- `activate_override`.

The validator checked each known field of an affected target while allowing its
licensed lifecycle change, but it did not reject an extra field. Unaffected
records and newly constructed records already had exact record checks, so the
gap appeared only on affected pre-existing targets.

The v2 correction adds a commitment-record field-set check under
`identity_lifecycle`. No mutation rule, allowlist, case, candidate, or outcome
classification changed.

## The 14 retained order divergences

They are all `reverse_list` at the preregistered top-level paths:

- `/entities` for eight authorized non-no-op cases;
- `/commitments` for six of those cases.

They preserve the element multiset, so the decomposed semantic checks treat
them as equivalent. The exact validator rejects them because canonical JSON and
receipt hashes are order-sensitive. This is not a dangerous state-semantic
blind spot under the frozen classification, but it is an engineering mismatch:
the implementation must either sort these record collections before hashing or
explicitly enforce canonical ordering.

## Mutation coverage

The retained corpus includes:

- 757 field deletions;
- 150 unknown-field insertions;
- 243 list-item drops;
- 243 list-item duplications;
- 250 scalar appends to lists;
- 97 list reversals;
- 36 boolean, 65 integer, 9 null, and 502 string mutations.

`mutate_float` had zero applicable paths because the frozen states contain no
floating-point values. This is applicability, not a pass for that operator.

## Verification

- focused post-repair suites: 15 passed in 4.04 seconds;
- complete repository regression: 432 passed in 51.25 seconds;
- independent v1/v2 CSV-only audit: 14/14 checks passed;
- no provider, credential, LLM, GPU, simulator, robot, or reserved LIBERO state
  27--49 was used.

## Claim boundary

Supported:

> A structure-agnostic one-edit traversal exposed a real schema-validation gap;
> a minimal, pre-documented correction removed it on an identical 2,352-candidate
> replay with no clean false rejection or crash.

Not supported:

- zero dangerous blind spots under this grammar proves validator completeness;
- list order is harmless for canonical receipts or replay hashes;
- the repaired validator handles multi-edit cancellation attacks;
- mutation counts represent learned-provider or robot failure rates.

This experiment is stronger evidence than the earlier hand-aligned fault suites
because it produced a falsifying result before repair. It should be reported as
such rather than presenting only v2.

