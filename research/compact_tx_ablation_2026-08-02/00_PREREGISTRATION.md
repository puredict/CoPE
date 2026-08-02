# X12 compact generic transaction ablation preregistration

Frozen date: 2026-08-02 (Asia/Shanghai)

## Question

X11 showed that a generic transactional executive is semantically equivalent
to CoPE on 12 frozen cases, but its verbose carrier stores per-write before and
after hashes and is often larger than a full state. This ablation asks whether
that resource result is an encoding artifact.

The tested compact carrier is a generic path/value transaction resembling JSON
Patch. It contains only schema, base semantic version, event ID, and ordered
`replace`/`add` path-value writes. Before/after hashes remain executor-generated
receipt fields and are not provider proposal bytes.

## Claim boundary

This is a deterministic CPU encoding/materialization experiment. The compact
proposal is mechanically derived from the already independent X11 TX staging
result; no model generates it. It tests executable representational overhead,
not learned-generation accuracy or embodied recovery.

No GPU, LLM, robot, simulator, checkpoint, or LIBERO state is used. States
27--49 remain untouched.

## Frozen corpus and comparison

Use the same 12 N-track cases as X11. For each case compare canonical compact
JSON bytes for:

1. CoPE specialized minimum typed patch;
2. compact generic path/value transaction;
3. X11 verbose generic transaction carrier;
4. FSR canonical full-state-v2.

Audit receipt bytes are reported separately from proposal bytes for every
method. Adding receipt bytes to only one proposal is prohibited.

## Independent materializer constraints

The compact materializer must not import or call the CoPE patch engine,
`expected_patch`, `materialize_patch`, or `derive_post_state`. It may apply
generic writes to a deep-copied base state and then call the common event-bound
validator/compiler exactly once before publishing.

Allowed path forms are frozen:

- `/commitments/<stable-id>/<field>`;
- `/commitments/+/<stable-id>`;
- `/entities/+/<stable-id>`;
- `/current_goal`;
- `/plan`;
- `/pending_restorations`;
- `/state_version`;
- `/evidence_versions`.

Unknown roots, unknown records, duplicate paths, wrong operation/path form,
wrong event ID, and wrong base version fail before validation. Semantic value
corruptions fail in the common validator. Publication is an atomic swap after
validation; caller input must remain byte-identical on success and failure.

## Assigned endpoints

Clean cases, required 12/12:

- materialized compact candidate equals X11 TX candidate, materialized CoPE,
  and FSR canonical reference;
- directive equality;
- one validator call;
- input immutability;
- receipt before/staged/after hash integrity;
- deterministic proposal and materialized-state replay.

Fault cases, required 8/8:

1. stale base version;
2. wrong event ID;
3. forbidden root path;
4. duplicate path;
5. unknown stable record ID;
6. progress-ledger semantic corruption;
7. illegal executing-action continuation;
8. external validator exception.

Every fault must fail closed, publish no state, record rollback, and preserve
the caller pre-state.

## Resource protocol

Byte counts use canonical compact JSON. Timing and `tracemalloc` are
descriptive: 20 warm-ups and 100 recorded repetitions per case/method, with
method order rotated by case and repetition. Record parse/materialize,
validation, commit, total, and peak allocation separately where available.

## Frozen interpretation rules

1. Compact materialization is eligible only after 12/12 clean and 8/8 faults.
2. If compact proposal is smaller than FSR in at least 8/12 cases and its
   median compact/FSR byte ratio is at most 0.9, X11's verbose-TX byte result is
   classified as substantially encoding-confounded.
3. If CoPE is smaller than compact TX in 12/12 cases and median CoPE/compact is
   at most 0.5, a specialized sparse-output size advantage remains on this
   corpus, without implying learned correctness.
4. If compact TX approaches or beats CoPE, sparse-output size is not
   CoPE-specific and claims must shrink further.
5. Time and memory results are implementation diagnostics, not universal
   representation claims.

