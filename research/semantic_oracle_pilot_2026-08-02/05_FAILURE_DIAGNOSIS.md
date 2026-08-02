# X09 assigned pilot failure diagnosis

Date: 2026-08-02 (Asia/Shanghai)

Decision: **assigned pilot NO-GO (0/4 arms, 0/2 pairs).**

The failure is retained in `03_ASSIGNED_RESULTS.csv` and
`04_PAIR_AUDIT.csv`.  Both states 25 and 26 are now consumed and cannot be
presented as fresh pilot evidence after a repair.

## Observed failure

Every arm independently completed its physical Oracle prefix far enough to
enter the semantic call, then raised:

`ValueError: reserved or unregistered state access rejected`

No post-event replacement or cancellation policy behavior was executed.

## Root cause

X09 correctly verified its narrow authorization for states 25/26, but then
called `cope.semantic_live_runner.run_semantic_wiring`, whose X04 safety lock
was still hard-coded to development states 0--4.  The authorization was not
passed across that API boundary.  This is an integration design defect, not a
physical controller failure and not evidence against the commitment-editing
hypothesis.

The pair-audit CSV also misleadingly reports some equality fields as `True`:
the original auditor treated two missing strings as equal.  Because
`both_arms_passed=False`, the final pair decision remained false, but the
field-level reporting must be corrected.

## Corrective action and claim boundary

The correction will:

1. add an explicit caller-supplied authorized-state set to the reusable
   semantic function while preserving states0--4 as its default;
2. make the X09 caller pass exactly `{25, 26}` only after sidecar verification;
3. require non-empty evidence before any pair-equality field can pass;
4. retain partial episode evidence on exceptions;
5. run tests proving the default X04 lock is unchanged.

Any corrected execution on states25/26 is a **consumed-state debug replay**.
It may diagnose whether the execution substrate works, but it cannot convert
this assigned pilot into a pass or authorize a learned-provider pilot.

States 27--49 remain untouched and locked.
