# Formal analyzer anti-overclaim hardening

Date: 2026-08-04 (Asia/Shanghai)

## Audit result

The locked two-event analyzer already used the correct independent unit and
comparison hierarchy:

- one full two-event sequence is one paired unit;
- CoPE versus neutral patch is primary;
- CoPE versus FSR-PC and full replan are Holm-adjusted secondary tests;
- exact manifest shape, common-input hashes, shared prefix hashes, zero retry
  and dependency skips are fail-closed;
- a one-task decisive gate is necessary but not sufficient.

The retained one-event materializer also hard-codes
`confirmatory_valid=false`.  No arithmetic or pairing bug was found.

## Hardening change

`tools/analyze_sequential_formal.py` now emits:

- `primary_comparison=true`;
- `secondary_cannot_rescue_primary=true`;
- `task_identity_count` from the frozen manifest;
- a categorical `formal_claim_status`.

The categorical state distinguishes incomplete substrate, primary
CoPE-neutral failure, locality failure, a necessary-gate pass on only one task,
and a multi-task necessary-gate pass that still requires external-validity
review.  Secondary p-values are deliberately absent from this decision
function.

## Verification

Focused regression: 6/6 tests passed in the isolated CPU environment.  New
tests prove that a primary tie returns
`NO_GO_PRIMARY_NEUTRAL_COMPARISON`, regardless of any secondary result, and
that a successful one-task synthetic table returns only
`NECESSARY_GATE_PASS_SINGLE_TASK_ONLY`.

