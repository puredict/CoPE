# Occurrence learned-formal oracle-confound audit

Date: 2026-08-04

## Decision

**No X14-style CoPE-only oracle guard found; PASS with a narrow
interpretation.** The learned runner never uses an oracle to generate a model
proposal. Oracle constructors are used in the credential-free preflight and
the analyzer's canonical reference, not as hidden provider assistance.

## Why this is not the earlier X14 confound

X14 gave CoPE an exact expected-patch check while weaker native baseline
guards allowed more faulty candidates through. Here all five arms have a
frozen native output contract and are judged against the same canonical
post-event transition:

- CoPE: exact fields, event/target/replacement identity, base version,
  operation type, fresh nonempty patch/operation identity through the typed
  patch engine, then canonical transition validation;
- neutral: exact minimum canonical write set, transactional staging, then the
  same canonical transition validation;
- governed: exact changed occurrence scope, complete affected records and
  blackboard delta, then canonical transition validation;
- FSR-PC: exact complete semantic-state fields, then canonical transition
  validation;
- full replan: exact occurrence-aware remaining-plan record, then canonical
  transition validation.

CoPE's materializer derives the logical candidate from a validated typed
operation and the common event, whereas state/delta arms materialize their
returned content. That is the representation being tested, not extra hidden
input: all arms receive the byte-identical pre-state, event, rules, and
physical-progress fact.

## New strictness tests

The focused suite now confirms that:

- a CoPE extra field is rejected;
- reuse of a historical CoPE patch ID is rejected;
- an FSR-PC extra field is rejected;
- a full-replan extra field is rejected;
- existing tests continue to reject a neutral redundant no-op write and a
  governed overbroad affected scope.

Focused result: 3 tests passed, covering the five native contracts and
negative variants. Provider calls and simulator reads were zero.

## Interpretation ceiling

This design measures **first-pass exact contract conformance**, not generic
semantic acceptability. A semantically equivalent but nonminimum neutral write
set or overbroad governed scope counts as failure because the corresponding
contract explicitly forbids it. Likewise, exact canonical validation is a
benchmark oracle and must not be presented as a deployable safety mechanism.

Therefore a CoPE win would support a narrower claim:

> Under matched common inputs and strict arm-native contracts, the model more
> often emits the canonical occurrence-sensitive CoPE operation and does so
> with better locality than both primary sparse controls.

It would not prove that CoPE is uniquely safe, that assurance is unnecessary,
or that all semantically acceptable baseline outputs are invalid.
