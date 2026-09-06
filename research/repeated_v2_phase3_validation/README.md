# Window 3 validation artifacts

All transcripts and pilot stop records are qualification evidence. They contain
no learned-policy performance measurements and no formal benchmark outcomes.

## Final candidate

Status: **PASS_WINDOW_3_SOFTWARE_QUALIFICATION**. Production pilots remain
blocked on the dependencies listed below; this status is not a scientific GO.

- `local_v2_tests_final.txt`: **499 passed, 1 optional simulator skip, 58 subtests
  passed** in 47.97 seconds after the final review corrections.
- `remote_full_tests_final.txt`: **1136 passed, 1 optional simulator skip,
  58 subtests passed** in 162.70 seconds: all 637 existing tests and 499 v2 tests.
- `REMOTE_FINAL_SOURCE_VERIFICATION.txt`: all **118** final candidate files
  matched `FINAL_SOURCE_SHA256.txt` on the server before the full regression.
- Final corrections preserve measured provider latency across crash replay,
  retain semantic planning/recovery failures, log raw and converted actions, and
  permit verified empty formal shards without loading runtime/model factories.
- `FINAL_SOURCE_SHA256.txt` binds all **118** files in the final transferred
  candidate. The archive SHA256 is
  `54188f1f342116f1b6ea710c583e668b42cc68011fbf84b24cff11e21439e8a3`.
  Verification transcripts and this evolving report are excluded from that
  candidate. Implementation, tests and included documentation are frozen.

## Local checks

- `local_v2_tests.txt`: first integrated v2 regression, **473 passed, 1 optional
  smoke skipped, 58 subtests passed** in 45.01 seconds.
- `local_libero_smoke.txt`: explicit opt-in real LIBERO CPU test, **1 passed** in
  3.21 seconds. The smoke checks reset, one physics step, exact restore and fresh
  observation; rendering, model inference and GPUs are disabled.

Interpreter: `/Users/lijingsu/miniforge3/envs/lerobot312/bin/python`.

## Server regression

- `remote_full_tests.txt`: the first integrated full repository regression,
  **1110 passed, 1 optional simulator skip, 58 subtests passed** in 161.19 seconds.
  This includes the 637 existing tests and 473 v2 tests.
- `REMOTE_SOURCE_VERIFICATION.txt`: all 117 transferred candidate files passed
  `sha256sum -c SOURCE_SHA256.txt` before that regression.

Final review corrections have separate verification transcripts below; these
initial transcripts and source hashes remain immutable.

## Production pilot attempts

The `pilot_controlled` and `pilot_end_to_end` directories contain immutable
`13_INFRASTRUCTURE_STOP.json` files from CLI attempts on the integrated phase-2
parent `41d15bd2ef8b4bb04194b524f9180d2b17b4fc3b` plus the phase-3 candidate.
The corresponding `*_console.txt` files preserve the command output.

Both attempts report `BLOCKED_TASK_CATALOG_GAPS` with 0 eligible tasks and 794
catalog gaps, zero runtime-factory calls, zero provider/VLA calls, and zero result
rows. End-to-end also reports missing VLA adapter/checkpoint configuration.
No empty or inferred event/episode result records were published.

```sh
python experiments/repeated_interruptions_v2.py --phase pilot \
  --protocol controlled --information-condition evidence_matched \
  --config configs/repeated_interruptions_v2_pilot.yaml \
  --output-dir <new-controlled-attempt-directory>
python experiments/repeated_interruptions_v2.py --phase pilot \
  --protocol end_to_end --information-condition evidence_matched \
  --config configs/repeated_interruptions_v2_pilot.yaml \
  --output-dir <new-vla-attempt-directory>
```

Exit code 2 denotes these blocked attempts. A changed dependency set requires a
new output directory; existing attempts are not overwritten. Process lock files
and empty runtime directories are not included in the committed report artifacts.

## Source correspondence

`SOURCE_SHA256.txt` identifies the 117 files in the first transferred candidate:
phase-1/phase-2 additions over frozen base `84e1e742579899adb67efee92cef16efca063b31`,
plus phase-3 implementation, tests and then-existing documentation. Validation
transcripts and process lock files were excluded from the transfer. Later final
candidate checks, if present, have separate filenames and preserve this record.

Remote CPU checks use `/home/lijingsu/vla/.venv/bin/python` and isolated worktree
`/home/lijingsu/codex-worktrees/cope-repeated-v2-phase3-20260906`, accessed through
the existing `fudan-26575` alias. `CUDA_VISIBLE_DEVICES` is empty. Other worktrees,
model weights, GPU allocations and user processes are unchanged.

See [the verification report](../../docs/repeated_v2/PHASE3_VERIFICATION.md) for
implementation scope, explicit production blockers and limits on conclusions.
