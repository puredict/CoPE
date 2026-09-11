# Fixed-template editor diagnostic

The hand-written `fixed_event_template_editor` is a separate zero-provider diagnostic and is not one of the eight registered non-oracle methods. It receives the same public event evidence and applies accepted operations through the same atomic typed-state kernel, but its event interpretation is a fixed lexical lookup table.

The focused test suite passed 8 tests in 0.13 seconds. It established these mechanism-level properties:

- the same visible symptom can select `SUSPEND` or `EXPIRE` when an explicit public user cancellation is present;
- three distinct public temporary-interference descriptions select the same `SUSPEND` transition;
- removing the matching temporary-interference rule causes a held-out visible realization to fail closed and preserves the ledger;
- restore requires fresh evidence bound to the stored public guard;
- replacement, cancellation, and reissue operate on public commitment records and allocate a fresh occurrence;
- canonical hidden event-family labels are rejected;
- snapshot/restore is byte-stable through JSON serialization;
- provider and output-token counts are zero.

This is evidence about the fixed lookup mechanism and its brittleness. It is not learned-reasoner performance, end-to-end recovery evidence, or a paper comparator result.

Command:

```text
/Users/lijingsu/Documents/cope_repeated_v2_phase4_worktree/.venv/bin/pytest -q tests/repeated_v2/test_fixed_template_diagnostic_v2_1.py
```

Result: `8 passed in 0.13s`.
