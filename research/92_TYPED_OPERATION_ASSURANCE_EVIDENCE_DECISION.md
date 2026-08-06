# Typed-operation versus assurance-layer evidence decision

Date: 2026-08-04 (Asia/Shanghai)

## Decision

Do not run another synonymous typed-versus-generic offline fault suite. The
repository already contains a chained, independently audited sequence of
experiments that isolates the question more strongly than the proposed new
ablation:

1. X14 showed an apparent native CoPE advantage, then demonstrated that it was
   caused by an exact event-specific expected-output guard rather than typing.
2. X15 removed that oracle-equivalent guard. A generic typed interpreter
   blocked all 14 commission/structural faults, compared with 5 fail-opens for
   compact TX and 10 for FSR-PC, but all three non-oracle arms failed open on
   all eight omission probes before common validation.
3. X16 replaced full expected-state equality with eight named decomposed
   contract predicate groups and matched the exact validator on 136/136 frozen
   cells.
4. X17 composed one to three predicate-level faults: 64/64 were rejected with
   exact attribution, and every predicate group had an isolated ablation
   witness.

These results answer the offline architectural question. Duplicating them
would spend time without increasing evidence independence.

## Quantitative evidence ledger

| Experiment | Key comparison | Result | Inference |
|---|---|---|---|
| X14 | native CoPE / compact TX / FSR-PC | representation fail-open 0/16, 7/16, 12/16; complete pipelines 0/48 | apparent advantage is pre-validator only |
| X14 matched guard | all arms receive exact canonical proposal guard | 16/16 faults rejected by every arm | typing-specificity gate fails |
| X15 generic interpreter | commission/structural faults | CoPE-generic 0/14, compact TX 5/14, FSR-PC 10/14 pre-validator fail-open | typed local operations reduce commission surface |
| X15 omission | partial/whole omissions | 8/8 pre-validator fail-open for all non-oracle arms | syntax cannot establish completeness |
| X16 decomposed assurance | clean/faulty materialized candidates | 48/48 clean accepted; 39/39 faulty rejected; 136/136 parity | named assurance checks replace exact state equality on the frozen set |
| X17 composition | order-1 to order-3 mutations | 64/64 rejected and exactly attributed; 8/8 singleton ablations fail open | all eight groups have a demonstrated local role |

All four campaigns are deterministic, synthetic, provider-free, and
simulator-free. Their independent CSV audits passed. They do not measure
learned generation frequencies or robot recovery.

## Frozen architecture consequence

The deployable CoPE claim is two-layered:

1. **Typed operation layer:** event binding, authority, stable full-commitment
   identity, lifecycle preconditions, atomic local effects, and replay/version
   checks reject illegal commission edits early.
2. **Assurance layer:** decomposed contract predicates check required lifecycle
   effects, version/evidence updates, goal consistency, preserved progress,
   action continuity, restoration/entity integrity, and unaffected scope. This
   layer is mandatory because valid-looking typed output may omit required
   work.

Receipts, before/after hashes, and journal replay are audit/publication
mechanisms. They do not by themselves prove semantic completeness and must not
be conflated with the eight validator groups.

## What remains experimentally unresolved

The decisive unresolved question is not offline fail-closed behavior. It is
whether, under matched information and calls, a learned model produces valid
two-event outputs more often or more cheaply with:

- the generic typed CoPE proposal;
- compact generic JSON transaction;
- FSR-PC complete semantic state;
- full remaining-task replan.

The exact/oracle CoPE materializer must remain an explicitly labeled upper
bound, never the primary learned arm. All learned arms must share the same
decomposed assurance layer after their representation-specific materializer;
otherwise the experiment confounds proposal language with validation strength.

Task 6 is useful for a different unresolved dimension: external validity of
full-atom identity and same-object target replacement under `on`, rather than
another replay of the existing basket/object-only fault suite.

## Paper claim boundary

Allowed:

> Typed commitment operations reduce the tested commission-error surface,
> while independent decomposed contract checks remain necessary for omissions.

Not allowed:

- typed patches are intrinsically complete or uniquely end-to-end safe;
- receipt/hash machinery substitutes for semantic validation;
- synthetic zero fail-open predicts learned or embodied success;
- CoPE beats generic transactions until the matched learned formal experiment
  actually runs.

