# X15 generic typed-interpreter preregistration

Frozen date: 2026-08-03 (Asia/Shanghai)

## Motivation

X14 found 0/16 CoPE representation fail-opens versus 7/16 for compact TX and
12/16 for FSR-PC, but CoPE's materializer compared the proposal exactly with
`expected_patch`. A matched exact-output guard made all arms reject 16/16. This
experiment removes that oracle-equivalent confound.

## Four frozen arms

1. `cope_exact`: current typed patch plus exact `expected_patch` guard;
2. `cope_generic`: the same patch syntax interpreted by a new generic typed
   operation executor;
3. `compact_tx`: generic compact path/value transaction;
4. `fsr_pc`: full-state-v2 rewrite.

The generic typed executor may inspect the event, current state, authority,
versions, stable IDs, operation types, and operation-local preconditions. It may
not import or call `expected_patch`, `derive_post_state`, or
`validate_and_compile`; it may not compare a proposal or candidate with a
canonical answer. A static source audit enforces the forbidden-symbol rule.

All four candidates then enter the same `validate_and_compile` only as the
final common validator.

## Cases and fault assignments

Use the 12 frozen public-synthetic N-track cases. Run 48 canonical controls
(12 cases x 4 arms) and 88 fault cells (22 assignments x 4 arms).

The first 16 assignments reproduce X14's structural, binding, authorization,
idempotence, progress, continuity, stable-ID, duplication, grounding, omission,
version, and scope faults. Six additional whole-operation omission assignments
cover cancellation, replacement, activation, release, conflicting-event
handling, and acknowledgement with a retained executing action.

Mutations are arm-specific encodings of the same semantic intent. They are not
byte-identical. Every faulty proposal must differ from its arm's canonical
proposal or the run is invalid.

## Outcomes

For each cell record parser acceptance, native representation guard acceptance,
candidate equality to the oracle, representation fail-open, common validator
calls/acceptance, end-to-end fail-open, rejection layer, caller-state mutation,
and crash.

Primary descriptive slices:

- all 22 assignments;
- `commission_or_structure` (the original X14 threats except the two omission
  cases already present);
- `omission` (F10, F14, and O01--O06; eight clustered probes, including partial
  and whole-event omissions).

No significance test is planned; rows are clustered hand-designed faults.

## Frozen gates and predictions

1. Clean control: 48/48 exact oracle state and one common-validator call.
2. Pipeline safety: 0/88 end-to-end fail-opens, crashes, or caller mutations.
3. Oracle removal: `cope_generic` must have at least one representation
   fail-open; otherwise the implementation likely retained an exact oracle.
4. Local typed-assurance: on `commission_or_structure`, `cope_generic` has fewer
   representation fail-opens than both compact TX and FSR-PC.
5. Completeness boundary: no claim is allowed that typed operations prevent
   omissions. If `cope_generic` materializes wrong candidates on omission
   probes, the paper must state that a common completeness validator remains
   necessary.
6. `cope_exact` is an upper-bound/oracle-control arm, not the proposed fair
   deployment result.

## Evidence boundary

This is deterministic offline fault injection, not learned-provider, security,
simulator, or robot evidence. Use no credential, provider call, GPU, simulator,
robot, or LIBERO state 27--49. Preserve outputs and use an independent CSV-only
audit.

