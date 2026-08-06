# X11 TX-EXEC+ strong-falsification preregistration

Frozen date: 2026-08-02 (Asia/Shanghai)

## Question and claim boundary

This CPU-only synthetic semantic experiment asks whether a generic persistent
transactional executive, without CoPE's typed-patch schema or patch engine, can
produce the same accepted canonical post-state and execution directive as CoPE
and native FSR-PC on the frozen N-track event contract.

If TX-EXEC+ is semantically equivalent, atomic, deterministic, and similarly
auditable, the result falsifies any claim that CoPE has unique execution-state
expressivity on these cases. CoPE may still have a learned-generation
factorization, serialized-output, ergonomics, or domain-schema advantage.

This experiment does not call an LLM, robot, simulator, policy, planner, or GPU.
It does not read LIBERO states 27--49 and cannot support learned or embodied
success claims.

## Independence constraints

The TX-EXEC implementation must not import or call:

- `expected_patch`;
- `materialize_patch`;
- `derive_post_state`;
- CoPE `apply_patch`, `PatchOutput`, or `ConstraintStateEngine`;
- the CoPE semantic materializer.

It may consume the same plain pre-state and event and may call the common
event-bound validator/compiler once after independently staging its candidate.
The experiment may use `derive_post_state` only as the separately named oracle
reference for comparison.

## Frozen corpus

The 12 cases in `01_CASE_MANIFEST.csv` are copied from the already frozen native
N-track manifest. They cover no-op, cancellation, replacement, override,
release, release after world change, wrong authority, stale version,
idempotence, irrelevant change, and valid/invalid action continuity.

Each case has three clean constructors:

1. Oracle reference post-state;
2. CoPE minimum typed patch materialized to full state;
3. independent TX-EXEC+ transaction.

Native FSR-PC is represented by the Oracle full post-state because the native
full-state control is the exact canonical reference, not a learned sample.

## Frozen TX-EXEC+ model

TX-EXEC+ is a generic optimistic transaction over a persistent task graph:

- check base semantic version, authority, issuer, and duplicate event before
  opening a write transaction;
- stage generic node updates/inserts plus projection replacements for goals,
  plan, restorations, entities, evidence, and semantic version;
- retain an executing action only when it remains legal;
- validate the staged full state with the common validator/compiler;
- publish by atomic swap only after validation;
- record before/staged/after hashes, mutation addresses, read/write versions,
  validator calls, decision, and rollback status.

The transaction carrier is generic address/value mutations. It must not expose
CoPE operation names such as `Expire`, `Supersede`, or `AddCommitment`.

## Assigned clean endpoints

For all 12 cases:

- TX-EXEC candidate equals Oracle canonical post-state;
- TX-EXEC candidate equals materialized CoPE post-state;
- all three compile to the same directive;
- input state remains byte-identical;
- valid-progress ledger is preserved or revalidated as specified;
- unauthorized, stale, and duplicate events commit a no-op;
- receipt before/staged/after hashes and version fields are internally valid;
- exactly one common validator call is recorded for a committed transaction;
- deterministic replay is byte-identical.

Any clean failure rejects semantic equivalence.

## Assigned fault-injection endpoints

`02_FAULT_MANIFEST.csv` freezes eight failures injected after staging but before
publication: unauthorized target mutation, progress deletion, stale version
bypass, wrong-authority bypass, wrong replacement grounding, restoration loss,
illegal executing-action continuation, and forced validator exception.

Every injected run must fail closed, leave the caller-visible pre-state
byte-identical, publish no post-state, and record rollback. Any partial publish
rejects atomicity.

## Resource and audit endpoints

For each clean case, record canonical bytes for CoPE patch, TX mutation carrier,
TX receipt, and FSR full state; staging/validation/commit latency; Python
`tracemalloc` peak; mutation count; validator calls; and audit fields. Timing is
descriptive, uses 20 warm-ups plus 100 recorded repetitions, alternates order by
case index, and does not support general runtime claims.

The auditability comparison is structural: presence of event ID, actor,
authority decision, versions, changed addresses, before/after hashes,
validation decision, and rollback status. It does not measure human debugging
time.

## Decision rules

1. `12/12` clean semantic equality, directive equality, input immutability, and
   receipt integrity plus `8/8` atomic fault rejection means TX-EXEC+ passes the
   strong falsifier.
2. If TX-EXEC+ passes, prohibit claims of unique state-transition expressivity
   or that generic transactions cannot preserve commitments.
3. If TX-EXEC+ fails only because of an implementation bug, fix and rerun under
   a separately recorded corrective stage; do not count the failure as evidence
   for CoPE.
4. Byte/time/memory differences are implementation-specific diagnostics.
5. No result unlocks reserved LIBERO states or substitutes for the blocked real
   N-track provider experiment.

