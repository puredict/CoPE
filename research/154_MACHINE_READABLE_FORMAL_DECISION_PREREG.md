# Machine-readable formal decision amendment

Date: 2026-08-04
Status: frozen before live formal outcomes

## Purpose

Prevent orchestration code from confusing analyzer process success (exit code
0) with scientific gate success. Existing exit-code behavior is retained for
compatibility; downstream launch decisions must read `04_DECISION.txt`.

## Occurrence fields

- schema and result-cell count;
- infrastructure validity;
- neutral and governed gates;
- joint primary gate;
- exact claim status;
- `secondary_can_rescue=false`.

## Embodied-v2 fields

The same fields are emitted, plus substrate completeness. The joint gate is
true only when substrate and infrastructure are valid and both primary gates
pass. A true joint gate may still carry
`NECESSARY_GATE_PASS_SINGLE_TASK_ONLY`; it is not a generality claim.

## Rule

No pipeline may branch on analyzer exit code alone. It must require the exact
preregistered occurrence claim status before launching embodied v2, and must
never let a secondary control override a false primary gate.
