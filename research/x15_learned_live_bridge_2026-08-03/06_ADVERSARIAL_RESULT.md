# X15 adversarial rejection result

Date: 2026-08-03 (Asia/Shanghai)

## Result

The dedicated adversarial selection passed: **9 passed, 13 deselected in
0.07s**. Nine tests cover the eight required rejection classes because unknown
target and unknown replacement are separate parameterized cases.

| Required class | Evidence | Result |
|---|---|---|
| forged receipt | model-added `receipt` violates exact CoPE fields | PASS |
| stale version | compact transaction with stale `base_version` | PASS |
| unknown target/replacement | two independent stable-ID mutations | PASS (2) |
| unauthorized extra mutation | extra CoPE mutation field | PASS |
| invalid operation | unsupported semantic operation | PASS |
| oracle substitution | fake/oracle provider metadata rejected before calls | PASS |
| silent fallback | provider timeout retained; all three draws attempted once; no fallback | PASS |
| idempotence violation | already processed event ID rejected | PASS |

Additional Phase A test rejects a nonzero action-count delta. Provider-backed
success tests cover both replacement and cancellation across all three arms,
including trusted receipts, predicate outcomes, fairness hashes, and zero action
delta.

Raw test output is retained in `02_ADVERSARIAL_TESTS.txt`.

## Regression

- Baseline before edits: 448 passed in 47.42s.
- Final suite: 462 passed in 47.68s.
- A superseded full-suite attempt exposed an old oracle-pilot import name; its
  log is retained. The caller was changed to the explicit oracle fixture, its
  focused suite passed 5/5, and the final full suite passed.
