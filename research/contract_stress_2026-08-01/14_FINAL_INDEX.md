# Contract-stress audit final index

Date: 2026-08-01 (Asia/Shanghai)

## Outcome

The next CoPE–FSR-PC gate is now executable rather than qualitative:

- 123 frozen semantic corruption/control cases;
- 62 malformed outputs incorrectly accepted;
- 13 grouped acceptance gates, all currently blocking;
- canonical prompt/directive isolation passed 2/2;
- CoPE transactional replay passed 67 tests, including 64 manual
  counterexamples and 10,000 seeded operation sequences;
- full repository regression passed 297/297;
- deterministic audit replay produced a byte-identical result CSV.

Decision: **do not run the two-state oracle pilot yet**. Fix and test the shared
semantic contract first. This protects LIBERO states 25–49 from being consumed
by an experiment whose arms currently receive unequal validation and compilation.

## Evidence map

- `00_PREREGISTRATION.md`: question, 123-case denominator, prior-knowledge
  boundary, frozen conditions, and reserve-state rule.
- `01_CORRUPTION_MANIFEST.csv`: every assigned mutation and normative rationale.
- `02_AUDIT_PROGRAM.txt`: frozen research-only deterministic audit program.
- `03_COMMANDS.txt`: exact manifest, result, atomicity, and regression commands.
- `04_ASSIGNED_RESULTS.csv`: all 123 actual validator/parser decisions.
- `05_AUDIT_STDOUT.txt`: aggregate execution output.
- `06_ATOMICITY_REPLAY.txt`: `67 passed` transactional replay.
- `07_FULL_PYTEST.txt`: `297 passed` full regression.
- `08_ACCEPTANCE_MATRIX.csv`: 13 grouped implementation gates and priorities.
- `09_RESULT.md`: authoritative interpretation and fairness boundary.
- `10_TWO_STATE_ORACLE_PILOT_SPEC.md`: blocked state-25 replacement/state-26
  cancellation smoke-test protocol.
- `11_FAILURE_LEDGER.csv`: exact mapping of 62 failures to G01–G13.
- `12_AUDIT_REPLAY.txt`: deterministic result reproduction.
- `13_SHA256SUMS.txt`: source and evidence hashes.

## Immediate engineering order

1. Introduce one canonical state materialization boundary shared by native
   FSR-PC output and post-CoPE state.
2. Implement P0 gates G01–G05, G09–G11, and G13; add each frozen case as a unit
   test without changing its expected decision.
3. Implement P1 closure/canonicalization gates G06–G08 and G12.
4. Re-run the unchanged 123-case audit; require 123/123 expectation matches.
5. Configure a non-fake predicate validator and verify the formal readiness
   report.
6. Only then run the specified state-25/state-26 oracle pilot.

This audit does not show that CoPE is intrinsically better than FSR-PC. It shows
that the current code would confound representation with validation strength,
and identifies the exact checks needed to remove that confound.
