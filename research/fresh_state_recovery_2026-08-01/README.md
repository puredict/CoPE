# Fresh-state recovery evidence index

## First preregistered run: max-move-steps 40, states 5–14

Authoritative files:

- `00_PREREGISTRATION.md`: frozen protocol, committed before outcomes at
  `e4e923e22880f079a343c1ad450f0e8158b1e819`.
- `01_COMMANDS.txt`: exact run command record.
- `02_ASSIGNED_EPISODES_v2.csv`: 30-row assigned-denominator ledger,
  including the three state-5 substrate failures.
- `03_RESULT_v2_PROTOCOL_CORRECTED.md`: authoritative result and decision.
- `05_FSR_PC_READINESS_AUDIT.md`: formal CoPE–FSR-PC blockers.
- `09_STATE5_AND_REPORT_CORRECTION_AUDIT.md`: state-5 cause, invalid
  diagnostic disclosure, and decision-rule correction.
- `raw_v1_preregistered/`: 27 raw CSV rows and 30 per-assignment TXT logs.
- `10_SHA256SUMS_FIRST_RUN.txt`: integrity manifest.

The assigned result is inconclusive because only 9/10 states provide complete
matched prefixes. Conditional on reaching the event, exact and local both
reach the physical updated goal in 9/9 pairs and local is faster in 9/9.

## Superseded or invalid files retained

- `03_RESULT.md` is superseded because it incorrectly treated the C1 validity
  failure as method rejection.
- `02_ASSIGNED_EPISODES.csv` is the corresponding preliminary ledger; v2 is
  authoritative.
- `04_STATE5_DIAGNOSTIC.txt` and
  `06_STATE5_CONTROLLER_MAX60_DIAGNOSTIC.txt` used the wrong target symbol and
  are invalid for diagnosing the formal run.
- `07_STATE5_CORRECT_TARGET_MAX40.txt` and
  `08_STATE5_CORRECT_TARGET_MAX60.txt` are their authoritative replacements.

No first-run assignment was overwritten or silently retried. States 5–14 are
consumed and cannot be reused as fresh data for a modified rule.
