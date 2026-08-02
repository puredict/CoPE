# X16 result: named completeness predicates match the oracle on the frozen suite

Date: 2026-08-03 (Asia/Shanghai)

## Bottom line

An eight-group decomposed validator accepted all 48 clean candidates and
rejected all 39 noncanonical candidates that passed their native
parser/materializer. Together with 49 native rejections, the resulting
non-oracle pipeline rejected all 88 faults.

Its accept/reject decision matched the old exact-state oracle validator on all
136 cells. The new validator source contains no reference to
`expected_patch`, `derive_post_state`, or `validate_and_compile`, and no
whole-candidate hash/serialization comparison pattern.

This closes the specific omission gap exposed by X15 on the frozen suite. It
does not prove formal completeness outside the hand-designed cases.

## Main result

| Check | Result |
|---|---:|
| Clean candidates accepted | 48/48 |
| Faults rejected natively | 49/88 |
| Faulty candidates materialized | 39/88 |
| Materialized faulty candidates actually noncanonical | 39/39 |
| Exact oracle validator rejected | 39/39 |
| Decomposed validator rejected | 39/39 |
| Exact/decomposed decision parity | 136/136 |
| Full decomposed pipeline rejected | 88/88 |
| Crashes / caller mutations | 0 / 0 |
| Independent CSV-only audit | 17/17 |
| Focused tests | 8 passed in 0.30 s |
| Complete regression | 425 passed in 47.33 s |

No provider, credential, LLM, GPU, simulator, robot, or reserved LIBERO state
27--49 was used.

## Predicate coverage and one-at-a-time ablation

| Predicate group | Violated by faulty candidates | Unique catches / fail-open if removed alone | Clean false positives |
|---|---:|---:|---:|
| authorization / no-op | 5 | 5 | 0 |
| version / evidence | 24 | 9 | 0 |
| stable identity / lifecycle | 19 | 2 | 0 |
| goal consistency | 17 | 0 | 0 |
| progress preservation | 1 | 1 | 0 |
| action continuity | 20 | 3 | 0 |
| restoration / entity | 14 | 0 | 0 |
| unaffected scope | 2 | 2 | 0 |

The version/evidence group has the largest unique contribution on this suite.
Authorization/no-op, progress, continuity, lifecycle, and unaffected-scope
checks are also individually necessary for at least one candidate.

Goal consistency and restoration/entity have zero unique catches only because
their violations overlap other groups here. This does not justify deleting
them: they detect 17 and 14 faulty candidates respectively, and the sample is
small and correlated.

## What this changes in the CoPE design

The safety architecture can now be stated without relying on an exact full
post-state oracle:

1. the generic typed interpreter blocks illegal or malformed commission edits
   using event binding and local operation preconditions;
2. decomposed event-contract predicates detect missing consequences and
   cross-field inconsistency;
3. publication occurs only when both layers pass.

This is stronger and more realistic than the earlier
`patch == expected_patch` implementation. It also makes rejection explanations
auditable: a failure is assigned to version/evidence, lifecycle, goal,
progress, continuity, restoration/entity, or unaffected scope.

## Claim boundary

Supported:

> On 12 frozen synthetic events and 22 clustered fault assignments, an
> oracle-free typed interpreter plus eight named event-contract predicate groups
> matched the exact validator with no false accepts or false rejects.

Not supported:

- the predicate set is formally complete for arbitrary tasks or states;
- the checks are independent or minimal;
- zero unique catches means a group is unnecessary;
- CoPE is end-to-end safer than compact TX or FSR-PC when all receive the same
  decomposed validator (all complete pipelines rejected the frozen faults);
- this measures learned generation, adversarial robustness, or robot success.

The remaining CoPE-specific evidence is earlier rejection and a smaller
commission-error surface, not unique final safety under an equally strong
validator.

## Required next stress test

Compose two and three faults across predicate boundaries, especially changes
that could cancel each other's local symptoms, and generate near-valid states
that satisfy seven of eight groups. The current single-fault campaign may
overestimate sufficiency because its violations are simple and correlated.

