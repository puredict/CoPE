# Controller substrate qualification final index

Date: 2026-08-02

Branch: `codex/oracle-substrate-qualification`

Preregistration commit: `b5e9bd6ea89bf7991bd1a070143126d8834a5063`

Harness commit: `c12555380dddcac6e9529233007c5b32d3313a18`

## Decision

PASS for the privileged `oracle/mechanism` stratum on basket-compatible
explicit-goal skills. FAIL/not qualified for the `learned/main` stratum.

Passing does not authorize state 25 or any reserved-state execution.

## Artifacts

- `00_PREREGISTRATION.md`: frozen 75-episode matrix and pass gates.
- `01_CONTROLLER_PRIVILEGE_CARD.md`: privilege, geometry, and access boundary.
- `02_QUALIFICATION_MANIFEST.csv`: assigned states/arms and frozen parameters.
- `03_GPU_PREFLIGHT.txt`: pre-run GPU inventory; experiments used CPU only.
- `04_RUN_LOG.txt`: assigned-run progress and final raw/exit counts.
- `assigned_v1/execution_ledger.csv`: case command outcomes.
- `assigned_v1/raw/q000.csv` through `q074.csv`: one raw episode per assignment.
- `05_EPISODES.csv`: normalized 75-row episode table.
- `06_PREFIX_PROVENANCE_AUDIT.csv`: 35 paired-group audits.
- `07_FAILURE_TAXONOMY.csv`: assigned-denominator failure counts.
- `08_RESULT.md`: final decision and exact behavioral results.
- `09_FULL_REGRESSION.txt`: repository regression output.
- `09_FULL_REGRESSION_EXIT.txt`: regression exit status.
- `10_SHA256SUMS.txt`: checksums for every artifact except the checksum file itself.

## Verification summary

- 75/75 raw episodes present; 75/75 runner exit zero.
- 35/35 paired prefix/provenance groups pass.
- 0/75 method-independent pre-event failures.
- 0 reserved state indices selected; selected indices are exactly 0--4.
- 0 learned-policy/provider calls and 0 GPU execution/inference.
- 341 repository tests pass.
