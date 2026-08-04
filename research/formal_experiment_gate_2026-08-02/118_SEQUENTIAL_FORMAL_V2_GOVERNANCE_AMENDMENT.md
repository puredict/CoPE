# Sequential formal v2 governance-collision amendment

Date frozen: 2026-08-04 (Asia/Shanghai)

## Why an amendment is required

The four-arm v1 design was frozen before the full-text audit of Tang et al.
(arXiv:2606.31339v1).  That paper makes a typed affected-scope, verifier-gated,
atomic governed proposal the closest public architecture control.  The new
zero-provider implementation has passed all four assigned dependent sequences
and is therefore capable of entering a learned comparison.

No v1 formal method outcome has been generated.  This amendment is caused by
external prior art and capability evidence, not by observed v1 treatment
results.  The v1 manifest, runner and analysis remain immutable provenance and
must not be relabeled v2.

## v2 design

Retain the 40 fixed task-0 sequence units and two dependent events per unit.
Add `governed_delta` as a fifth arm.  The design contains 40 x 5 x 2 = **400
fixed provider calls**, zero retries and zero repairs.

Arms:

1. CoPE typed minimum update;
2. neutral JSON-path transaction;
3. governed affected-scope forest/blackboard delta;
4. complete semantic-state regeneration;
5. full remaining-task replan.

All five must pass oracle capability, common-input, shared-validator and shared
physical-directive gates before any learned formal call.

## Co-primary efficacy family

The co-primary comparisons are:

- CoPE versus neutral patch;
- CoPE versus governed delta.

For each, use sequence-level success and a two-sided exact paired McNemar test.
Holm-adjust the two efficacy p-values as one family.  Each comparison must have
adjusted p < 0.05 and paired risk difference at least +0.15.

Neither FSR-PC nor full-replan success can rescue a failure of either
co-primary comparison.  Their paired tests remain secondary and are Holm
adjusted as a separate descriptive family.

## Co-primary locality family

Within sequences where CoPE and the named control have parser- and
semantic-valid outputs for both events, compare total proposal bytes.  For each
control report median paired relative reduction and an exact sign test after
discarding ties.  Holm-adjust the neutral and governed locality p-values as one
family.  Both controls must satisfy adjusted p < 0.05 and median reduction at
least 20%.

Contract bytes are reported separately and cannot satisfy the proposal
locality endpoint.

## Safety and integrity gates

For each co-primary control, CoPE must have no greater count of stale-execution
sequences and no greater count of invariant-violation sequences.  All 40 shared
substrates must be eligible.  Any retry, arm-specific common-input hash,
prefix-hash divergence, missing cell, invalid dependency skip or unauthorized
state access aborts analysis.

## Machine decision

The joint necessary gate passes only when substrate, both efficacy comparisons,
both safety comparisons and both locality comparisons pass.  A one-task pass is
reported as `NECESSARY_GATE_PASS_SINGLE_TASK_ONLY`, never submission GO.

If CoPE ties either neutral or governed control, the method-superiority route
fails even if FSR-PC loses 40/40.  The correct route is compact specialization,
benchmark/protocol contribution or stop.

