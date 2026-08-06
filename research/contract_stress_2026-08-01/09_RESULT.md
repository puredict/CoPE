# Shared semantic corruption and atomicity audit result

Date: 2026-08-01 (Asia/Shanghai)

Preregistration commit:
`2c5266f6064862d1e32ff7f530d08d4af6882392`

## Decision

**NO-GO for the two-state oracle pilot and for formal CoPE–FSR-PC.**

All 123 frozen cases were emitted exactly once, but 62 malformed outputs were
accepted contrary to the preregistered contract. The failures are validation
coverage failures, not simulator or policy failures. No LIBERO state, provider,
GPU, or robot was used in this audit.

| Surface | Assigned | Expected-valid controls | Malformed assigned | Malformed accepted | Malformed rejection coverage |
|---|---:|---:|---:|---:|---:|
| Replacement full-state-v2 | 61 | 2/2 pass | 59 | 32 | 27/59 (45.8%) |
| Cancellation full-state-v2 | 50 | 2/2 pass | 48 | 23 | 25/48 (52.1%) |
| Main `FullStateOutput` parser | 12 | 1/1 pass | 11 | 7 | 4/11 (36.4%) |
| **Total** | **123** | **5/5 pass** | **118** | **62** | **56/118 (47.5%)** |

The previously known seven replacement gaps all reproduced. Therefore the
earlier 16-case result was not a logging accident. The expanded corpus exposed
additional holes in authority/provenance, physical-event consistency, complete
plan semantics, entity closure, duplicate-goal canonicalization, unauthorized
restorations, and the separate cancellation validator.

## What passed

- Schema, state revision, event issuer/authority/target, commitment count and
  identity, lifecycle, replacement lineage, and current-goal set checks rejected
  their covered corruptions in the canonical replacement validator.
- Cancellation correctly rejected stale versions, unauthorized events, wrong
  targets, false completed progress at the physical predicate input, invalid
  lifecycle, nonempty plans, and non-HALT directives.
- Both canonical diagnostic-prompt controls passed isolation: changing provider
  prose did not change the compiled replacement prompt or cancellation HALT.
- The CoPE transactional engine replay passed 67 tests, comprising two explicit
  atomicity tests, 64 manual counterexamples, and one test that executes 10,000
  seeded operation sequences. Rejected patches retained identical state and
  hashes under the frozen tests.

These successes are useful but do not offset accepted semantic corruptions. A
single stale executable plan or fabricated progress record can invalidate a
long-horizon recovery comparison.

## Failure structure

The 62 failures collapse into 13 acceptance gates in
`08_ACCEPTANCE_MATRIX.csv`:

- **P0 execution-integrity failures:** authority/provenance (8), an already
  completed pending goal (1), progress ledger (12), evidence binding (12), plan
  continuity (9), restoration injection (2), schema/nonempty-state checks (2),
  and direct provider prompt control in the main FSR path (1).
- **P1 canonical-integrity failures:** entity closure (9), commitment grounding
  (4), duplicate current-goal atoms (1), and main-state lineage (1).

P0/P1 is a post-hoc engineering priority, not a change to the frozen scoring:
all 13 gates block the pilot. P0 means the accepted corruption can directly
alter what is executed or what progress/evidence is trusted. P1 means the state
is non-canonical or incomplete and can break continuity or later updates.

## Fairness implication

The result must **not** be written as “CoPE is more robust than FSR-PC.” The two
surfaces currently receive unequal semantic enforcement:

- CoPE's typed engine has strong transactional rollback and identity rules.
- The canonical full-state validators check only selected fields.
- The main FSR method uses an even weaker `FullStateOutput` parser and directly
  executes provider-supplied `controller_prompt`.

Running a comparison now would confound representation with validator strength
and compiler privilege. The fair fix is one shared semantic state contract:
validate a native full rewrite and the materialized post-CoPE state with the
same checks, then compile both through the same deterministic compiler.

## Frozen-condition outcome

| Condition | Result |
|---|---|
| C1: 123 unique assigned rows | PASS |
| C2: canonical replacement/cancellation expectations | FAIL |
| C3: canonical prompt/directive isolation | PASS |
| C4: malformed main-parser cases rejected or path replaced | FAIL |
| C5: frozen CoPE atomicity suites | PASS (`67 passed`) |
| C6: full repository regression | PASS (`297 passed`) |

The next permitted action is implementation and unit-testing of the 13 shared
acceptance gates. States 25–49 remain untouched.
