# Window 2 qualification evidence

All records here are CPU implementation qualification, not formal model or robot
results. No external provider or VLA calls were made by the oracle-fixture smoke.

- `local_v2_tests.txt`: 328 combined v2 tests passed.
- `local_full_tests.txt`: 964 passed; the known frozen Linux BDDL asset check
  fails on macOS. The baseline exhibits the same environmental failure.
- `remote_full_tests.txt`: all 965 tests passed on `fudan-26575`.
- `TRANSFER_PATHS.txt`, `SOURCE_SHA256.txt`, `REMOTE_SOURCE_VERIFICATION.txt`:
  correspondence of all 24 new executable/test/schema source files with the
  isolated server regression worktree. The remaining source is the exact
  phase-1 parent commit `b8462c28424d6551ab1713e67d68f42ca149b55f`.
- `oracle_fixture_smoke/RESULT.txt`: diagnostic smoke metadata.
- `oracle_fixture_smoke/SUMMARY.csv`, `EVENT_CELLS.txt`: 72 distinct event cells.
- `oracle_fixture_smoke/EXACT_PROMPT_LOGS.txt`: all 56 exact fixture requests and
  responses, frozen configurations, and explicitly labeled byte-unit accounting.

The fixture answers are hand-authored diagnostic responses. The eight oracle
upper-bound cells are privileged; all other smoke adapters receive public inputs.
No statistical or learned-policy success claim follows from these fixtures.

See [the verification report](../../docs/repeated_v2/PHASE2_VERIFICATION.md)
for scope, interfaces, and reproduction commands.
