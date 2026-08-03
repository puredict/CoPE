# Shared commit-envelope attribution experiment preregistration

Date: 2026-08-03 (Asia/Shanghai)

## Hypothesis

After deterministic transaction bookkeeping is assigned to the same trusted
commit envelope for every arm, does a typed CoPE semantic delta remain easier
to generate correctly than an equivalently sparse generic delta and a complete
semantic state?

This preserves the fixed core hypothesis—recover by editing persistent task
commitments rather than replanning the task—while removing an attribution
confound.

## Shared trusted envelope

No learned arm outputs:

- `state_version` increments;
- `evidence_version` updates;
- processed-event records;
- event payload hashes;
- receipts, before/after hashes, or audit history.

After a proposal passes semantic validation, one shared trusted envelope binds
the event, increments versions exactly once, computes the canonical event hash,
appends the processed-event record, and emits the receipt. The same code and
validator are used for every arm.

## Arms

1. **CoPE-semantic:** typed commitment/action/progress/restoration/fact edits,
   without `CommitEvent`.
2. **Neutral-typed:** identical typed fields and executor with permuted neutral
   operation labels.
3. **Compact-semantic:** generic stable-ID path/value writes restricted to
   semantic state roots, without transaction-metadata paths.
4. **FSR-semantic:** complete semantic state excluding system-managed
   transaction metadata.

All arms receive the same explicit rule-clause packet. Every oracle delta atom
must cite a visible rule-clause ID. Output schemas are exact and strict. No arm
receives the oracle, expected delta, or case family label.

## Development gate

First construct at least six new APPLY development cases covering six distinct
families. They are permanently excluded from confirmation. Each arm's oracle
must materialize to the same post-state after the shared envelope.

Provider qualification requires:

- at least 4/6 correct for CoPE-semantic, neutral-typed and compact-semantic;
- no parser failures under strict schemas;
- zero accepted safety violation;
- zero repair, retry, fallback or oracle substitution;
- all expected delta atoms supported by provider-visible clause IDs.

If the sparse arms lack this ceiling, stop and qualify a stronger model or
improve the common rule packet. Do not generate a confirmatory holdout.

## Confirmatory boundary

Only after the development gate passes may a newly frozen independent holdout
be created. It cannot reuse X14, X15, X16 or X17 development tasks. The primary
paired tests and multiplicity correction must be frozen before provider calls.

This experiment is synthetic and uses no simulator or reserved state. States
27--49 remain locked; states 47--49 remain permanent reserve.
