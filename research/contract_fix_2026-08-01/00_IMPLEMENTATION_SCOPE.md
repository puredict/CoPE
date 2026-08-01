# Shared semantic gate implementation scope

Date frozen: 2026-08-01 (Asia/Shanghai)

Pre-change parent commit:
`3b7423b274edb7935155d3053ccf9b9adb0cf924`

Frozen audit source:
`research/contract_stress_2026-08-01/02_AUDIT_PROGRAM.txt` from preregistration
commit `2c5266f6064862d1e32ff7f530d08d4af6882392`.

## Authorized implementation slice

1. Add one event-bound canonical-section validator shared by semantic
   replacement and cancellation full-state-v2 states.
2. Bind commitments, task-relevant entities, progress ledger, plan,
   restorations, and evidence versions to the deterministic canonical state for
   the authorized event.
3. Reject replacement events whose pending original goal is already physically
   complete and reject duplicate current-goal atoms.
4. Harden the transitional main `FullStateOutput` parser: pin full-state-v1,
   require nonempty structured commitments and plan, require source/priority/
   lineage, compile execution prose deterministically from structured state,
   and reject a mismatching diagnostic provider prompt.
5. Add focused tests without changing any of the 123 frozen expectations.

## Generalization rule

The implementation may not inspect `case_id` or special-case audit strings.
Semantic full-state checks must compare event-grounded structures, not search
for malicious words. The main v1 compiler may use only versioned constraint and
plan fields; raw provider prose remains diagnostic and must match the compiled
result before it can be retained.

Exact canonical closure is intentionally fail-closed for this version. Future
optional metadata requires a schema-version change and new tests rather than
silent acceptance.

## Evaluation rule

- Keep the original 123-row result immutable.
- Write post-fix results to a new directory.
- Require 123/123 expectation matches, 67/67 atomicity tests, and a clean full
  regression before reassessing the pilot.
- Passing does not by itself authorize simulation. The real provider, non-fake
  predicate validator, shared semantic runner, and formal readiness report are
  separate gates.
- States 25–49 remain untouched.
