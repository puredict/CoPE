# Semantic materialization evidence index

Date: 2026-08-02 (Asia/Shanghai)

## Decision-bearing artifacts

- `00_PREREGISTRATION.md`: frozen question, four cases, invariants, and decision rule.
- `01_PREFLIGHT_CASES.csv`: exact CPU assignments.
- `manifests/semantic_oracle_pilot_v1.csv`: uninspected state-25/state-26 reservation; not a formal atlas.
- `11_INDEPENDENT_ASSIGNED_RESULTS.csv`: authoritative 4/4 result after removing shared-builder circularity.
- `12_INDEPENDENT_PREFLIGHT_STDOUT.txt`: authoritative first-run summary.
- `13_INDEPENDENT_REPLAY_RESULTS.csv`: deterministic replay.
- `14_INDEPENDENT_REPLAY_STDOUT.txt`: byte-equality verdict.
- `15_INDEPENDENT_CONTRACT_REPLAY.csv` and `16_INDEPENDENT_CONTRACT_STDOUT.txt`: unchanged 123-case audit.
- `17_INDEPENDENT_ATOMICITY_STDOUT.txt`: 67-test atomicity/property replay.
- `18_INDEPENDENT_FULL_REGRESSION_STDOUT.txt`: 326-test repository regression.
- `19_RESULT.md`: scope-aware interpretation and next experiment.
- `20_X_GATE_STATUS.csv`: X01--X08 gate delta.

## Retained but superseded artifacts

`03_ASSIGNED_RESULTS.csv` through `10_REPLAY_STDOUT.txt` record the initial
wiring implementation. They are retained because deleting an inconvenient
result would break the audit trail. They are not authoritative for X07 because
that materializer reused the native builder.

## Claim boundary

This package closes a CPU semantic materialization contract only. It contains
zero embodied rollouts, zero learned-provider calls, zero GPU execution, and
zero new task-success observations. Reserved states 25--49 were not inspected.
