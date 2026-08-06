# Assigned v2 self-audit and downgrade

Date: 2026-08-02 (Asia/Shanghai)

The assigned v2 directory reported 12/12 clean equivalence, 8/8 fail-closed
faults, 12/12 deterministic semantic replay, and source independence. The raw
outputs are retained unchanged.

Post-result inspection found that fault F08 did not exercise the intended
external-validator exception path. `execute_transaction` special-cased F08 and
raised internally immediately before invoking the supplied validator callback;
the raw receipt correctly recorded `validator_calls=0`.

Consequences:

- the 12 clean cases remain valid;
- F01--F07 remain valid rollback tests;
- F08 proves rollback for an internal pre-validation exception, not for a
  validator callback exception;
- the v2 claim of 8/8 coverage of the frozen fault mechanisms is downgraded to
  7/8 plus one adjacent rollback control;
- v2 is not the final authoritative strong-falsifier result.

Corrective action frozen before v3:

1. remove the F08 exception special case from the transaction engine;
2. pass a validator callback that raises `RuntimeError` only for F08;
3. require the rejected receipt to record `validator_calls=1`;
4. retain every case, threshold, other fault injection, timing protocol, and
   output schema;
5. rerun into a new directory without overwriting v2.

No GPU, LLM, robot, simulator, or reserved LIBERO state was used in v2 or this
audit.
