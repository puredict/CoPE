# X14 result: CoPE's observed safety advantage is not typing-specific

Date: 2026-08-03 (Asia/Shanghai)

## Bottom line

The implemented CoPE path rejected all 16 injected faults before producing a
candidate state, while compact TX produced 7/16 noncanonical candidates and
FSR-PC produced 12/16. All of those baseline candidates were then rejected by
the shared event-bound validator, so the complete three pipelines had zero
fail-open events.

However, CoPE's pre-validator advantage came from
`materialize_patch == expected_patch`, an exact event-specific canonical-output
comparison. When the same canonical-proposal guard was applied as a control to
compact TX and FSR-PC, all three arms rejected 16/16. Therefore the
preregistered typing-specificity gate failed.

The safe interpretation is:

> In this synthetic implementation, CoPE places an oracle-equivalent guard
> earlier in the pipeline. The experiment does not show that typed patch syntax
> itself provides a unique safety advantage.

## Audited results

| Measure (16 faults per arm) | CoPE | Compact TX | FSR-PC |
|---|---:|---:|---:|
| Schema-parser rejection | 4 | 8 | 4 |
| Native representation-guard rejection | 12 | 1 | 0 |
| Reached and rejected by common validator | 0 | 7 | 12 |
| Noncanonical candidate before common validator | 0 | 7 | 12 |
| End-to-end fail-open | 0 | 0 | 0 |
| Parser or matched canonical guard rejects | 16 | 16 | 16 |
| Caller-state mutation | 0 | 0 | 0 |
| Uncaught crash | 0 | 0 | 0 |

Additional controls:

- canonical clean cells: 36/36 passed;
- noncanonical mutations: 48/48 differed from their frozen canonical output;
- faulty cells satisfying the frozen fail-closed checks: 48/48;
- independent CSV-only audit: 17/17 checks passed;
- focused tests: 3 passed in 0.20 seconds;
- complete repository regression: 409 passed in 47.44 seconds.

No provider, LLM, credential, GPU, simulator, robot, or reserved LIBERO state
27--49 was used.

## Where the baseline candidates got through

Compact TX materialized noncanonical states for seven semantic intents:

- unauthorized cancellation;
- duplicate-event reapplication;
- illegal action continuity;
- unobserved replacement grounding;
- omitted required evidence/version transition;
- double state-version advance;
- unrelated sibling corruption.

Its parser/materializer blocked the four structural faults plus stale binding,
wrong event binding, forbidden progress path, duplicate path, and unknown stable
record. FSR-PC's full-state parser blocked only the four structural faults; the
shared validator had to catch every semantic mutation.

These are useful defense-in-depth differences, but no bad state was published
because the common validator performs exact event-bound state comparison.

## Why this weakens the typed-assurance claim

`parse_patch` itself rejected only the same four top-level structural faults as
FSR-PC. The other 12 CoPE faults were caught because `materialize_patch`
compared the entire proposal to a deterministically computed
`expected_patch`. This is stronger than a generic typed-operation interpreter:
it already knows the exact correct answer for the event.

Consequently:

1. the current result cannot separate type safety from oracle availability;
2. a baseline given the same exact-output guard becomes equally fail-closed;
3. if `expected_patch` is always computable, the learned patch generator may be
   redundant for these cases;
4. zero fail-open under an exact post-state validator is a unit-level safety
   result, not evidence of recovery competence.

## Claim decision

- Pipeline safety gate: **PASS** (0/48 end-to-end fail-open).
- Native typed-assurance gate: **PASS descriptively** (0 vs 7 vs 12
  pre-validator noncanonical candidates).
- Typing-specificity gate: **FAIL** (matched guard equalizes all arms).

Allowed claim:

> CoPE's current event-bound canonical guard rejects faulty patches earlier than
> the generic baselines' native guards on this 16-intent synthetic suite.

Not allowed:

- typed patches are intrinsically or uniquely safe;
- CoPE is safer end to end than compact TX or FSR-PC here;
- the fault suite measures learned-generation robustness or robot success;
- a hand-constructed 16-intent suite is a security certificate.

## Required next experiment

Replace the exact `expected_patch` equality check with a generic typed-operation
interpreter that checks authority, versions, stable IDs, lifecycle preconditions,
and operation-local invariants without knowing the full correct patch. Repeat
the same mutations and add omission/extra-operation cases. That experiment can
test whether typed operations retain a real assurance advantage when the oracle
confound is removed.

